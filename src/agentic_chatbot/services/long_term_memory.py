"""
Long-term memory: facts about the user that outlive a single conversation.

Stored in the LangGraph store under the namespace ``("memories", <user_id>)``,
one item per fact. With Postgres the store is the ``store`` table that
``AsyncPostgresStore.setup()`` creates, so memories survive restarts and are
shared by every conversation. The graph reads them in the recall block and
writes them in the remember block (``nodes/memory_nodes.py``); the API in
``api/routes/memory.py`` lets the user see, add and delete them.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.store.base import BaseStore

from agentic_chatbot.core.flags import as_flag
from agentic_chatbot.core.settings import config_section

NAMESPACE = "memories"
MAX_CHARS = 300

_store: BaseStore | None = None
_backend = "memory"

# Never keep secrets, even if a model suggests it: keys, passwords, card and account numbers.
_SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{8,}|api[_ -]?key|secret key|(?:access|auth|bearer) token|password|passwd|pass ?code|\bpin\b"
    r"|\b\d(?:[ -]?\d){11,18}\b)",
    re.I,
)


def set_memory_store(store: BaseStore | None, backend: str = "memory") -> None:
    global _store, _backend
    _store, _backend = store, backend


def get_memory_store() -> BaseStore | None:
    return _store


def memory_backend() -> str:
    return _backend if _store is not None else "off"


def long_term_enabled() -> bool:
    return as_flag(config_section("memory").get("long_term"), default=True)


def default_user_id() -> str:
    return str(config_section("memory").get("user_id") or "local")


def user_id_from(config: dict | None) -> str:
    configurable = (config or {}).get("configurable") or {}
    return str(configurable.get("user_id") or default_user_id())


def namespace(user_id: str) -> tuple[str, str]:
    return (NAMESPACE, user_id)


def clean_memory(text: str) -> str | None:
    """Normalise a memory sentence; None when it's empty or looks like a secret."""
    text = " ".join(str(text or "").split()).strip(" -•*")
    if not text or len(text) < 3 or _SECRET.search(text):
        return None
    return text[:MAX_CHARS]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _to_dict(item: Any) -> dict[str, Any]:
    value = item.value or {}
    return {
        "id": item.key,
        "content": value.get("content", ""),
        "category": value.get("category", "fact"),
        "source": value.get("source"),
        "created_at": value.get("created_at") or (item.created_at.isoformat() if item.created_at else None),
        "updated_at": value.get("updated_at") or (item.updated_at.isoformat() if item.updated_at else None),
    }


async def list_memories(store: BaseStore, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    """Newest first."""
    cap = int(config_section("memory").get("max_memories", 200))
    items = await store.asearch(namespace(user_id), limit=max(limit or cap, 1) + 50)
    memories = [_to_dict(i) for i in items]
    memories.sort(key=lambda m: m.get("updated_at") or "", reverse=True)
    return memories[:limit] if limit else memories


async def add_memory(store: BaseStore, user_id: str, content: str, *, category: str = "fact",
                     source: str | None = None) -> dict[str, Any] | None:
    text = clean_memory(content)
    if not text:
        return None
    existing = await list_memories(store, user_id)
    for m in existing:  # same fact already stored: refresh it instead of duplicating
        if m["content"].casefold() == text.casefold():
            return await update_memory(store, user_id, m["id"], text) or m
    key = uuid.uuid4().hex[:12]
    now = _now()
    value = {"content": text, "category": category, "source": source, "created_at": now, "updated_at": now}
    await store.aput(namespace(user_id), key, value)
    await prune(store, user_id)
    return {"id": key, **value}


async def update_memory(store: BaseStore, user_id: str, memory_id: str, content: str) -> dict[str, Any] | None:
    text = clean_memory(content)
    item = await store.aget(namespace(user_id), memory_id)
    if not text or item is None:
        return None
    value = {**(item.value or {}), "content": text, "updated_at": _now()}
    await store.aput(namespace(user_id), memory_id, value)
    return {"id": memory_id, **value}


async def delete_memory(store: BaseStore, user_id: str, memory_id: str) -> bool:
    if await store.aget(namespace(user_id), memory_id) is None:
        return False
    await store.adelete(namespace(user_id), memory_id)
    return True


async def clear_memories(store: BaseStore, user_id: str) -> int:
    memories = await list_memories(store, user_id)
    for m in memories:
        await store.adelete(namespace(user_id), m["id"])
    return len(memories)


async def prune(store: BaseStore, user_id: str) -> int:
    cap = int(config_section("memory").get("max_memories", 200))
    memories = await list_memories(store, user_id)
    extra = memories[cap:]
    for m in extra:
        await store.adelete(namespace(user_id), m["id"])
    return len(extra)


def format_memories(memories: list[dict[str, Any]], *, with_ids: bool = False) -> str:
    if not memories:
        return ""
    if with_ids:
        return "\n".join(f"[{m['id']}] {m['content']}" for m in memories)
    return "\n".join(f"- {m['content']}" for m in memories)
