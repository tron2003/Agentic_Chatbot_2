"""
Agent route: a ReAct loop with tools and live reasoning events.

Each model turn streams its text to the client as it is generated. When the
turn ends with tool calls, the node emits ``draft_reset`` so the client moves
that text into the reasoning timeline (it was the agent thinking out loud, not
the answer), then runs the tools in parallel and emits a timeline stop per
tool call. The final turn, without tool calls, is the answer.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.integrations.registry import tool_titles
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.nodes.events import emit, step
from agentic_chatbot.prompts.agent_prompt import FINALIZE_INSTRUCTION, build_agent_prompt
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.tools.mcp_tools import get_agent_tools
from agentic_chatbot.utils.message_builder import context_window, message_text, strip_think

logger = logging.getLogger(__name__)

TOOL_TITLES = {
    "web_search": "Searching the web",
    "calculator": "Calculating",
    "current_datetime": "Checking the date and time",
    "search_knowledge_base": "Searching your documents",
    "read_pdf": "Reading a PDF",
    "describe_spreadsheets": "Reading your spreadsheets",
    "query_spreadsheet": "Calculating from your spreadsheet",
}


def _describe_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    if len(args) == 1:
        value = next(iter(args.values()))
        return value if isinstance(value, str) else json.dumps(value)[:200]
    return json.dumps(args, ensure_ascii=False)[:240]


async def _run_tool(tools: dict[str, BaseTool], call: dict[str, Any], timeout: float, max_chars: int) -> ToolMessage:
    name, call_id = call["name"], call["id"]
    tool = tools.get(name)
    if tool is None:
        return ToolMessage(content=f"Error: tool '{name}' does not exist.", tool_call_id=call_id, name=name, status="error")
    try:
        result = await asyncio.wait_for(
            tool.ainvoke({"type": "tool_call", "id": call_id, "name": name, "args": call.get("args") or {}}),
            timeout=timeout,
        )
    except TimeoutError:
        return ToolMessage(content=f"Error: {name} timed out after {timeout:.0f}s.", tool_call_id=call_id, name=name, status="error")
    except Exception as exc:  # tool raised
        logger.warning("Tool %s failed: %s", name, exc)
        return ToolMessage(content=f"Error running {name}: {exc}", tool_call_id=call_id, name=name, status="error")

    if not isinstance(result, ToolMessage):
        result = ToolMessage(content=str(result), tool_call_id=call_id, name=name)
    text = message_text(result.content) if not isinstance(result.content, str) else result.content
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[output truncated]"
    return ToolMessage(content=text, tool_call_id=call_id, name=name, artifact=result.artifact,
                       status=getattr(result, "status", "success"))


def _preview_items(found: list[dict], limit: int = 6) -> list[dict]:
    """What a search turned up, for the live activity line and source chips in the timeline."""
    return [{"title": (s.get("title") or "")[:120], "url": s.get("url")} for s in found[:limit] if s.get("url") or s.get("title")]


def _sources_from(message: ToolMessage) -> list[dict]:
    artifact = message.artifact
    if isinstance(artifact, list):
        return [s for s in artifact if isinstance(s, dict) and (s.get("url") or s.get("title"))]
    return []


async def agent_node(state: Chatbot, config: RunnableConfig) -> dict:
    with ExecutionTimer("agent_node", logger_instance=logger):
        cfg = config_section("agent")
        max_iterations = int(cfg.get("max_iterations", 8))
        timeout = float(cfg.get("tool_timeout_seconds", 45))
        max_chars = int(cfg.get("max_tool_output_chars", 12000))

        kb_available = await get_knowledge_base().has_documents()
        tools = get_agent_tools(include_kb=kb_available)
        by_name = {t.name: t for t in tools}
        titles = {**TOOL_TITLES, **tool_titles()}
        llm = get_llm("main").bind_tools(tools)

        history: list[BaseMessage] = [
            SystemMessage(content=build_agent_prompt(list(by_name), state.summary, state.user_memories))
        ]
        history.extend(context_window(state.messages))

        sources: list[dict] = []
        seen_urls: set[str] = set()
        final: AIMessage | None = None

        for iteration in range(max_iterations + 1):
            last_round = iteration == max_iterations
            if last_round:
                history.append(HumanMessage(content=FINALIZE_INSTRUCTION))
            response: AIMessage = await llm.ainvoke(history, config=config)
            history.append(response)

            if not response.tool_calls or last_round:
                final = response
                break

            thought = strip_think(message_text(response.content))
            emit({"type": "draft_reset"})
            if thought:
                step("thinking", "Planning", thought)

            logger.info("Agent iteration %d: %d tool call(s)", iteration + 1, len(response.tool_calls))
            for call in response.tool_calls:
                step("tool", titles.get(call["name"], f"Using {call['name']}"), _describe_args(call.get("args") or {}),
                     step_id=call["id"], status="running", tool=call["name"])

            results = await asyncio.gather(*[_run_tool(by_name, c, timeout, max_chars) for c in response.tool_calls])

            for call, result in zip(response.tool_calls, results, strict=True):
                found = _sources_from(result)
                fresh = [s for s in found if not s.get("url") or s["url"] not in seen_urls]
                seen_urls.update(s["url"] for s in fresh if s.get("url"))
                sources.extend(fresh)
                preview = result.content if isinstance(result.content, str) else message_text(result.content)
                summary = f"{len(found)} result{'s' if len(found) != 1 else ''}" if found else preview[:280]
                step("tool", titles.get(call["name"], f"Used {call['name']}"), _describe_args(call.get("args") or {}),
                     step_id=call["id"], status="error" if result.status == "error" else "done",
                     tool=call["name"], result=summary, items=_preview_items(found))
            if sources:
                emit({"type": "sources", "items": sources})
            history.extend(results)

        answer = strip_think(message_text(final.content)) if final else ""
        if not answer:
            answer = "I couldn't put together an answer from the tool results. Try rephrasing the question."
        return {"messages": [AIMessage(content=answer)]}
