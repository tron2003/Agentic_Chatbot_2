"""LangGraph checkpointer: Postgres when DB_URI is set, in-memory otherwise."""

from __future__ import annotations

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver

from agentic_chatbot.core.settings import get_settings, pg_conninfo

logger = logging.getLogger(__name__)


class MemoryLoader:
    def __init__(self) -> None:
        self._pool = None
        self.backend = "memory"

    async def load_memory(self) -> BaseCheckpointSaver:
        settings = get_settings()
        if not settings.db_uri:
            logger.warning("DB_URI not set: conversation memory is in-process only and resets on restart")
            return InMemorySaver()

        if settings.is_production:
            return await self._postgres(settings.db_uri, settings.db_pool_size)
        try:
            return await self._postgres(settings.db_uri, settings.db_pool_size)
        except Exception as exc:
            # In development, keep going without Postgres; in production fail loudly.
            logger.error("Postgres checkpointer unavailable (%s); falling back to in-memory", exc)
            return InMemorySaver()

    async def _postgres(self, uri: str, size: int) -> BaseCheckpointSaver:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            conninfo=pg_conninfo(uri),
            max_size=size,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
            open=False,
        )
        await pool.open(wait=True, timeout=15)
        self._pool = pool
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        self.backend = "postgres"
        logger.info("Using Postgres checkpointer")
        return saver

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
