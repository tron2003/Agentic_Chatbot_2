"""
One chat turn: persist the question, stream the pipeline, persist the answer.

``ChatTurn.events()`` is shared by the SSE endpoint and the JSON endpoint, so
both behave identically. Protocol events added at this layer:

    {"type": "meta", "conversation_id", "message_id", "user_message_id", "is_new"}
    {"type": "title", "conversation_id", "title"}
    {"type": "done", "message": {...stored assistant message...}}
    {"type": "error", "code", "message", "request_id"}
    {"type": "ping"}                             # heartbeat for proxies

Approval step: when the agent pauses before an act tool, the pipeline sends
``approval_required``; the turn stores the message with ``metadata.pending_approval``
and ends with ``done``. ``prepare_resume()`` continues it: the rest of the answer
streams into the same message, and ``metadata.approvals`` records each decision.
Only web turns pause (``interactive``); the OpenAI-compatible API and the MCP server
have nobody to approve, so act tools are declined there.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage

from agentic_chatbot.components.llm_loader import describe_llm, get_llm
from agentic_chatbot.core.context import get_request_id
from agentic_chatbot.exception.exception import CustomException
from agentic_chatbot.integrations.webhooks import emit_event
from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline
from agentic_chatbot.prompts.summary_prompt import TITLE_PROMPT
from agentic_chatbot.services.store import ChatStore
from agentic_chatbot.utils.message_builder import message_text, strip_think

logger = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15.0
_background: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    """Run work that must finish even if the client disconnects (outside the request's cancel scope)."""
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def fallback_title(text: str) -> str:
    text = " ".join(text.split())
    return (text[:57] + "…") if len(text) > 58 else (text or "New chat")


async def generate_title(message: str) -> str:
    try:
        response = await asyncio.wait_for(
            get_llm("router").ainvoke([HumanMessage(content=TITLE_PROMPT.format(message=message[:1500]))]),
            timeout=12,
        )
        title = strip_think(message_text(response.content)).strip().strip("\"'`.").splitlines()[0]
        title = re.sub(r"^(title:\s*)", "", title, flags=re.I).strip()
        return title[:80] if title else fallback_title(message)
    except Exception as exc:
        logger.info("Title generation failed (%s); using fallback", exc)
        return fallback_title(message)


def public_error(exc: BaseException) -> dict[str, str]:
    """Map an exception to a user-facing message. Internal details stay in the logs."""
    if isinstance(exc, CustomException):
        return {"code": exc.error_code, "message": exc.public_message}
    name = type(exc).__name__
    text = str(exc).lower()
    if "AuthenticationError" in name or "PermissionDenied" in name or "401" in text and "auth" in text:
        return {"code": "LLM_AUTH", "message": "The model provider rejected the API key. Check the key in .env."}
    if "RateLimit" in name or "429" in text or "overloaded" in text:
        return {"code": "LLM_RATE_LIMIT", "message": "The model provider is busy or rate limiting. Wait a moment and try again."}
    if "NotFound" in name and "model" in text:
        return {"code": "LLM_MODEL_NOT_FOUND", "message": "The configured model wasn't found. Check model_name in config/config.yaml."}
    if "Connect" in name or "Timeout" in name or isinstance(exc, (ConnectionError, TimeoutError)):
        return {"code": "LLM_UNREACHABLE", "message": "Couldn't reach the model provider. Check the network, or OLLAMA_BASE_URL for local models."}
    if "BadRequest" in name and ("context" in text or "too long" in text or "tokens" in text):
        return {"code": "LLM_CONTEXT", "message": "The conversation is too long for the model. Start a new chat."}
    return {"code": "INTERNAL_ERROR", "message": "Something went wrong while generating the answer."}


class _Accumulator:
    def __init__(self) -> None:
        self.draft = ""
        self.answer: str | None = None
        self.route: str | None = None
        self.route_reason: str | None = None
        self.steps: dict[str, dict] = {}
        self.sources: list[dict] = []
        self.pending: list[dict] | None = None  # actions waiting for approval

    @classmethod
    def from_message(cls, message: dict) -> _Accumulator:
        """Carry on from a stored (paused) message: keep its route, timeline and sources."""
        acc = cls()
        meta = message.get("metadata") or {}
        acc.route, acc.route_reason = meta.get("route"), meta.get("route_reason")
        acc.steps = {s["id"]: s for s in meta.get("steps") or [] if isinstance(s, dict) and s.get("id")}
        acc.sources = list(meta.get("sources") or [])
        return acc

    def apply(self, ev: dict[str, Any]) -> None:
        kind = ev.get("type")
        if kind == "token":
            self.draft += ev.get("text", "")
        elif kind == "draft_reset":
            self.draft = ""
        elif kind == "route":
            self.route, self.route_reason = ev.get("route"), ev.get("reason")
        elif kind == "step":
            s = ev["step"]
            self.steps[s["id"]] = {**self.steps.get(s["id"], {}), **s}
        elif kind == "sources":
            self.sources = list(ev.get("items") or [])
        elif kind == "answer":
            self.answer = ev.get("content") or ""
            self.route = self.route or ev.get("route")
        elif kind == "approval_required":
            self.pending = list(ev.get("actions") or [])
            for action in self.pending:
                if action.get("id") in self.steps:
                    self.steps[action["id"]]["status"] = "waiting"

    @property
    def content(self) -> str:
        return self.answer if self.answer is not None else self.draft


class ChatTurn:
    def __init__(self, pipeline: ChatbotPipeline, store: ChatStore, *, conversation_id: str, is_new: bool,
                 message: str | None, model_message: str | None, user_message_id: str | None,
                 checkpoint_id: str | None = None, source: str = "web", mode: str = "auto",
                 user_id: str | None = None, resume: dict[str, str] | None = None, prior: dict | None = None):
        self.pipeline = pipeline
        self.store = store
        self.conversation_id = conversation_id
        self.is_new = is_new
        self.message = message
        self.model_message = model_message
        self.user_message_id = user_message_id
        self.checkpoint_id = checkpoint_id
        self.source = source
        self.mode = mode
        self.user_id = user_id
        self.resume = resume
        self.prior = prior
        self.interactive = source == "web"
        self.assistant_id = prior["id"] if prior else f"msg_{uuid.uuid4().hex[:20]}"

    def _approvals(self) -> list[dict]:
        """Decisions so far for this message: earlier ones plus the ones being resumed now."""
        meta = (self.prior or {}).get("metadata") or {}
        log = list(meta.get("approvals") or [])
        if self.resume is not None:
            for action in (meta.get("pending_approval") or {}).get("actions") or []:
                log.append({k: action.get(k) for k in ("id", "tool", "title", "server", "args")}
                           | {"decision": self.resume.get(action.get("id"), "decline")})
        return log

    def _metadata(self, acc: _Accumulator, started: float, **extra: Any) -> dict[str, Any]:
        llm = describe_llm()
        prior_meta = (self.prior or {}).get("metadata") or {}
        elapsed = int((time.perf_counter() - started) * 1000) + int(prior_meta.get("elapsed_ms") or 0)
        approvals = self._approvals()
        return {
            "route": acc.route,
            "route_reason": acc.route_reason,
            "steps": [s for s in acc.steps.values() if s.get("kind") != "route"],
            "sources": acc.sources,
            "elapsed_ms": elapsed,
            "model": llm["main"]["model"],
            "request_id": get_request_id(),
            "source": self.source,
            **({"mode": self.mode} if self.mode != "auto" else {}),
            **({"approvals": approvals} if approvals else {}),
            **({"pending_approval": {"actions": acc.pending}} if acc.pending else {}),
            **extra,
        }

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        started = time.perf_counter()
        acc = _Accumulator.from_message(self.prior) if self.prior else _Accumulator()
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()
        persisted = False

        yield {
            "type": "meta",
            "conversation_id": self.conversation_id,
            "message_id": self.assistant_id,
            "user_message_id": self.user_message_id,
            "is_new": self.is_new,
            **({"resumed": True} if self.resume is not None else {}),
        }

        async def produce() -> None:
            try:
                async for ev in self.pipeline.stream(self.conversation_id, self.model_message, self.checkpoint_id,
                                                     mode=self.mode, user_id=self.user_id,
                                                     interactive=self.interactive, resume=self.resume):
                    await queue.put(ev)
                await queue.put(sentinel)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await queue.put(exc)

        producer = asyncio.create_task(produce())
        title_task = asyncio.create_task(generate_title(self.message)) if self.is_new and self.message else None

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield {"type": "ping"}
                    continue
                if item is sentinel:
                    break
                if isinstance(item, BaseException):
                    logger.error("Chat turn failed", exc_info=item)
                    err = public_error(item)
                    yield {"type": "error", **err, "request_id": get_request_id()}
                    if acc.content.strip():
                        await self._persist(acc, started, failed=True)
                    persisted = True
                    return
                acc.apply(item)
                if item.get("type") != "answer":
                    yield item

            title: str | None = None
            if title_task:
                try:
                    title = await asyncio.wait_for(title_task, timeout=12)
                except Exception:
                    title = fallback_title(self.message or "")
                await self.store.rename_conversation(self.conversation_id, title)
                yield {"type": "title", "conversation_id": self.conversation_id, "title": title}
                emit_event("conversation.created", {"conversation_id": self.conversation_id, "title": title,
                                                    "source": self.source})

            stored = await self._persist(acc, started)
            persisted = True
            yield {"type": "done", "message": stored}
            if acc.pending:
                return  # answer.completed fires once the paused answer is finished
            if title is None:
                conv = await self.store.get_conversation(self.conversation_id)
                title = conv["title"] if conv else None
            emit_event("answer.completed", {
                "conversation_id": self.conversation_id,
                "message_id": stored["id"],
                "title": title,
                "question": self.message,
                "route": acc.route,
                "content": stored["content"],
                "sources": acc.sources,
                "elapsed_ms": stored["metadata"].get("elapsed_ms"),
                "source": self.source,
            })
        finally:
            if not producer.done():
                producer.cancel()
            if title_task and not title_task.done():
                title_task.cancel()
            if not persisted and acc.content.strip():
                # Client stopped the generation: keep what was produced so far.
                _spawn(self._persist(acc, started, stopped=True))

    async def _persist(self, acc: _Accumulator, started: float, **flags: Any) -> dict:
        content = acc.content.strip() or ("" if acc.pending else "_No answer was produced._")
        return await self.store.add_message(
            self.conversation_id, self.assistant_id, "assistant", content, self._metadata(acc, started, **flags)
        )


class TurnError(Exception):
    """A request that can't start a turn (maps to an HTTP status in the API layer)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


async def prepare_turn(pipeline: ChatbotPipeline, store: ChatStore, *, conversation_id: str | None,
                       message: str | None, regenerate: bool = False,
                       attachments: list[dict] | None = None, source: str = "web",
                       title: str | None = None, mode: str = "auto", user_id: str | None = None) -> ChatTurn:
    """Create/continue a conversation, store the user message and return a ready ChatTurn."""
    conversation_id = conversation_id or f"c_{uuid.uuid4().hex[:20]}"
    existing = await store.get_conversation(conversation_id)

    if regenerate:
        if not existing:
            raise TurnError(404, "Conversation not found.")
        checkpoint_id = await pipeline.regenerate_checkpoint(conversation_id)
        if not checkpoint_id:
            raise TurnError(409, "There is no answer to regenerate in this conversation.")
        await store.delete_last_assistant(conversation_id)
        return ChatTurn(pipeline, store, conversation_id=conversation_id, is_new=False, message=None,
                        model_message=None, user_message_id=None, checkpoint_id=checkpoint_id, source=source,
                        user_id=user_id)

    if not message:
        raise TurnError(422, "Message cannot be empty")
    if not existing:
        await store.create_conversation(conversation_id, title or fallback_title(message))
    else:
        await drop_pending_approval(pipeline, store, conversation_id)

    model_message = message
    metadata: dict[str, Any] = {"source": source} if source != "web" else {}
    if mode == "deep_research":
        metadata["mode"] = mode
    if attachments:
        names = ", ".join(a["name"] for a in attachments)
        model_message += f"\n\n[The user attached these files, now in the knowledge base: {names}]"
        metadata["attachments"] = attachments

    user_message_id = f"msg_{uuid.uuid4().hex[:20]}"
    await store.add_message(conversation_id, user_message_id, "user", message, metadata)
    return ChatTurn(pipeline, store, conversation_id=conversation_id, is_new=not existing,
                    message=message, model_message=model_message, user_message_id=user_message_id, source=source,
                    mode=mode, user_id=user_id)


DROPPED_NOTE = "_Not run: a new message was sent before this action was approved._"


async def _paused_message(store: ChatStore, conversation_id: str, message_id: str | None = None) -> dict | None:
    for msg in reversed(await store.get_messages(conversation_id)):
        if msg["role"] != "assistant":
            continue
        if (msg.get("metadata") or {}).get("pending_approval") and (message_id is None or msg["id"] == message_id):
            return msg
    return None


async def drop_pending_approval(pipeline: ChatbotPipeline, store: ChatStore, conversation_id: str) -> None:
    """A new message on a paused chat counts as declining: mark the stored message so the UI shows it."""
    msg = await _paused_message(store, conversation_id)
    if not msg:
        return
    meta = dict(msg.get("metadata") or {})
    actions = (meta.pop("pending_approval", None) or {}).get("actions") or []
    meta["approvals"] = [*(meta.get("approvals") or []),
                         *({k: a.get(k) for k in ("id", "tool", "title", "server", "args")} | {"decision": "dropped"}
                           for a in actions)]
    for s in meta.get("steps") or []:
        if s.get("status") == "waiting":
            s["status"], s["result"] = "declined", "Not approved"
    content = (msg.get("content") or "").strip()
    await store.add_message(conversation_id, msg["id"], "assistant",
                            f"{content}\n\n{DROPPED_NOTE}".strip(), meta)


async def prepare_resume(pipeline: ChatbotPipeline, store: ChatStore, *, conversation_id: str, message_id: str,
                         decisions: dict[str, str], user_id: str | None = None) -> ChatTurn:
    """Continue a paused answer with the user's decisions ({call id: "approve" | "decline"})."""
    if not await store.get_conversation(conversation_id):
        raise TurnError(404, "Conversation not found.")
    waiting = await pipeline.pending_approval(conversation_id)
    msg = await _paused_message(store, conversation_id, message_id)
    if not waiting or not msg:
        raise TurnError(409, "Nothing in this conversation is waiting for approval. It may have been answered already.")
    ids = {a["id"] for a in waiting}
    clean = {i: ("approve" if str(decisions.get(i, "")).lower() == "approve" else "decline") for i in ids}
    return ChatTurn(pipeline, store, conversation_id=conversation_id, is_new=False, message=None,
                    model_message=None, user_message_id=None, source="web", user_id=user_id,
                    resume=clean, prior=msg)
