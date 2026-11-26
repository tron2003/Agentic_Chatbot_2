"""Chat route: one model call with conversation memory. Tokens stream to the client."""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.prompts.prompt import build_chat_prompt
from agentic_chatbot.utils.message_builder import context_window, message_text, strip_think

logger = logging.getLogger(__name__)


async def chat_node(state: Chatbot, config: RunnableConfig) -> dict:
    with ExecutionTimer("chat_node", logger_instance=logger):
        messages = [SystemMessage(content=build_chat_prompt(state.summary, state.user_memories))]
        messages.extend(context_window(state.messages))
        response = await get_llm("main").ainvoke(messages, config=config)
        return {"messages": [AIMessage(content=strip_think(message_text(response.content)), id=response.id)]}
