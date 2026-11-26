"""Prompt for answering from knowledge base passages."""

from __future__ import annotations

from agentic_chatbot.prompts.prompt import memory_sections

RAG_PROMPT = """You answer questions using knowledge base passages from the user's own documents.

Passages
--------
{context}

How to answer
- Base the answer on the passages above. Cite them inline with their numbers, like [1] or [2][3].
- Combine information from several passages when they agree; point out when they disagree.
- If the passages don't contain the answer, say what is missing and answer only the part they support.
- Use Markdown for structure. Keep quotes short.
{memory}"""

NO_PASSAGES = "No relevant passages were found for this question."


def build_rag_prompt(context: str, summary: str | None, user_memories: str | None = None) -> str:
    return RAG_PROMPT.format(context=context or NO_PASSAGES, memory=memory_sections(summary, user_memories))
