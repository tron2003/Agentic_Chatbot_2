"""
Agent route: a ReAct loop with tools and live reasoning events.

Each model turn streams its text to the client as it is generated. When the
turn ends with tool calls, the node emits ``draft_reset`` so the client moves
that text into the reasoning timeline (it was the agent thinking out loud, not
the answer), then runs the tools in parallel and emits a timeline stop per
tool call. The final turn, without tool calls, is the answer.

Approval step: when a turn asks for an **act** tool (see ``services.tool_policy``),
read tools from that turn still run, but the act calls wait. The node saves its
loop in state (``agent_scratch``…) and returns; the graph moves to the
``approval`` node, which pauses with ``interrupt()``. When the user decides, the
graph comes back here, runs the approved calls, tells the model which ones were
declined, and carries on from the saved round. Pausing in a separate node matters:
on resume LangGraph re-runs the whole interrupted node, and re-running this loop
would call the model and the finished tools again.

Runs with nobody to approve (the OpenAI-compatible API, the MCP server) don't
pause: act calls are declined with a note saying approval is needed in the app.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import interrupt

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section, get_settings
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.integrations.registry import tool_titles
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.nodes.events import emit, step
from agentic_chatbot.prompts.agent_prompt import FINALIZE_INSTRUCTION, build_agent_prompt
from agentic_chatbot.services import connections
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.services.tool_policy import decide, server_of, tool_key
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

DECLINED_BY_USER = (
    "Not run: the user declined this action. Don't try it again in this answer; "
    "tell the user plainly that it wasn't done."
)
NEEDS_APP_APPROVAL = (
    "Not run: this action needs the user's approval, which can only be given in the {app} app. "
    "Tell the user it wasn't done and that they can approve it there."
)

# State written when an answer is finished, so nothing from a paused loop leaks into the next turn.
CLEARED: dict[str, Any] = {
    "agent_scratch": [], "agent_round": 0, "agent_sources": [], "pending_actions": [], "action_decisions": {},
}


def _describe_args(args: dict[str, Any]) -> str:
    if not args:
        return ""
    if len(args) == 1:
        value = next(iter(args.values()))
        return value if isinstance(value, str) else json.dumps(value)[:200]
    return json.dumps(args, ensure_ascii=False)[:240]


def _humanize(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").strip().capitalize()


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


class _Loop:
    """Everything one agent turn needs; survives a pause through ``to_state`` / ``from_state``."""

    def __init__(self, tools: list[BaseTool]):
        cfg = config_section("agent")
        self.max_iterations = int(cfg.get("max_iterations", 8))
        self.timeout = float(cfg.get("tool_timeout_seconds", 45))
        self.max_chars = int(cfg.get("max_tool_output_chars", 12000))
        self.by_name = {t.name: t for t in tools}
        self.titles = {**TOOL_TITLES, **tool_titles()}
        self.sources: list[dict] = []
        self.seen_urls: set[str] = set()

    def title(self, name: str) -> str:
        return self.titles.get(name) or _humanize(name)

    def describe_action(self, call: dict[str, Any]) -> dict[str, Any]:
        tool = self.by_name.get(call["name"])
        return {
            "id": call["id"],
            "tool": call["name"],
            "key": tool_key(tool) if tool else call["name"],
            "server": server_of(tool) if tool else "",
            "title": self.title(call["name"]),
            "args": call.get("args") or {},
            "description": ((tool.description or "") if tool else "").strip()[:300],
        }

    def record(self, call: dict[str, Any], result: ToolMessage, status: str | None = None) -> None:
        """Timeline stop for a finished call, and its sources."""
        found = _sources_from(result)
        fresh = [s for s in found if not s.get("url") or s["url"] not in self.seen_urls]
        self.seen_urls.update(s["url"] for s in fresh if s.get("url"))
        self.sources.extend(fresh)
        preview = result.content if isinstance(result.content, str) else message_text(result.content)
        summary = f"{len(found)} result{'s' if len(found) != 1 else ''}" if found else preview[:280]
        step("tool", self.title(call["name"]), _describe_args(call.get("args") or {}),
             step_id=call["id"], status=status or ("error" if result.status == "error" else "done"),
             tool=call["name"], result=summary, items=_preview_items(found))

    async def run(self, calls: list[dict[str, Any]]) -> list[ToolMessage]:
        for call in calls:
            step("tool", self.title(call["name"]), _describe_args(call.get("args") or {}),
                 step_id=call["id"], status="running", tool=call["name"])
        results = await asyncio.gather(*[_run_tool(self.by_name, c, self.timeout, self.max_chars) for c in calls])
        for call, result in zip(calls, results, strict=True):
            self.record(call, result)
        return list(results)

    def skip(self, call: dict[str, Any], text: str, summary: str) -> ToolMessage:
        """A call that won't run: the model gets ``text``, the timeline shows ``summary``."""
        result = ToolMessage(content=text, tool_call_id=call["id"], name=call["name"], status="error")
        step("tool", self.title(call["name"]), _describe_args(call.get("args") or {}), step_id=call["id"],
             status="declined", tool=call["name"], result=summary)
        return result


