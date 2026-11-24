"""
Quick Postgres reachability check, shared by the chat store, the LangGraph
checkpointer and the vector store.

One short probe (cached per URI) instead of a 15-second pool timeout for each
of them, plus one clear message when DB_URI points at a database that isn't
running. The probe is synchronous: call it with ``asyncio.to_thread`` from
async code.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlsplit

from agentic_chatbot.core.settings import pg_conninfo

CONNECT_TIMEOUT_SECONDS = 3


def describe_target(uri: str) -> str:
    """``host:port/db`` for messages, never the password."""
    try:
        parts = urlsplit(pg_conninfo(uri))
        return f"{parts.hostname or 'localhost'}:{parts.port or 5432}/{parts.path.lstrip('/') or 'postgres'}"
    except ValueError:
        return "the configured database"


@lru_cache(maxsize=8)
def check_postgres(uri: str) -> str | None:
    """None when Postgres answers, otherwise a one-line reason. Cached for the process lifetime."""
    try:
        import psycopg

        with psycopg.connect(pg_conninfo(uri), connect_timeout=CONNECT_TIMEOUT_SECONDS) as conn:
            conn.execute("SELECT 1")
        return None
    except Exception as exc:  # any failure means "not usable right now"
        text = str(exc).strip()
        return text.splitlines()[0] if text else type(exc).__name__


def unreachable_hint(uri: str, reason: str) -> str:
    return (
        f"Postgres isn't reachable at {describe_target(uri)} ({reason}). "
        "Start it (docker compose up -d db), fix DB_URI in .env, or remove DB_URI to use in-memory storage."
    )


def reset_postgres_check() -> None:
    check_postgres.cache_clear()
