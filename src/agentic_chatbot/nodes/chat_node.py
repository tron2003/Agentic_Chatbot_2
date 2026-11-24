"""Chat route: one model call with conversation memory. Tokens stream to the client."""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.prompts.prompt import build_chat_prompt
from agentic_chatbot.utils.message_builder import conversational, message_text, strip_think

logger = logging.getLogger(__name__)


async def chat_node(state: Chatbot, config: RunnableConfig) -> dict:
    with ExecutionTimer("chat_node", logger_instance=logger):
        limit = int(config_section("memory").get("context_messages", 12))
        messages = [SystemMessage(content=build_chat_prompt(state.summary))]
        messages.extend(conversational(state.messages, limit))
        response = await get_llm("main").ainvoke(messages, config=config)
        return {"messages": [AIMessage(content=strip_think(message_text(response.content)), id=response.id)]}