async def agent_node(state: Chatbot, config: RunnableConfig) -> dict:
    with ExecutionTimer("agent_node", logger_instance=logger):
        interactive = bool(((config or {}).get("configurable") or {}).get("interactive"))
        kb_available = await get_knowledge_base().has_documents()
        tools = get_agent_tools(include_kb=kb_available)
        loop = _Loop(tools)
        llm = get_llm("main").bind_tools(tools)
        settings = connections.tool_settings()

        system = SystemMessage(content=build_agent_prompt(list(loop.by_name), state.summary, state.user_memories))
        resuming = bool(state.agent_scratch and state.pending_actions and state.action_decisions)

        if resuming:
            history: list[BaseMessage] = [system, *state.agent_scratch]
            loop.sources = list(state.agent_sources)
            loop.seen_urls = {s["url"] for s in loop.sources if s.get("url")}
            calls = _pending_calls(state)
            approved = [c for c in calls if state.action_decisions.get(c["id"]) == "approve"]
            declined = [c for c in calls if state.action_decisions.get(c["id"]) != "approve"]
            results = await loop.run(approved) if approved else []
            results += [loop.skip(c, DECLINED_BY_USER, "You declined this") for c in declined]
            order = {c["id"]: i for i, c in enumerate(calls)}
            history.extend(sorted(results, key=lambda m: order.get(m.tool_call_id, 0)))
            if loop.sources:
                emit({"type": "sources", "items": loop.sources})
            start = state.agent_round + 1
            logger.info("Agent resumed: %d approved, %d declined", len(approved), len(declined))
        else:
            history = [system, *context_window(state.messages)]
            start = 0

        final: AIMessage | None = None
        for iteration in range(start, loop.max_iterations + 1):
            last_round = iteration >= loop.max_iterations
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

            calls = list(response.tool_calls)
            asks = [c for c in calls if decide(loop.by_name.get(c["name"]), settings) == "ask"]
            now = [c for c in calls if c not in asks]

            if asks and interactive:
                for call in asks:
                    step("tool", loop.title(call["name"]), _describe_args(call.get("args") or {}),
                         step_id=call["id"], status="waiting", tool=call["name"], result="Waiting for your approval")
                results = await loop.run(now) if now else []
                history.extend(results)
                if loop.sources:
                    emit({"type": "sources", "items": loop.sources})
                logger.info("Agent paused for approval: %s", ", ".join(c["name"] for c in asks))
                return {
                    "agent_scratch": history[1:],
                    "agent_round": iteration,
                    "agent_sources": loop.sources,
                    "pending_actions": [loop.describe_action(c) for c in asks],
                    "action_decisions": {},
                }

            note = NEEDS_APP_APPROVAL.format(app=get_settings().app_name)
            results = await loop.run(now) if now else []
            results += [loop.skip(c, note, "Needs your approval in the app") for c in asks]
            order = {c["id"]: i for i, c in enumerate(calls)}
            if loop.sources:
                emit({"type": "sources", "items": loop.sources})
            history.extend(sorted(results, key=lambda m: order.get(m.tool_call_id, 0)))

        answer = strip_think(message_text(final.content)) if final else ""
        if not answer:
            answer = "I couldn't put together an answer from the tool results. Try rephrasing the question."
        return {"messages": [AIMessage(content=answer)], **CLEARED}


def _pending_calls(state: Chatbot) -> list[dict[str, Any]]:
    """The waiting calls, rebuilt from the last model turn in the saved loop."""
    wanted = {a["id"] for a in state.pending_actions}
    for msg in reversed(state.agent_scratch):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            return [c for c in msg.tool_calls if c["id"] in wanted]
    return [{"id": a["id"], "name": a["tool"], "args": a.get("args") or {}} for a in state.pending_actions]


def _normalize(decision: Any, actions: list[dict]) -> dict[str, str]:
    """Accept {id: "approve"|"decline"}, {"approve": [...ids]}, or True/False for all. Anything unclear declines."""
    ids = [a["id"] for a in actions]
    if isinstance(decision, bool):
        return dict.fromkeys(ids, "approve" if decision else "decline")
    if isinstance(decision, dict) and isinstance(decision.get("approve"), list):
        chosen = set(decision["approve"])
        return {i: "approve" if i in chosen else "decline" for i in ids}
    if isinstance(decision, dict):
        return {i: "approve" if str(decision.get(i, "")).lower() in ("approve", "approved", "yes", "allow") else "decline"
                for i in ids}
    return dict.fromkeys(ids, "decline")


async def approval_node(state: Chatbot) -> dict:
    """Pause until the user approves or declines the waiting actions.

    Kept tiny on purpose: on resume LangGraph re-runs this node from the top, and the only
    thing it does is read the answer that ``interrupt()`` now returns.
    """
    decision = interrupt({"type": "approval", "actions": state.pending_actions})
    return {"action_decisions": _normalize(decision, state.pending_actions)}


def after_agent(state: Chatbot) -> bool:
    """True when the agent stopped to wait for approval."""
    return bool(state.pending_actions) and not state.action_decisions
