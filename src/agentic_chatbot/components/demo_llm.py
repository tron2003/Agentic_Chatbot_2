"""
A scripted chat model for running the app without any API key (LLM_PROVIDER=demo).

It exercises the real pipeline end to end: the router gets a structured
routing decision, the agent receives genuine tool calls (calculator, date/time,
web search when configured), and answers stream token by token. Replies are
clearly labelled as demo output.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool

_MATH = re.compile(r"(\d[\d\s.,]*\s*[-+*/x×^%]\s*[\d\s.,()+\-*/x×^%]+)")
_CURRENT = re.compile(r"\b(latest|today|news|current|now|this week|price|score|release|202\d)\b", re.I)
_DOCS = re.compile(r"\b(document|pdf|paper|file|uploaded|knowledge base|report)\b", re.I)
_TIME = re.compile(r"\b(time|date|day is it|what day)\b", re.I)


def _text(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(b.get("text", "") for b in content if isinstance(b, dict))


class DemoChatModel(BaseChatModel):
    bound_tools: list[str] = []
    token_delay: float = float(os.getenv("DEMO_TOKEN_DELAY", "0.012"))

    @property
    def _llm_type(self) -> str:
        return "demo"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> DemoChatModel:  # type: ignore[override]
        names = [convert_to_openai_tool(t)["function"]["name"] for t in tools]
        return self.model_copy(update={"bound_tools": names})

    # ── scripting ────────────────────────────────────────────────────────────
    def _respond(self, messages: list[BaseMessage]) -> AIMessage:
        system = next((_text(m) for m in messages if isinstance(m, SystemMessage)), "")
        human = next((_text(m) for m in reversed(messages) if isinstance(m, HumanMessage)), "")
        question = human.split("Latest user message:")[-1].strip()

        if "Router" in self.bound_tools:
            agents = re.findall(r"the external agent ([\w-]+) to do", system)
            named = next((a for a in agents if a.lower() in question.lower()), None)
            if named:
                route, reason = "agent", f"The user is asking {named} to do something."
            elif _DOCS.search(question) and "currently EMPTY" not in system:
                route, reason = "rag", "The question refers to the user's documents."
            elif _MATH.search(question) or _CURRENT.search(question) or _TIME.search(question):
                route, reason = "agent", "Needs a tool or current information."
            else:
                route, reason = "chat", "General conversation."
            return AIMessage(
                content="",
                tool_calls=[{"name": "Router", "args": {"route": route, "reason": reason}, "id": _id()}],
            )

        if "conversation title" in human:
            words = re.sub(r"[^\w\s]", "", question.split("Message:")[-1]).split()
            return AIMessage(content=" ".join(words[:5]).capitalize() or "New chat")

        if "running summary" in system or "running summary" in human:
            return AIMessage(content="The user is trying out the assistant in demo mode.")

        if "research agent" in system:
            last = messages[-1]
            if isinstance(last, ToolMessage):
                return AIMessage(content=_agent_answer(question, messages))
            if "Do not call any more tools" in human:
                return AIMessage(content=_agent_answer(question, messages))
            call = _pick_tool(question, self.bound_tools)
            if call:
                return AIMessage(content=call[2], tool_calls=[{"name": call[0], "args": call[1], "id": _id()}])
            return AIMessage(content=_agent_answer(question, messages))

        if "knowledge base passages" in system:
            cited = re.findall(r"^\[(\d+)\] \(source: ([^,)]+)", system, re.M)
            if not cited:
                return AIMessage(content=_demo(f"I searched your documents for **{question}** but found no relevant passages."))
            bullets = "\n".join(f"- Passage [{n}] comes from *{name}*." for n, name in cited[:4])
            return AIMessage(
                content=_demo(
                    f"I found {len(cited)} passages related to **{question}** in your knowledge base.\n\n"
                    f"{bullets}\n\nA real model would now synthesise them into an answer with citations like [1]."
                )
            )

        return AIMessage(content=_chat_answer(question))

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._respond(messages))])

    def _stream(self, messages: list[BaseMessage], stop: list[str] | None = None,
                run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> Iterator[ChatGenerationChunk]:
        for chunk in _chunks(self._respond(messages)):
            if run_manager and isinstance(chunk.message.content, str) and chunk.message.content:
                run_manager.on_llm_new_token(chunk.message.content, chunk=chunk)
            yield chunk

    async def _astream(self, messages: list[BaseMessage], stop: list[str] | None = None,
                       run_manager: AsyncCallbackManagerForLLMRun | None = None, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in _chunks(self._respond(messages)):
            if run_manager and isinstance(chunk.message.content, str) and chunk.message.content:
                await run_manager.on_llm_new_token(chunk.message.content, chunk=chunk)
            yield chunk
            await asyncio.sleep(self.token_delay)


def _id() -> str:
    return f"call_{uuid.uuid4().hex[:12]}"


def _chunks(message: AIMessage) -> Iterator[ChatGenerationChunk]:
    text = message.content if isinstance(message.content, str) else ""
    pieces = re.findall(r"\S+\s*|\s+", text) or [""]
    msg_id = f"run-{uuid.uuid4().hex[:10]}"
    for i, piece in enumerate(pieces):
        last = i == len(pieces) - 1
        yield ChatGenerationChunk(
            message=AIMessageChunk(
                content=piece,
                id=msg_id,
                tool_call_chunks=[
                    {"name": tc["name"], "args": json.dumps(tc["args"]), "id": tc["id"], "index": j}
                    for j, tc in enumerate(message.tool_calls)
                ] if last else [],
            )
        )


def _pick_tool(question: str, tools: list[str]) -> tuple[str, dict, str] | None:
    for tool in tools:
        if tool.startswith("ask_") and tool[4:].replace("_", " ") in question.lower():
            return tool, {"task": question}, f"I'll hand this to {tool[4:]}."
    math = _MATH.search(question)
    if math and "calculator" in tools:
        expr = math.group(1).replace("x", "*").replace("×", "*").replace("^", "**").strip(" .,")
        return "calculator", {"expression": expr}, "Let me work that out with the calculator."
    if _TIME.search(question) and "current_datetime" in tools:
        return "current_datetime", {}, "I'll check the current date and time."
    if "web_search" in tools:
        return "web_search", {"query": question[:200]}, "I'll search the web for this."
    if "current_datetime" in tools and _CURRENT.search(question):
        return "current_datetime", {}, "Web search isn't configured, so I'll at least confirm today's date."
    return None


def _agent_answer(question: str, messages: list[BaseMessage]) -> str:
    results = [m for m in messages if isinstance(m, ToolMessage)]
    if not results:
        return _demo(f"I couldn't find a tool that fits **{question}**, so this is as far as demo mode goes.")
    lines = "\n".join(f"- `{m.name or 'tool'}` returned: {_text(m)[:220].strip()}" for m in results)
    return _demo(
        f"Here's what the tools returned for **{question}**:\n\n{lines}\n\n"
        "With a real model connected, I'd turn these results into a sourced answer."
    )


def _chat_answer(question: str) -> str:
    return _demo(
        f"You said: *{question[:300]}*\n\n"
        "Every message goes through the same three-way router:\n\n"
        "| Route | When it's used | What happens |\n"
        "|---|---|---|\n"
        "| Chat | Explanations, writing, small talk | One model call with your conversation memory |\n"
        "| Documents | Questions about files you uploaded | Passages are retrieved and cited |\n"
        "| Research | Anything current, or tasks needing tools | The agent plans, calls tools, then answers |\n\n"
        "To get real answers, set a provider in `.env`:\n\n"
        "```bash\nLLM_PROVIDER=claude\nANTHROPIC_API_KEY=sk-ant-...\n```"
    )


def _demo(body: str) -> str:
    return f"**Demo mode** (no model connected)\n\n{body}"
