"""Router: decide whether a message goes to chat, rag (documents) or agent (tools)."""

from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.entity.router import Router
from agentic_chatbot.exception.exception import LLMConfigError
from agentic_chatbot.integrations.registry import agent_capabilities
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.nodes.events import emit, step
from agentic_chatbot.prompts.router_prompt import build_router_prompt
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.services.spreadsheets import CALC_INTENT, mentions_sheets, sheets_available
from agentic_chatbot.tools.mcp_tools import get_agent_tools
from agentic_chatbot.utils.message_builder import conversational, latest_user_text, transcript

logger = logging.getLogger(__name__)

_AGENT_HINT = re.compile(
    r"\b(today|tonight|latest|news|current(ly)?|right now|price|stock|shares?|score|weather|release[sd]?|"
    r"this (week|month|year)|who (is|won)|search|look up|calculate|compute|20[2-3]\d|"
    r"research|investigat\w*|find out|fact[- ]check|holdings?|invest(ment|ments|or|ors)?|ceo|revenue|market cap|valuation)\b"
    r"|\d+\s*[-+*/^]\s*\d+",
    re.I,
)
_DOC_HINT = re.compile(r"\b(document|docs|pdf|paper|report|file|uploaded|my notes|knowledge base)\b", re.I)

# The user explicitly asks for research or a lookup. That always goes to Research,
# whatever the router model says, because only that route can search.
_RESEARCH_INTENT = re.compile(
    r"\b(research|investigate|look\s+(it\s+|this\s+|that\s+)?up|look into|search (for|the web|online|about)|"
    r"find out|google|fact[- ]check)\b",
    re.I,
)

ROUTE_LABELS = {"chat": "Chat", "rag": "Documents", "agent": "Deep research"}
_ROUTE_WORD = re.compile(r"\b(chat|rag|agent)\b", re.I)


def heuristic_route(text: str, kb_available: bool) -> Router:
    """Used when the model can't produce a routing decision at all."""
    if kb_available and _DOC_HINT.search(text):
        return Router(route="rag", reason="Mentions the user's documents.")
    if _AGENT_HINT.search(text):
        return Router(route="agent", reason="Looks time-sensitive, asks for research, or needs a tool.")
    return Router(route="chat", reason="General conversation.")


def apply_research_intent(decision: Router, text: str) -> Router:
    """An explicit request to research or look something up always goes to Research."""
    if decision.route == "chat" and _RESEARCH_INTENT.search(text):
        return Router(route="agent", reason="You asked to research or look this up, so it goes to Deep research.")
    return decision


def apply_sheet_intent(decision: Router, text: str, has_sheets: bool) -> Router:
    """Calculations over the user's spreadsheets need the agent's SQL tool: document search can't add up."""
    if has_sheets and decision.route != "agent" and CALC_INTENT.search(text) and mentions_sheets(text):
        return Router(route="agent", reason="Needs calculations over your spreadsheets.")
    return decision


async def _plain_route(system: str, prompt: str, config: RunnableConfig) -> Router:
    """Second try for models whose structured output fails now and then: ask for one word."""
    response = await get_llm("router").ainvoke(
        [SystemMessage(content=system + "\n\nAnswer with exactly one word: chat, rag or agent."), HumanMessage(content=prompt)],
        config=config,
    )
    content = response.content if isinstance(response.content, str) else str(response.content)
    match = _ROUTE_WORD.search(content)
    if not match:
        raise ValueError(f"no route in router reply: {content[:80]!r}")
    return Router(route=match.group(1).lower(), reason="Chosen by the router model (plain-text answer).")


async def router_node(state: Chatbot, config: RunnableConfig) -> dict:
    if state.mode == "deep_research":
        # The user switched Deep research on: no need to ask the router model.
        reason = "Deep research is switched on for this message."
        emit({"type": "route", "route": "agent", "label": ROUTE_LABELS["agent"], "reason": reason})
        step("route", f"Routed to {ROUTE_LABELS['agent']}", reason)
        return {"route": "agent"}

    with ExecutionTimer("router_node", logger_instance=logger):
        question = latest_user_text(state.messages)
        kb = get_knowledge_base()
        documents = await kb.document_names()
        kb_available = bool(documents)
        tool_names = [t.name for t in get_agent_tools(include_kb=kb_available)]

        history = conversational(state.messages[:-1], int(config_section("memory").get("context_messages", 12)))[-6:]
        prompt = (
            (f"Conversation summary:\n{state.summary}\n\n" if state.summary else "")
            + (f"Recent conversation:\n{transcript(history, 600)}\n\n" if history else "")
            + f"Latest user message:\n{question}"
        )

        system = build_router_prompt(documents, tool_names, agent_capabilities())
        quiet = {**config, "tags": [*config.get("tags", []), "nostream"]}
        try:
            structured = get_llm("router").with_structured_output(Router)
            decision = await structured.ainvoke([SystemMessage(content=system), HumanMessage(content=prompt)], config=quiet)
            if not isinstance(decision, Router):
                decision = Router.model_validate(decision)
        except LLMConfigError:
            raise
        except Exception as exc:
            # Small/free models fail structured output now and then (bad JSON, a 429).
            # Before this fallback existed, every failure went straight to keyword routing.
            logger.warning("Router structured output failed (%s: %s); asking for a plain answer", type(exc).__name__, exc)
            try:
                decision = await _plain_route(system, prompt, quiet)
            except LLMConfigError:
                raise
            except Exception as exc2:
                logger.warning("Router model failed again (%s: %s); using keyword routing", type(exc2).__name__, exc2)
                fallback = heuristic_route(question, kb_available)
                decision = Router(route=fallback.route, reason=f"Router model unavailable; keyword match: {fallback.reason}")

        decision = apply_research_intent(decision, question)
        decision = apply_sheet_intent(decision, question, sheets_available())
        route = decision.route
        reason = decision.reason
        if route == "rag" and not kb_available:
            route, reason = "chat", "The knowledge base is empty, so answering directly."

        logger.info("Route decision", extra={"route": route, "reason": reason})
        emit({"type": "route", "route": route, "label": ROUTE_LABELS[route], "reason": reason})
        step("route", f"Routed to {ROUTE_LABELS[route]}", reason)
        return {"route": route}
