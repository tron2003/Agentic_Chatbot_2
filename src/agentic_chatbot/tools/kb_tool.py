"""Let the research agent search the user's knowledge base too."""

from __future__ import annotations

from langchain_core.tools import tool

from agentic_chatbot.services.knowledge_base import get_knowledge_base


@tool(response_format="content_and_artifact")
async def search_knowledge_base(query: str) -> tuple[str, list[dict]]:
    """Search the user's uploaded documents (PDFs, notes, code) for passages relevant to the query."""
    docs = await get_knowledge_base().search(query)
    if not docs:
        return "No relevant passages in the knowledge base.", []
    blocks, sources = [], []
    for i, d in enumerate(docs, start=1):
        name = d.metadata.get("source_name", "document")
        page = d.metadata.get("page")
        where = f"{name}, page {page}" if page else name
        blocks.append(f"[{i}] ({where})\n{d.page_content.strip()}")
        sources.append({"kind": "doc", "title": name, "page": page, "snippet": d.page_content[:300]})
    return "\n\n".join(blocks), sources
