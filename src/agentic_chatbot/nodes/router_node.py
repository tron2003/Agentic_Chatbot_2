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
from agentic_chatbot.tools.mcp_tools import get_agent_tools
from agentic_chatbot.utils.message_builder import conversational, latest_user_text, transcript

logger = logging.getLogger(__name__)

_AGENT_HINT = re.compile(
    r"\b(today|tonight|latest|news|current(ly)?|right now|price|stock|score|weather|release[sd]?|"
    r"this (week|month|year)|who (is|won)|search|look up|calculate|compute|20[2-3]\d)\b|\d+\s*[-+*/^]\s*\d+",
    re.I,
)
_DOC_HINT = re.compile(r"\b(document|docs|pdf|paper|report|file|uploaded|my notes|knowledge base)\b", re.I)

ROUTE_LABELS = {"chat": "Chat", "rag": "Documents", "agent": "Research"}


def heuristic_route(text: str, kb_available: bool) -> Router:
    """Used when the model can't produce a structured routing decision."""
    if kb_available and _DOC_HINT.search(text):
        return Router(route="rag", reason="Mentions the user's documents.")
    if _AGENT_HINT.search(text):
        return Router(route="agent", reason="Looks time-sensitive or needs a tool.")
    return Router(route="chat", reason="General conversation.")


async def router_node(state: Chatbot, config: RunnableConfig) -> dict:
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

        try:
            structured = get_llm("router").with_structured_output(Router)
            decision = await structured.ainvoke(
                [SystemMessage(content=build_router_prompt(documents, tool_names, agent_capabilities())), HumanMessage(content=prompt)],
                config={**config, "tags": [*config.get("tags", []), "nostream"]},
            )
            if not isinstance(decision, Router):
                decision = Router.model_validate(decision)
        except LLMConfigError:
            raise
        except Exception as exc:
            logger.warning("Router model failed (%s); using heuristic routing", exc)
            decision = heuristic_route(question, kb_available)

        route = decision.route
        reason = decision.reason
        if route == "rag" and not kb_available:
            route, reason = "chat", "The knowledge base is empty, so answering directly."

        logger.info("Route decision", extra={"route": route, "reason": reason})
        emit({"type": "route", "route": route, "label": ROUTE_LABELS[route], "reason": reason})
        step("route", f"Routed to {ROUTE_LABELS[route]}", reason)
        return {"route": route}
