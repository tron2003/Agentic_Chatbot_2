"""
Persistence for what the UI shows: conversations, their messages, and the
knowledge-base document registry.

LangGraph's checkpointer stores what the *model* remembers (including
summaries and trimmed history). This store keeps the full, user-facing
transcript plus metadata (route, sources, reasoning steps) for the sidebar.

``PostgresStore`` is used when DB_URI is set; ``MemoryStore`` otherwise.
Table names are prefixed ``chatbot_`` so they never collide with the old
``chat_history`` table or tables created by an earlier init.sql.
"""

from __future__ import annotations

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from agentic_chatbot.core.db import check_postgres, unreachable_hint
from agentic_chatbot.core.settings import get_settings, pg_conninfo
from agentic_chatbot.exception.exception import DatabaseException

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


class ChatStore(ABC):
    backend = "abstract"

    async def init(self) -> None: ...
    async def close(self) -> None: ...
    async def ping(self) -> bool:
        return True

    # conversations
    @abstractmethod
    async def create_conversation(self, conversation_id: str, title: str) -> dict: ...
    @abstractmethod
    async def get_conversation(self, conversation_id: str) -> dict | None: ...
    @abstractmethod
    async def list_conversations(self, query: str | None = None, limit: int = 100) -> list[dict]: ...
    @abstractmethod
    async def rename_conversation(self, conversation_id: str, title: str) -> bool: ...
    @abstractmethod
    async def delete_conversation(self, conversation_id: str) -> bool: ...
    @abstractmethod
    async def delete_all_conversations(self) -> int: ...
    @abstractmethod
    async def get_messages(self, conversation_id: str) -> list[dict]: ...
    @abstractmethod
    async def add_message(self, conversation_id: str, message_id: str, role: str, content: str, metadata: dict | None = None) -> dict: ...
    @abstractmethod
    async def delete_last_assistant(self, conversation_id: str) -> None: ...
    @abstractmethod
    async def stats(self) -> dict: ...

    # knowledge base registry
    @abstractmethod
    async def add_document(self, doc: dict) -> None: ...
    @abstractmethod
    async def list_documents(self) -> list[dict]: ...
    @abstractmethod
    async def get_document(self, doc_id: str) -> dict | None: ...
    @abstractmethod
    async def delete_document(self, doc_id: str) -> bool: ...
    @abstractmethod
    async def delete_all_documents(self) -> int: ...


# ─── In-memory ──────────────────────────────────────────────────────────────


