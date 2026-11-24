"""
OpenAI-compatible API so other agent apps can use Junction as their model.

    GET  /v1/models
    POST /v1/chat/completions   (stream or JSON)

Point OpenClaw (custom provider, api: openai-completions), Hermes Agent, Open
WebUI, LibreChat or any OpenAI SDK at ``http://<host>:8001/v1`` with model
``junction``. Every request goes through the same router → chat / documents /
research pipeline as the web UI.

Sessions
--------
* Default (stateless): the client's message history is used as-is for one
  turn in a temporary thread, which is deleted afterwards. This is what agent
  apps expect, since they keep their own history.
* With a ``user`` field or ``X-Junction-Conversation`` header: Junction keeps
  the conversation itself (memory, summaries), only the latest user message is
  used, and the conversation shows up in Junction's sidebar.

Client-side ``tools`` are ignored: Junction answers with its own tools (web,
documents, connected agents) and never returns ``tool_calls``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel, ConfigDict, Field

from agentic_chatbot.api.security import rate_limit
from agentic_chatbot.core.context import get_request_id
from agentic_chatbot.integrations.config import get_integrations
from agentic_chatbot.services.chat_service import TurnError, _spawn, prepare_turn, public_error
from agentic_chatbot.services.store import get_store

logger = logging.getLogger(__name__)


async def require_openai_key(request: Request) -> None:
    keys = get_integrations().openai_api.key_set()
    if not keys:
        return
    auth = request.headers.get("authorization", "")
    presented = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not any(hmac.compare_digest(presented, k) for k in keys):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key.", headers={"WWW-Authenticate": "Bearer"})


router = APIRouter(prefix="/v1", tags=["openai-compatible"], dependencies=[Depends(require_openai_key)])


class OAIMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    role: str
    content: str | list[Any] | None = None


class OAIChatRequest(BaseModel):
    model_config = ConfigDict(extra="allow")  # tools, temperature, etc. are accepted and ignored
    model: str | None = None
    messages: list[OAIMessage] = Field(min_length=1)
    stream: bool = False
    user: str | None = Field(None, max_length=200)


def _text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        if isinstance(part, dict) and part.get("type") in ("text", "input_text"):
            parts.append(str(part.get("text", "")))
        elif isinstance(part, str):
            parts.append(part)
    return "\n".join(p for p in parts if p)


def to_history(messages: list[OAIMessage]) -> list[BaseMessage]:
    """Keep user/assistant text; drop the client's system prompt, tool calls and tool results."""
    history: list[BaseMessage] = []
    for m in messages:
        text = _text(m.content).strip()
        if not text:
            continue
        if m.role == "user":
            history.append(HumanMessage(content=text))
        elif m.role == "assistant":
            history.append(AIMessage(content=text))
    return history


def _sources_footer(sources: list[dict]) -> str:
    lines = []
    for i, s in enumerate(sources[:8], start=1):
        if s.get("url"):
            lines.append(f"{i}. [{s.get('title') or s['url']}]({s['url']})")
        else:
            page = f", p. {s['page']}" if s.get("page") else ""
            lines.append(f"{i}. {s.get('title', 'document')}{page}")
    return "\n\nSources:\n" + "\n".join(lines) if lines else ""


