"""RAG route: retrieve passages from the knowledge base, answer with citations."""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.exception.exception import VectorStoreException
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.nodes.events import emit, step
from agentic_chatbot.prompts.rag_prompt import build_rag_prompt
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.utils.message_builder import conversational, latest_user_text, message_text, strip_think

logger = logging.getLogger(__name__)


async def rag_node(state: Chatbot, config: RunnableConfig) -> dict:
    with ExecutionTimer("rag_node", logger_instance=logger):
        question = latest_user_text(state.messages)
        step_id = "retrieval"
        step("retrieval", "Searching your documents", question[:160], step_id=step_id, status="running")

        failed = False
        try:
            docs = await get_knowledge_base().search(question)
        except VectorStoreException as exc:
            logger.error("Retrieval failed: %s", exc)
            step("retrieval", "Document search failed", exc.public_message, step_id=step_id, status="error")
            docs, failed = [], True

        blocks, sources = [], []
        for i, doc in enumerate(docs, start=1):
            name = doc.metadata.get("source_name", "document")
            page = doc.metadata.get("page")
            label = f"source: {name}" + (f", page {page}" if page else "")
            blocks.append(f"[{i}] ({label})\n{doc.page_content.strip()}")
            sources.append({
                "kind": "doc",
                "index": i,
                "title": name,
                "page": page,
                "doc_id": doc.metadata.get("doc_id"),
                "snippet": doc.page_content.strip()[:280],
            })

        files = sorted({s["title"] for s in sources})
        if docs:
            step("retrieval", f"Found {len(docs)} passage{'s' if len(docs) != 1 else ''} in {len(files)} document{'s' if len(files) != 1 else ''}",
                 ", ".join(files), step_id=step_id)
            emit({"type": "sources", "items": sources})
        elif not failed:
            step("retrieval", "No matching passages", "Answering with what the model knows.", step_id=step_id)

        limit = int(config_section("memory").get("context_messages", 12))
        messages = [SystemMessage(content=build_rag_prompt("\n\n".join(blocks), state.summary))]
        messages.extend(conversational(state.messages, limit))
        response = await get_llm("main").ainvoke(messages, config=config)
        return {"messages": [AIMessage(content=strip_think(message_text(response.content)), id=response.id)]}