class MemoryStore(ChatStore):
    backend = "memory"

    def __init__(self) -> None:
        self._convs: dict[str, dict] = {}
        self._msgs: dict[str, list[dict]] = {}
        self._docs: dict[str, dict] = {}
        self._lock = asyncio.Lock()

    async def create_conversation(self, conversation_id: str, title: str) -> dict:
        async with self._lock:
            if conversation_id not in self._convs:
                now = utcnow()
                self._convs[conversation_id] = {"id": conversation_id, "title": title, "created_at": now, "updated_at": now}
                self._msgs[conversation_id] = []
            return self._public(self._convs[conversation_id])

    def _public(self, conv: dict) -> dict:
        msgs = self._msgs.get(conv["id"], [])
        last = next((m for m in reversed(msgs) if m["role"] == "assistant"), None)
        return {
            "id": conv["id"],
            "title": conv["title"],
            "created_at": _iso(conv["created_at"]),
            "updated_at": _iso(conv["updated_at"]),
            "message_count": len(msgs),
            "last_route": (last or {}).get("metadata", {}).get("route"),
        }

    async def get_conversation(self, conversation_id: str) -> dict | None:
        conv = self._convs.get(conversation_id)
        return self._public(conv) if conv else None

    async def list_conversations(self, query: str | None = None, limit: int = 100) -> list[dict]:
        convs = sorted(self._convs.values(), key=lambda c: c["updated_at"], reverse=True)
        if query:
            q = query.lower()
            convs = [
                c for c in convs
                if q in c["title"].lower() or any(q in m["content"].lower() for m in self._msgs.get(c["id"], []))
            ]
        return [self._public(c) for c in convs[:limit]]

    async def rename_conversation(self, conversation_id: str, title: str) -> bool:
        conv = self._convs.get(conversation_id)
        if not conv:
            return False
        conv["title"] = title
        conv["updated_at"] = utcnow()
        return True

    async def delete_conversation(self, conversation_id: str) -> bool:
        existed = self._convs.pop(conversation_id, None) is not None
        self._msgs.pop(conversation_id, None)
        return existed

    async def delete_all_conversations(self) -> int:
        n = len(self._convs)
        self._convs.clear()
        self._msgs.clear()
        return n

    async def get_messages(self, conversation_id: str) -> list[dict]:
        return deepcopy(self._msgs.get(conversation_id, []))

    async def add_message(self, conversation_id: str, message_id: str, role: str, content: str, metadata: dict | None = None) -> dict:
        """Insert, or update content and metadata when the ID exists (like the Postgres upsert)."""
        async with self._lock:
            msgs = self._msgs.setdefault(conversation_id, [])
            existing = next((m for m in msgs if m["id"] == message_id), None)
            if existing:
                existing.update(content=content, metadata=metadata or {})
                if conversation_id in self._convs:
                    self._convs[conversation_id]["updated_at"] = utcnow()
                return deepcopy(existing)
            msg = {
                "id": message_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "metadata": metadata or {},
                "created_at": _iso(utcnow()),
            }
            msgs.append(msg)
            if conversation_id in self._convs:
                self._convs[conversation_id]["updated_at"] = utcnow()
            return deepcopy(msg)

    async def delete_last_assistant(self, conversation_id: str) -> None:
        msgs = self._msgs.get(conversation_id, [])
        if msgs and msgs[-1]["role"] == "assistant":
            msgs.pop()

    async def stats(self) -> dict:
        total = sum(len(v) for v in self._msgs.values())
        return {"conversations": len(self._convs), "messages": total, "documents": len(self._docs)}

    async def add_document(self, doc: dict) -> None:
        self._docs[doc["id"]] = {**doc, "created_at": _iso(doc.get("created_at") or utcnow())}

    async def list_documents(self) -> list[dict]:
        return sorted(deepcopy(list(self._docs.values())), key=lambda d: d["created_at"], reverse=True)

    async def get_document(self, doc_id: str) -> dict | None:
        doc = self._docs.get(doc_id)
        return deepcopy(doc) if doc else None

    async def delete_document(self, doc_id: str) -> bool:
        return self._docs.pop(doc_id, None) is not None

    async def delete_all_documents(self) -> int:
        n = len(self._docs)
        self._docs.clear()
        return n


