"""
Vector store factory.

* With ``VECTOR_DB_URI`` (or ``DB_URI``) set and Postgres reachable: PGVector
  (persistent).
* Without a database, or in development when the database isn't reachable:
  an in-memory store, so the app keeps working. Documents are lost on restart;
  a warning explains how to fix it. In production an unreachable database is an
  error instead.

``get_vector_store()`` may open a database connection: call it from a worker
thread (``asyncio.to_thread``) in async code so it never blocks the event loop.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from agentic_chatbot.components.embedding_loader import get_embeddings
from agentic_chatbot.core.db import check_postgres, unreachable_hint
from agentic_chatbot.core.settings import config_section, get_settings, sqlalchemy_uri
from agentic_chatbot.exception.exception import VectorStoreException

logger = logging.getLogger(__name__)

_backend: str | None = None  # set once the store has been created


def vector_backend() -> str:
    """'pgvector' or 'memory' (what /api/meta and the UI report)."""
    if _backend is not None:
        return _backend
    uri = get_settings().effective_vector_db_uri
    if not uri:
        return "memory"
    if get_settings().is_production:
        return "pgvector"
    return "pgvector" if check_postgres(uri) is None else "memory"


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    global _backend
    embeddings = get_embeddings()
    settings = get_settings()
    uri = settings.effective_vector_db_uri
    if not uri:
        logger.warning("No VECTOR_DB_URI/DB_URI set: using an in-memory vector store (not persistent)")
        _backend = "memory"
        return InMemoryVectorStore(embedding=embeddings)

    reason = check_postgres(uri)
    if reason:
        if settings.is_production:
            raise VectorStoreException(
                f"Vector database unreachable: {reason}",
                public_message="The vector database isn't reachable. Check VECTOR_DB_URI / DB_URI.",
            )
        logger.warning("%s Documents are kept in memory for now.", unreachable_hint(uri, reason))
        _backend = "memory"
        return InMemoryVectorStore(embedding=embeddings)

    try:
        from langchain_postgres import PGVector

        store = PGVector(
            embeddings=embeddings,
            collection_name=str(config_section("rag").get("collection", "chatbot_docs")),
            connection=sqlalchemy_uri(uri),
            use_jsonb=True,
            engine_args={"connect_args": {"connect_timeout": 5}, "pool_pre_ping": True},
        )
        logger.info("PGVector store ready")
        _backend = "pgvector"
        return store
    except Exception as exc:  # pragma: no cover - needs a database
        raise VectorStoreException(
            f"Failed to initialise PGVector: {exc}",
            public_message="Could not set up the vector database. Check VECTOR_DB_URI and that the pgvector extension is installed.",
        ) from exc


def reset_vector_store() -> None:
    global _backend
    _backend = None
    get_vector_store.cache_clear()


class VectorStoreLoader:
    """Backwards-compatible wrapper."""

    def load_vectorstore(self) -> VectorStore:
        return get_vector_store()
