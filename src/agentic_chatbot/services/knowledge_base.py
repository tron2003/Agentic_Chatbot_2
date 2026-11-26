"""
Knowledge base: ingest files into the vector store, search them, delete them.

Every chunk gets a deterministic ID (``<doc_id>:<n>``) that is recorded in the
document registry, so a single document can be removed from the vector store
later. Blocking work (parsing, embedding, similarity search) runs in a worker
thread so it never stalls the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from agentic_chatbot.components.embedding_loader import embedding_provider
from agentic_chatbot.components.ollama_service import ensure_ollama
from agentic_chatbot.components.reranker import get_reranker
from agentic_chatbot.components.vector_store_loader import get_vector_store, vector_backend
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.exception.exception import FileProcessingException, VectorStoreException
from agentic_chatbot.integrations.webhooks import emit_event
from agentic_chatbot.services.spreadsheets import is_spreadsheet, remove_copies, save_copy, warm_cache
from agentic_chatbot.services.store import get_store
from agentic_chatbot.utils.document_loader import DocumentLoader

logger = logging.getLogger(__name__)


def _embedding_hint(exc: Exception, fallback: str) -> str:
    """Turn the most common embedding failures into a message that says what to do."""
    text = str(exc).lower()
    provider = embedding_provider()
    if provider == "ollama":
        block = config_section("embeddings").get("ollama") or {}
        model = block.get("model", "qwen3-embedding:0.6b")
        base_url = block.get("base_url", "http://127.0.0.1:11434")
        if "not found" in text or "status code: 404" in text or "try pulling" in text:
            return f"The embedding model '{model}' isn't installed in Ollama. Run: ollama pull {model}"
        if any(s in text for s in ("failed to connect", "connection refused", "connecterror", "timed out")):
            return f"Couldn't reach Ollama at {base_url}. Start Ollama (or fix OLLAMA_BASE_URL) and try again."
    if provider == "openai" and ("401" in text or "api key" in text):
        return "OpenAI rejected the embeddings request. Check OPENAI_API_KEY in .env."
    return fallback


async def ensure_embeddings_ready() -> None:
    """Start a local Ollama if it isn't running (development only); a no-op for other providers."""
    if embedding_provider() != "ollama":
        return
    block = config_section("embeddings").get("ollama") or {}
    await asyncio.to_thread(ensure_ollama, block.get("base_url", "http://127.0.0.1:11434"))


class KnowledgeBase:
    def __init__(self) -> None:
        self._names_cache: list[str] | None = None

    @property
    def backend(self) -> str:
        return vector_backend()

    def _invalidate(self) -> None:
        self._names_cache = None

    async def document_names(self) -> list[str]:
        if self._names_cache is None:
            docs = await get_store().list_documents()
            self._names_cache = [d["name"] for d in docs]
        return self._names_cache

    async def has_documents(self) -> bool:
        return bool(await self.document_names())

    async def ingest_file(self, path: Path, display_name: str, size_bytes: int) -> dict[str, Any]:
        cfg = config_section("rag")
        loader = DocumentLoader(int(cfg.get("chunk_size", 1000)), int(cfg.get("chunk_overlap", 150)))
        try:
            chunks: list[Document] = await asyncio.to_thread(loader.load_documents, path)
        except Exception as exc:
            raise FileProcessingException(
                f"Failed to parse {display_name}: {exc}",
                public_message=f"Couldn't read {display_name}. Is it a valid, non-encrypted file?",
            ) from exc
        if not chunks:
            raise FileProcessingException(
                f"No text extracted from {display_name}",
                public_message=f"{display_name} has no extractable text (scanned PDFs need OCR first).",
            )

        doc_id = uuid.uuid4().hex[:12]
        ids = [f"{doc_id}:{i}" for i in range(len(chunks))]
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({"doc_id": doc_id, "source_name": display_name, "chunk": i})

        try:
            await ensure_embeddings_ready()
            # Opening the store can touch the database: keep it off the event loop.
            store = await asyncio.to_thread(get_vector_store)
            await asyncio.to_thread(store.add_documents, chunks, ids=ids)
        except VectorStoreException:
            raise
        except Exception as exc:
            raise VectorStoreException(
                f"Embedding/indexing failed for {display_name}: {exc}",
                public_message=_embedding_hint(
                    exc,
                    "Couldn't index the file. Check that the embedding model is reachable "
                    "(EMBEDDING_PROVIDER / OLLAMA_BASE_URL).",
                ),
            ) from exc

        record = {
            "id": doc_id,
            "name": display_name,
            "file_type": path.suffix.lower() or "",
            "size_bytes": size_bytes,
            "chunks": len(chunks),
            "chunk_ids": ids,
        }
        await get_store().add_document(record)
        if is_spreadsheet(display_name):
            # Keep the file itself too, so the agent can calculate with it (services/spreadsheets.py).
            try:
                await asyncio.to_thread(save_copy, path, doc_id, display_name)
                await asyncio.to_thread(warm_cache)
            except OSError as exc:
                logger.warning("Couldn't keep a copy of %s for calculations: %s", display_name, exc)
        self._invalidate()
        emit_event("document.ingested", {k: v for k, v in record.items() if k != "chunk_ids"})
        logger.info("Ingested document", extra={"doc_id": doc_id, "chunks": len(chunks)})
        return record

    async def delete_document(self, doc_id: str) -> bool:
        record = await get_store().get_document(doc_id)
        if not record:
            return False
        ids = list(record.get("chunk_ids") or [])
        if ids:
            try:
                store = await asyncio.to_thread(get_vector_store)
                await asyncio.to_thread(store.delete, ids)
            except Exception as exc:
                logger.warning("Vector delete failed for %s: %s", doc_id, exc)
        await get_store().delete_document(doc_id)
        await asyncio.to_thread(remove_copies, doc_id)
        self._invalidate()
        emit_event("document.deleted", {"id": doc_id, "name": record["name"]})
        return True

    async def clear(self) -> int:
        docs = await get_store().list_documents()
        for doc in docs:
            await self.delete_document(doc["id"])
        self._invalidate()
        return len(docs)

    async def search(self, query: str) -> list[Document]:
        cfg = config_section("rag")
        k = int(cfg.get("k", 6))
        await ensure_embeddings_ready()
        store = await asyncio.to_thread(get_vector_store)
        try:
            docs = await asyncio.to_thread(
                store.max_marginal_relevance_search,
                query,
                k=k if not cfg.get("rerank") else max(k * 2, 10),
                fetch_k=int(cfg.get("fetch_k", 24)),
                lambda_mult=float(cfg.get("lambda_mult", 0.6)),
            )
        except Exception as exc:
            raise VectorStoreException(
                f"Similarity search failed: {exc}",
                public_message=_embedding_hint(exc, "Searching your documents failed. Check the embedding model."),
            ) from exc

        if cfg.get("rerank") and docs:
            reranker = get_reranker(str(cfg.get("rerank_model")))
            if reranker:
                docs = await asyncio.to_thread(reranker.rerank, query, docs, int(cfg.get("rerank_top_k", k)))
        return docs[:k]


_kb = KnowledgeBase()


def get_knowledge_base() -> KnowledgeBase:
    return _kb