# ─── Postgres ───────────────────────────────────────────────────────────────

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS chatbot_conversations (
        id          TEXT PRIMARY KEY,
        title       TEXT NOT NULL DEFAULT 'New chat',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """
    CREATE TABLE IF NOT EXISTS chatbot_messages (
        id               TEXT PRIMARY KEY,
        conversation_id  TEXT NOT NULL REFERENCES chatbot_conversations(id) ON DELETE CASCADE,
        role             TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        content          TEXT NOT NULL,
        metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_chatbot_messages_conv ON chatbot_messages (conversation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_chatbot_conversations_updated ON chatbot_conversations (updated_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS chatbot_documents (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        file_type   TEXT NOT NULL,
        size_bytes  BIGINT NOT NULL DEFAULT 0,
        chunks      INTEGER NOT NULL DEFAULT 0,
        chunk_ids   JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
]


class PostgresStore(ChatStore):
    backend = "postgres"

    def __init__(self, uri: str, pool_size: int = 5) -> None:
        self._uri = pg_conninfo(uri)
        self._pool_size = pool_size
        self._pool = None

    async def init(self) -> None:
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        try:
            self._pool = AsyncConnectionPool(
                conninfo=self._uri,
                max_size=self._pool_size,
                kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row, "connect_timeout": 5},
                open=False,
            )
            await self._pool.open(wait=True, timeout=15)
            async with self._pool.connection() as conn:
                for stmt in _SCHEMA:
                    await conn.execute(stmt)
            logger.info("Postgres chat store ready")
        except Exception as exc:
            # Stop the pool's background reconnect workers instead of leaking them.
            if self._pool is not None:
                await self._pool.close(timeout=1)
                self._pool = None
            raise DatabaseException(f"Could not initialise chat store: {exc}") from exc

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()

    async def ping(self) -> bool:
        try:
            async with self._pool.connection() as conn:  # type: ignore[union-attr]
                await conn.execute("SELECT 1")
            return True
        except Exception:
            return False

    async def _fetch(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            async with self._pool.connection() as conn:  # type: ignore[union-attr]
                cur = await conn.execute(sql, params)
                return await cur.fetchall() if cur.description else []
        except Exception as exc:
            raise DatabaseException(f"Query failed: {exc}") from exc

    @staticmethod
    def _conv(row: dict) -> dict:
        return {
            "id": row["id"],
            "title": row["title"],
            "created_at": _iso(row["created_at"]),
            "updated_at": _iso(row["updated_at"]),
            "message_count": int(row.get("message_count") or 0),
            "last_route": row.get("last_route"),
        }

    async def create_conversation(self, conversation_id: str, title: str) -> dict:
        await self._fetch(
            "INSERT INTO chatbot_conversations (id, title) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
            (conversation_id, title),
        )
        conv = await self.get_conversation(conversation_id)
        assert conv is not None
        return conv

    async def get_conversation(self, conversation_id: str) -> dict | None:
        rows = await self._fetch(
            """SELECT c.*, (SELECT COUNT(*) FROM chatbot_messages m WHERE m.conversation_id = c.id) AS message_count,
                      (SELECT m.metadata->>'route' FROM chatbot_messages m WHERE m.conversation_id = c.id
                       AND m.role = 'assistant' ORDER BY m.created_at DESC LIMIT 1) AS last_route
               FROM chatbot_conversations c WHERE c.id = %s""",
            (conversation_id,),
        )
        return self._conv(rows[0]) if rows else None

    async def list_conversations(self, query: str | None = None, limit: int = 100) -> list[dict]:
        if query:
            like = f"%{query}%"
            rows = await self._fetch(
                """SELECT c.*, (SELECT COUNT(*) FROM chatbot_messages m WHERE m.conversation_id = c.id) AS message_count,
                      (SELECT m.metadata->>'route' FROM chatbot_messages m WHERE m.conversation_id = c.id
                       AND m.role = 'assistant' ORDER BY m.created_at DESC LIMIT 1) AS last_route
                   FROM chatbot_conversations c
                   WHERE c.title ILIKE %s OR EXISTS (
                       SELECT 1 FROM chatbot_messages m WHERE m.conversation_id = c.id AND m.content ILIKE %s)
                   ORDER BY c.updated_at DESC LIMIT %s""",
                (like, like, limit),
            )
        else:
            rows = await self._fetch(
                """SELECT c.*, (SELECT COUNT(*) FROM chatbot_messages m WHERE m.conversation_id = c.id) AS message_count,
                      (SELECT m.metadata->>'route' FROM chatbot_messages m WHERE m.conversation_id = c.id
                       AND m.role = 'assistant' ORDER BY m.created_at DESC LIMIT 1) AS last_route
                   FROM chatbot_conversations c ORDER BY c.updated_at DESC LIMIT %s""",
                (limit,),
            )
        return [self._conv(r) for r in rows]

    async def rename_conversation(self, conversation_id: str, title: str) -> bool:
        rows = await self._fetch(
            "UPDATE chatbot_conversations SET title = %s, updated_at = NOW() WHERE id = %s RETURNING id",
            (title, conversation_id),
        )
        return bool(rows)

    async def delete_conversation(self, conversation_id: str) -> bool:
        rows = await self._fetch("DELETE FROM chatbot_conversations WHERE id = %s RETURNING id", (conversation_id,))
        return bool(rows)

    async def delete_all_conversations(self) -> int:
        rows = await self._fetch("DELETE FROM chatbot_conversations RETURNING id")
        return len(rows)

    async def get_messages(self, conversation_id: str) -> list[dict]:
        rows = await self._fetch(
            "SELECT * FROM chatbot_messages WHERE conversation_id = %s ORDER BY created_at ASC",
            (conversation_id,),
        )
        return [{**r, "created_at": _iso(r["created_at"]), "metadata": r.get("metadata") or {}} for r in rows]

    async def add_message(self, conversation_id: str, message_id: str, role: str, content: str, metadata: dict | None = None) -> dict:
        rows = await self._fetch(
            """INSERT INTO chatbot_messages (id, conversation_id, role, content, metadata)
               VALUES (%s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata
               RETURNING *""",
            (message_id, conversation_id, role, content, json.dumps(metadata or {})),
        )
        await self._fetch("UPDATE chatbot_conversations SET updated_at = NOW() WHERE id = %s", (conversation_id,))
        row = rows[0]
        return {**row, "created_at": _iso(row["created_at"])}

    async def delete_last_assistant(self, conversation_id: str) -> None:
        await self._fetch(
            """DELETE FROM chatbot_messages WHERE id = (
                   SELECT id FROM chatbot_messages WHERE conversation_id = %s
                   ORDER BY created_at DESC LIMIT 1)
               AND role = 'assistant'""",
            (conversation_id,),
        )

    async def stats(self) -> dict:
        rows = await self._fetch(
            """SELECT (SELECT COUNT(*) FROM chatbot_conversations) AS conversations,
                      (SELECT COUNT(*) FROM chatbot_messages) AS messages,
                      (SELECT COUNT(*) FROM chatbot_documents) AS documents"""
        )
        return {k: int(v) for k, v in rows[0].items()}

    async def add_document(self, doc: dict) -> None:
        await self._fetch(
            """INSERT INTO chatbot_documents (id, name, file_type, size_bytes, chunks, chunk_ids)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb)""",
            (doc["id"], doc["name"], doc["file_type"], doc["size_bytes"], doc["chunks"], json.dumps(doc["chunk_ids"])),
        )

    async def list_documents(self) -> list[dict]:
        rows = await self._fetch("SELECT * FROM chatbot_documents ORDER BY created_at DESC")
        return [{**r, "created_at": _iso(r["created_at"])} for r in rows]

    async def get_document(self, doc_id: str) -> dict | None:
        rows = await self._fetch("SELECT * FROM chatbot_documents WHERE id = %s", (doc_id,))
        return {**rows[0], "created_at": _iso(rows[0]["created_at"])} if rows else None

    async def delete_document(self, doc_id: str) -> bool:
        rows = await self._fetch("DELETE FROM chatbot_documents WHERE id = %s RETURNING id", (doc_id,))
        return bool(rows)

    async def delete_all_documents(self) -> int:
        rows = await self._fetch("DELETE FROM chatbot_documents RETURNING id")
        return len(rows)


# ─── singleton ──────────────────────────────────────────────────────────────

_store: ChatStore | None = None


async def init_store() -> ChatStore:
    global _store
    settings = get_settings()
    if settings.db_uri:
        # One quick, shared reachability probe (cached) instead of a 15 s pool timeout per component.
        reason = await asyncio.to_thread(check_postgres, settings.db_uri)
        if reason and not settings.is_production:
            logger.warning("%s Chat history is kept in memory for now.", unreachable_hint(settings.db_uri, reason))
            _store = MemoryStore()
            return _store
        store: ChatStore = PostgresStore(settings.db_uri)
        try:
            await store.init()
        except DatabaseException as exc:
            if settings.is_production:
                raise
            logger.error("Postgres chat store unavailable (%s); using in-memory store", exc)
            store = MemoryStore()
    else:
        logger.warning("DB_URI not set: chat history is kept in memory and resets on restart")
        store = MemoryStore()
    _store = store
    return store


def get_store() -> ChatStore:
    global _store
    if _store is None:
        _store = MemoryStore()
    return _store


def set_store(store: ChatStore | None) -> None:
    global _store
    _store = store
