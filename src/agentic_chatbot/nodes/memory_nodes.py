"""
Long-term memory blocks.

* ``recall``   runs first in every turn: loads what is known about the user from
               the LangGraph store and puts it in state for the prompts.
* ``remember`` runs after the answer: asks the model which durable facts the
               user just shared (or asked to forget) and writes the changes to
               the store. Skipped cheaply when the message says nothing about
               the user, so most turns cost no extra model call.

The store is Postgres-backed when DB_URI is reachable (see components/memory.py),
so memories survive restarts and are shared by all conversations.
"""

from __future__ import annotations

import logging
import re

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.base import BaseStore
from pydantic import BaseModel, Field

from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.exception.exception import LLMConfigError
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.nodes.events import step
from agentic_chatbot.prompts.memory_prompt import MEMORY_PROMPT
from agentic_chatbot.services.long_term_memory import (
    add_memory,
    delete_memory,
    format_memories,
    get_memory_store,
    list_memories,
    long_term_enabled,
    update_memory,
    user_id_from,
)
from agentic_chatbot.utils.message_builder import latest_user_text, message_text
from agentic_chatbot.utils.structured import structured_invoke

logger = logging.getLogger(__name__)

# Placeholders, not sample facts: a small model may copy a realistic example into memory.
MEMORY_EXAMPLE = (
    '{"add": ["<new fact about the user>"], "update": [{"id": "<existing id>", "content": "<corrected fact>"}], '
    '"delete": ["<id to remove>"]}\nUse empty lists for anything that doesn\'t change, e.g. {"add": [], "update": [], "delete": []}'
)

# Messages where the user says something about themselves, or asks to remember/forget.
WORTH_REMEMBERING = re.compile(
    r"\b(i am|i'm|im|i've|i work|i live|i use|i prefer|i like|i love|i hate|i enjoy|i want|i need|i study|"
    r"i (?:don'?t|do not|never|always) \w+|i'?m (?:working|building|learning|based|from)|"
    r"my (?:name|job|role|title|team|company|employer|project|goal|stack|favou?rite|wife|husband|partner|"
    r"son|daughter|kids?|dog|cat|city|country|time ?zone|email)|call me|remember|forget|from now on|prefer)\b",
    re.I,
)
_EXPLICIT = re.compile(r"\bremember (?:that )?(.{3,240})", re.I)


class MemoryEdit(BaseModel):
    id: str = Field(description="Id of the existing memory")
    content: str = Field(description="The corrected memory sentence")


class MemoryOps(BaseModel):
    """Changes to make to the user's long-term memory."""

    add: list[str] = Field(default_factory=list, description="New memories, one short sentence each")
    update: list[MemoryEdit] = Field(default_factory=list, description="Existing memories to rewrite")
    delete: list[str] = Field(default_factory=list, description="Ids of memories to remove")


def _store() -> BaseStore | None:
    try:
        from langgraph.config import get_store

        store = get_store()
        if store is not None:
            return store
    except Exception:  # not inside a graph run, or compiled without a store
        pass
    return get_memory_store()


async def recall(state: Chatbot, config: RunnableConfig) -> dict:
    """Load the user's long-term memories into state for this turn's prompts."""
    if not long_term_enabled():
        return {"user_memories": None}
    store = _store()
    if store is None:
        return {"user_memories": None}
    limit = int(config_section("memory").get("recall_limit", 40))
    try:
        memories = await list_memories(store, user_id_from(config), limit=limit)
    except Exception as exc:  # memory must never block an answer
        logger.warning("Couldn't load long-term memory: %s", exc)
        return {"user_memories": None}
    # Recall is silent: memories shape the answer without a "Recalled N memories" stop in the timeline.
    return {"user_memories": format_memories(memories) or None}


def _last_answer(state: Chatbot) -> str:
    for m in reversed(state.messages):
        if isinstance(m, AIMessage) and not m.tool_calls:
            return message_text(m.content)
    return ""


async def _extract(user: str, answer: str, existing: list[dict], config: RunnableConfig) -> MemoryOps:
    prompt = MEMORY_PROMPT.format(
        existing=format_memories(existing, with_ids=True) or "(none yet)",
        user=user[:4000],
        assistant=answer[:1500],
    )
    try:
        return await structured_invoke(MemoryOps, prompt, MEMORY_EXAMPLE, config=config)
    except LLMConfigError:
        raise
    except Exception as exc:
        # Small models fail structured output now and then. Still honour an explicit "remember that …".
        logger.warning("Memory extraction failed (%s: %s)", type(exc).__name__, exc)
        match = _EXPLICIT.search(user)
        return MemoryOps(add=[f'Asked to remember: "{match.group(1).strip().rstrip(".")}"']) if match else MemoryOps()


async def remember(state: Chatbot, config: RunnableConfig) -> dict:
    """Write durable facts from the latest exchange to long-term memory."""
    if not long_term_enabled():
        return {}
    store = _store()
    user_text = latest_user_text(state.messages)
    if store is None or not user_text or not WORTH_REMEMBERING.search(user_text):
        return {}

    with ExecutionTimer("remember", logger_instance=logger):
        user_id = user_id_from(config)
        thread = (config.get("configurable") or {}).get("thread_id")
        step_id = "memory-save"
        try:
            existing = await list_memories(store, user_id)
            ops = await _extract(user_text, _last_answer(state), existing, config)
            known = {m["id"]: m for m in existing}
            changes: list[str] = []
            for memory_id in ops.delete:
                if memory_id in known and await delete_memory(store, user_id, memory_id):
                    changes.append(f"Forgot: {known[memory_id]['content']}")
            for edit in ops.update:
                if edit.id in known and edit.id not in ops.delete:
                    saved = await update_memory(store, user_id, edit.id, edit.content)
                    if saved:
                        changes.append(f"Updated: {saved['content']}")
            for text in ops.add:
                saved = await add_memory(store, user_id, text, source=thread)
                if saved:
                    changes.append(f"Saved: {saved['content']}")
        except LLMConfigError:
            return {}
        except Exception as exc:
            logger.warning("Couldn't update long-term memory: %s", exc)
            return {}

        if changes:
            logger.info("Long-term memory updated (%d change(s))", len(changes))
            step("memory", "Updated long-term memory", "\n".join(changes), step_id=step_id,
                 result=f"{len(changes)} change{'s' if len(changes) != 1 else ''}")
        return {}
