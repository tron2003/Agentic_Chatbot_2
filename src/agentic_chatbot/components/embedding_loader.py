"""Embedding model factory (configured under ``embeddings`` in config.yaml)."""

from __future__ import annotations

from functools import lru_cache

from langchain_core.embeddings import Embeddings

from agentic_chatbot.core.settings import config_section
from agentic_chatbot.exception.exception import VectorStoreException


def embedding_provider() -> str:
    return str(config_section("embeddings").get("provider") or "ollama").lower()


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    cfg = config_section("embeddings")
    provider = embedding_provider()

    if provider == "ollama":
        from langchain_ollama import OllamaEmbeddings

        block = cfg.get("ollama") or {}
        return OllamaEmbeddings(
            model=block.get("model", "qwen3-embedding:0.6b"),
            base_url=block.get("base_url", "http://127.0.0.1:11434"),
        )

    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        block = cfg.get("openai") or {}
        if not block.get("api_key"):
            raise VectorStoreException(
                "OPENAI_API_KEY missing for embeddings",
                public_message="OpenAI embeddings need OPENAI_API_KEY in .env.",
            )
        return OpenAIEmbeddings(model=block.get("model", "text-embedding-3-small"), api_key=block["api_key"])

    if provider == "fake":
        from langchain_core.embeddings import DeterministicFakeEmbedding

        return DeterministicFakeEmbedding(size=256)

    raise VectorStoreException(
        f"Unknown embedding provider {provider}",
        public_message=f"Unknown embedding provider '{provider}'. Use ollama, openai or fake.",
    )


class EmbeddingLoader:
    """Backwards-compatible wrapper."""

    def load_embeddings(self) -> Embeddings:
        return get_embeddings()
