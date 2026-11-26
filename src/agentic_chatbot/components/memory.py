"""
Memory backends.

* Short-term memory: the LangGraph checkpointer, one history per conversation thread.
* Long-term memory: the LangGraph store, facts about the user shared by every thread.

Both use Postgres when DB_URI is set and reachable (one connection pool for the
two), and fall back to in-memory versions in development otherwise.
"""

from __future__ import annotations

import asyncio
import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from agentic_chatbot.core.db import check_postgres, describe_target
from agentic_chatbot.core.settings import get_settings, pg_conninfo

logger = logging.getLogger(__name__)


class MemoryLoader:
    def __init__(self) -> None:
        self._pool = None
        self.backend = "memory"        # checkpointer (short-term)
        self.store_backend = "memory"  # store (long-term)

    async def load_memory(self) -> BaseCheckpointSaver:
        settings = get_settings()
        if not settings.db_uri:
            logger.warning("DB_URI not set: conversation memory is in-process only and resets on restart")
            return InMemorySaver()

        if settings.is_production:
            return await self._postgres(settings.db_uri, settings.db_pool_size)

        # Development: skip Postgres straight away when the shared startup probe failed.
        if await asyncio.to_thread(check_postgres, settings.db_uri):
            logger.warning(
                "Conversation memory is in-process only until Postgres at %s is reachable",
                describe_target(settings.db_uri),
            )
            return InMemorySaver()
        try:
            return await self._postgres(settings.db_uri, settings.db_pool_size)
        except Exception as exc:
            logger.error("Postgres checkpointer unavailable (%s); falling back to in-memory", exc)
            return InMemorySaver()

    async def load_store(self) -> BaseStore:
        """Long-term memory store. Call after ``load_memory`` so it can share the Postgres pool."""
        if self._pool is not None:
            from langgraph.store.postgres.aio import AsyncPostgresStore

            try:
                store = AsyncPostgresStore(self._pool)  # type: ignore[arg-type]
                await store.setup()  # creates the store tables on first run
                self.store_backend = "postgres"
                logger.info("Using Postgres for long-term memory")
                return store
            except Exception as exc:
                if get_settings().is_production:
                    raise
                logger.error("Postgres store unavailable (%s); long-term memory is in-process only", exc)
        elif get_settings().db_uri:
            logger.warning("Long-term memory is in-process only until Postgres is reachable")
        self.store_backend = "memory"
        return InMemoryStore()

    async def _postgres(self, uri: str, size: int) -> BaseCheckpointSaver:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=pg_conninfo(uri),
            max_size=size,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row, "connect_timeout": 5},
            open=False,
        )
        try:
            await pool.open(wait=True, timeout=15)
            saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
            await saver.setup()
        except Exception:
            # Stop the pool's background reconnect workers instead of leaking them.
            await pool.close(timeout=1)
            raise
        self._pool = pool
        self.backend = "postgres"
        logger.info("Using Postgres checkpointer")
        return saver

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
