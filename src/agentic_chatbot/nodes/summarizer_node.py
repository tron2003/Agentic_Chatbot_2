"""
Summarise block: keeps short-term memory inside the model's context window.

The checkpointer keeps every message of a thread, and each answer node sends
only the most recent ones that fit ``memory.context_tokens``. Without this
block, anything older than that window would simply be forgotten. Once a thread
holds more than ``memory.summary_trigger_tokens`` (or ``summary_threshold``
messages), the older messages are folded into a running summary and removed
from state; the summary goes into every prompt, so the model still knows what
was said earlier while the context stays small.

It runs after the answer has been sent, so it never delays the reply.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.nodes.events import step
from agentic_chatbot.prompts.summary_prompt import SUMMARY_PROMPT
from agentic_chatbot.utils.message_builder import count_tokens, message_text, strip_think, transcript

logger = logging.getLogger(__name__)


def _limits() -> tuple[int, int, int]:
    cfg = config_section("memory")
    return (
        int(cfg.get("summary_threshold", 24)),
        int(cfg.get("keep_last_messages", 6)),
        int(cfg.get("summary_trigger_tokens", 6000)),
    )


def should_summarize(state: Chatbot) -> bool:
    threshold, keep, trigger_tokens = _limits()
    messages = list(state.messages)
    if len(messages) <= max(keep, 2):
        return False
    return len(messages) > threshold or count_tokens(messages) > trigger_tokens


def _split(messages: list) -> tuple[list, list]:
    """Return (to_summarise, to_keep); the kept window starts at a user message."""
    _, keep, _ = _limits()
    cut = max(len(messages) - keep, 0)
    while cut < len(messages) and getattr(messages[cut], "type", "") != "human":
        cut += 1
    return messages[:cut], messages[cut:]


async def summarize_conversation(state: Chatbot, config: RunnableConfig) -> dict:
    with ExecutionTimer("summarize_conversation", logger_instance=logger):
        old, kept = _split(list(state.messages))
        if not old:
            return {}
        step_id = "memory-summary"
        before = count_tokens(list(state.messages))
        step("memory", "Summarising earlier messages", f"{len(old)} older messages, about {before:,} tokens in this chat",
             step_id=step_id, status="running")
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
            step("memory", "Couldn't summarise earlier messages", "Will try again after the next answer.",
                 step_id=step_id, status="error")
            return {}
        if not summary:
            step("memory", "Couldn't summarise earlier messages", "The model returned an empty summary.",
                 step_id=step_id, status="error")
            return {}
        after = count_tokens(kept)
        logger.info("Summarised %d messages (%d -> %d tokens kept verbatim)", len(old), before, after)
        step("memory", "Summarised earlier messages",
             f"Folded {len(old)} older messages into the running summary to stay within the context window.",
             step_id=step_id, result=f"About {before:,} tokens down to {after:,} plus a short summary")
        return {"summary": summary, "messages": [RemoveMessage(id=m.id) for m in old if m.id]}
