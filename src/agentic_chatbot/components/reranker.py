"""Optional cross-encoder reranker (enable with ``rag.rerank: true``).

sentence-transformers is heavy (it pulls in PyTorch), so it is an optional
dependency: ``pip install sentence-transformers``. If it isn't installed, the
reranker is skipped with a warning and MMR ordering is kept.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        from sentence_transformers import CrossEncoder  # type: ignore[import-not-found]

        self.model = CrossEncoder(model_name)

    def rerank(self, query: str, docs: list[Document], top_k: int = 4) -> list[Document]:
        if not docs:
            return docs
        scores = self.model.predict([(query, d.page_content) for d in docs])
        ranked = sorted(zip(docs, scores, strict=True), key=lambda pair: float(pair[1]), reverse=True)
        out = []
        for doc, score in ranked[:top_k]:
            doc.metadata["rerank_score"] = float(score)
            out.append(doc)
        return out


@lru_cache(maxsize=1)
def get_reranker(model_name: str) -> Reranker | None:
    try:
        return Reranker(model_name)
    except ImportError:
        logger.warning("rag.rerank is on but sentence-transformers is not installed; skipping rerank")
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not load reranker %s: %s", model_name, exc)
    return None
