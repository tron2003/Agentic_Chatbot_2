import sys
import logging
from langchain_core.messages import SystemMessage, HumanMessage
from agentic_chatbot.components.vector_store_loader import VectorStoreLoader
from agentic_chatbot.components.llm_loader import LLMLoader
from agentic_chatbot.prompts.rag_prompt import RAG_PROMPT
from agentic_chatbot.utils.message_builder import build_messages
from agentic_chatbot.exception.exception import LLMException, VectorStoreException
from agentic_chatbot.logging.logging_utils import (
    ExecutionTimer,
    get_correlation_id,
    log_async,
)

logger = logging.getLogger(__name__)

vector_db = VectorStoreLoader().load_vectorstore()
llm = LLMLoader().load_llm()


@log_async()
async def rag_node(state):
    """
    RAG node for retrieving and grounding responses with knowledge base documents.
    Performs semantic search and augments LLM response with retrieved context.
    """
    correlation_id = get_correlation_id()

    with ExecutionTimer("rag_node", correlation_id, logger):
        try:
            if not state.messages:
                logger.error(
                    "No messages in state", extra={"correlation_id": correlation_id}
                )
                raise LLMException(
                    "No messages provided for RAG", sys, correlation_id=correlation_id
                )

            question = state.messages[-1].content
            logger.debug(
                f"RAG query: {question[:100]}...",
                extra={"correlation_id": correlation_id},
            )

            # Retrieve relevant documents
            logger.debug(
                "Performing vector search for relevant documents",
                extra={"correlation_id": correlation_id},
            )

            try:
                docs = vector_db.max_marginal_relevance_search(
                    question, k=10, fetch_k=30
                )
                logger.info(
                    f"Retrieved {len(docs)} documents from vector store",
                    extra={"correlation_id": correlation_id},
                )
            except Exception as e:
                logger.error(
                    f"Vector store search failed: {str(e)}",
                    extra={"correlation_id": correlation_id},
                    exc_info=True,
                )
                raise VectorStoreException(
                    f"Failed to retrieve documents: {str(e)}",
                    sys,
                    correlation_id=correlation_id,
                )

            context = "\n".join(doc.page_content for doc in docs)
            context_length = len(context.split())
            logger.debug(
                f"RAG context prepared: {context_length} words",
                extra={"correlation_id": correlation_id},
            )

            # RAG system prompt with retrieved document context
            filled_prompt = RAG_PROMPT.format(context=context)

            # Build full message list: RAG prompt + conversation history (summary + recent messages)
            messages = [SystemMessage(content=filled_prompt)]
            messages.extend(build_messages(state))

            logger.debug(
                f"RAG conversation prepared with {len(messages)} messages",
                extra={"correlation_id": correlation_id},
            )

            response = await llm.ainvoke(messages)

            logger.info(
                "RAG response generated successfully",
                extra={
                    "correlation_id": correlation_id,
                    "response_length": (
                        len(response.content) if hasattr(response, "content") else 0
                    ),
                    "documents_used": len(docs),
                },
            )

            return {"messages": [response]}

        except (LLMException, VectorStoreException):
            raise
        except Exception as e:
            logger.error(
                f"RAG node failed: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True,
            )
            raise LLMException(
                f"Failed to generate RAG response: {str(e)}",
                sys,
                correlation_id=correlation_id,
            )
