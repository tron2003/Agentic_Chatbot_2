import sys
import os
import logging
from langchain_postgres import PGVector

from agentic_chatbot.components.embedding_loader import EmbeddingLoader
from agentic_chatbot.exception.exception import VectorStoreException
from agentic_chatbot.logging.logging_utils import get_correlation_id

logger = logging.getLogger(__name__)


class VectorStoreLoader:
    """Loads and configures PGVector instance for semantic search."""

    def load_vectorstore(self):
        """Initialize and return a PGVector instance."""
        correlation_id = get_correlation_id()

        try:
            logger.debug(
                "Loading embeddings for vector store",
                extra={"correlation_id": correlation_id},
            )

            embeddings = EmbeddingLoader().load_embeddings()

            logger.debug(
                "Embeddings loaded successfully",
                extra={"correlation_id": correlation_id},
            )

            # Get database connection string from environment or use default
            db_uri = os.getenv(
                "VECTOR_DB_URI",
                "postgresql://postgres:postgres@localhost:5442/project_chatbot",
            )

            logger.debug(
                "Initializing PGVector connection",
                extra={"correlation_id": correlation_id},
            )

            vector_store = PGVector(
                embeddings=embeddings, collection_name="chatbot_docs", connection=db_uri
            )

            logger.info(
                "Vector store loaded successfully",
                extra={"correlation_id": correlation_id},
            )

            return vector_store

        except Exception as e:
            logger.error(
                f"Failed to load vector store: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise VectorStoreException(
                f"Failed to initialize vector store: {str(e)}",
                sys,
                correlation_id=correlation_id,
            )