async def _text_events(events: AsyncIterator[dict[str, Any]], append_sources: bool) -> AsyncIterator[tuple[str, Any]]:
    """Turn Junction events into ("delta", text) / ("ping", None) / ("error", {...}) / ("final", meta).

    Research answers are held back until final: the agent's planning text streams
    first and is withdrawn (draft_reset), which an OpenAI client can't undo.
    """
    route: str | None = None
    held = ""
    streamed = ""
    final: str | None = None
    sources: list[dict] = []
    conversation_id: str | None = None
    try:
        async for ev in events:
            kind = ev.get("type")
            if kind == "meta":
                conversation_id = ev.get("conversation_id")
            elif kind == "route":
                route = ev.get("route")
            elif kind == "token":
                if route == "agent":
                    held += ev["text"]
                else:
                    streamed += ev["text"]
                    yield "delta", ev["text"]
            elif kind == "draft_reset":
                held = ""
            elif kind == "sources":
                sources = list(ev.get("items") or [])
            elif kind == "answer":
                final = ev.get("content") or ""
            elif kind == "done":
                final = ev["message"]["content"]
            elif kind == "error":
                yield "error", {"message": ev.get("message"), "code": ev.get("code")}
                return
            elif kind == "ping":
                yield "ping", None
    except Exception as exc:  # stateless path: pipeline errors arrive as exceptions
        logger.error("OpenAI-compatible turn failed", exc_info=exc)
        yield "error", public_error(exc)
        return

    answer = final if final is not None else (streamed or held)
    if answer.startswith(streamed):
        rest = answer[len(streamed):]
        if rest:
            yield "delta", rest
    if append_sources and sources:
        yield "delta", _sources_footer(sources)
    yield "final", {"route": route, "sources": sources, "conversation_id": conversation_id}


@router.get("/models")
async def list_models():
    name = get_integrations().openai_api.model_name
    return {"object": "list", "data": [{"id": name, "object": "model", "created": 0, "owned_by": "junction"}]}


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    name = get_integrations().openai_api.model_name
    return {"id": name, "object": "model", "created": 0, "owned_by": "junction"}


def _error_body(message: str, code: str = "server_error") -> dict:
    return {"error": {"message": message, "type": "server_error", "code": code, "request_id": get_request_id()}}


@router.post("/chat/completions", dependencies=[Depends(rate_limit)])
async def chat_completions(body: OAIChatRequest, request: Request):
    cfg = get_integrations().openai_api
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant is still starting.")

    history = to_history(body.messages)
    if not history or not isinstance(history[-1], HumanMessage):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The last message must be a user message with text.")

    session = request.headers.get("x-junction-conversation") or body.user
    headers: dict[str, str] = {}
    cleanup_thread: str | None = None

    if session and cfg.persist_conversations:
        conversation_id = "oai_" + hashlib.sha256(session.encode()).hexdigest()[:24]
        try:
            turn = await prepare_turn(pipeline, get_store(), conversation_id=conversation_id,
                                      message=str(history[-1].content), source="openai_api")
        except TurnError as exc:
            raise HTTPException(exc.status, exc.message)
        events: AsyncIterator[dict[str, Any]] = turn.events()
        headers["X-Junction-Conversation"] = conversation_id
    else:
        cleanup_thread = f"oai_tmp_{uuid.uuid4().hex[:16]}"
        events = pipeline.stream(cleanup_thread, history)

    def cleanup() -> None:
        checkpointer = getattr(pipeline, "checkpointer", None)
        if cleanup_thread and checkpointer is not None:
            _spawn(checkpointer.adelete_thread(cleanup_thread))

    completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
    created = int(time.time())
    model = cfg.model_name

    if not body.stream:
        content, meta, error = "", {}, None
        try:
            async for kind, value in _text_events(events, cfg.append_sources):
                if kind == "delta":
                    content += value
                elif kind == "error":
                    error = value
                elif kind == "final":
                    meta = value
        finally:
            cleanup()
        if error:
            return JSONResponse(_error_body(error["message"], error.get("code") or "server_error"), status_code=502)
        return JSONResponse(
            {
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "junction": meta,
            },
            headers=headers,
        )

    def chunk(delta: dict, finish: str | None = None, **extra: Any) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            **extra,
        }
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def sse() -> AsyncIterator[str]:
        try:
            yield chunk({"role": "assistant", "content": ""})
            async for kind, value in _text_events(events, cfg.append_sources):
                if kind == "delta":
                    yield chunk({"content": value})
                elif kind == "ping":
                    yield ": ping\n\n"
                elif kind == "error":
                    yield f"data: {json.dumps(_error_body(value['message'], value.get('code') or 'server_error'))}\n\n"
                    break
                elif kind == "final":
                    yield chunk({}, "stop", junction=value)
            yield "data: [DONE]\n\n"
        finally:
            cleanup()

    return StreamingResponse(
        sse(),
        media_type="text/event-stream",
        headers={**headers, "Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
