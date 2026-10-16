"""
Summariser: fold older messages into a running summary and drop them from state.

Fix from the previous version: it summarised the *recent* messages and then
deleted the *older* ones, so the deleted messages never reached the summary.
Now the messages being removed are exactly the ones summarised.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.prompts.summary_prompt import SUMMARY_PROMPT
from agentic_chatbot.utils.message_builder import message_text, strip_think, transcript

logger = logging.getLogger(__name__)


def _limits() -> tuple[int, int]:
    cfg = config_section("memory")
    return int(cfg.get("summary_threshold", 24)), int(cfg.get("keep_last_messages", 10))


def should_summarize(state: Chatbot) -> bool:
    threshold, _ = _limits()
    return len(state.messages) > threshold


def _split(messages: list) -> tuple[list, list]:
    """Return (to_summarise, to_keep); the kept window starts at a user message."""
    _, keep = _limits()
    cut = max(len(messages) - keep, 0)
    while cut < len(messages) and getattr(messages[cut], "type", "") != "human":
        cut += 1
    return messages[:cut], messages[cut:]


async def summarize_conversation(state: Chatbot, config: RunnableConfig) -> dict:
    with ExecutionTimer("summarize_conversation", logger_instance=logger):
        old, _ = _split(list(state.messages))
        if not old:
            return {}
        prompt = SUMMARY_PROMPT.format(existing=state.summary or "(none yet)", transcript=transcript(old))
        try:
            response = await get_llm("router").ainvoke(
                [HumanMessage(content=prompt)],
                config={**config, "tags": [*config.get("tags", []), "nostream"]},
            )
            summary = strip_think(message_text(response.content))
        except Exception as exc:
            # Never lose the answer because summarising failed; try again next turn.
            logger.warning("Summarisation failed: %s", exc)
            return {}
        logger.info("Summarised %d messages", len(old))
        return {"summary": summary, "messages": [RemoveMessage(id=m.id) for m in old if m.id]}
