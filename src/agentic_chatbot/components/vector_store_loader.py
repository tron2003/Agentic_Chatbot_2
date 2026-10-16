"""
Vector store factory.

* With ``VECTOR_DB_URI`` (or ``DB_URI``) set: PGVector in Postgres (persistent).
* Without a database: an in-memory store, so the app still works for local
  development. Documents are lost on restart; a warning is logged.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.vectorstores import InMemoryVectorStore, VectorStore

from agentic_chatbot.components.embedding_loader import get_embeddings
from agentic_chatbot.core.settings import config_section, get_settings, sqlalchemy_uri
from agentic_chatbot.exception.exception import VectorStoreException

logger = logging.getLogger(__name__)


def vector_backend() -> str:
    return "pgvector" if get_settings().effective_vector_db_uri else "memory"


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    embeddings = get_embeddings()
    uri = get_settings().effective_vector_db_uri
    if not uri:
        logger.warning("No VECTOR_DB_URI/DB_URI set: using an in-memory vector store (not persistent)")
        return InMemoryVectorStore(embedding=embeddings)

    try:
        from langchain_postgres import PGVector

        store = PGVector(
            embeddings=embeddings,
            collection_name=str(config_section("rag").get("collection", "chatbot_docs")),
            connection=sqlalchemy_uri(uri),
            use_jsonb=True,
        )
        logger.info("PGVector store ready")
        return store
    except Exception as exc:  # pragma: no cover - needs a database
        raise VectorStoreException(
            f"Failed to initialise PGVector: {exc}",
            public_message="Could not connect to the vector database. Check VECTOR_DB_URI and that the pgvector extension is installed.",
        ) from exc


def reset_vector_store() -> None:
    get_vector_store.cache_clear()


class VectorStoreLoader:
    """Backwards-compatible wrapper."""

    def load_vectorstore(self) -> VectorStore:
        return get_vector_store()
