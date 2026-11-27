"""Prompt for the conversational (chat) route, plus the memory sections shared by every route."""

from __future__ import annotations

from datetime import datetime

SYSTEM_PROMPT = """You are a helpful personal AI assistant.

Today's date is {today}.

How to respond
- Use what you know about the user, the conversation summary and the history naturally; remember their name, preferences, projects and goals.
- If something is in the history, summary or long-term memory, answer from it directly.
- Never invent memories or facts. If you don't know, say so and ask a short follow-up question.
- Be concise and clear. Use Markdown (headings, lists, tables, fenced code with a language tag) when it improves readability.
- For anything that depends on current events, say that Deep research can look it up.
{memory}"""


def project_section() -> str:
    """The project this chat belongs to and its instructions (empty outside projects)."""
    from agentic_chatbot.core.scope import current_scope

    scope = current_scope()
    if scope is None or not scope.project_id:
        return ""
    text = f"\nProject\nThis chat is part of the user's project \"{scope.name}\". Its documents are the only ones you can search here.\n"
    if scope.instructions.strip():
        text += f"Project instructions from the user (follow them in every answer):\n{scope.instructions.strip()}\n"
    return text


def memory_sections(summary: str | None, user_memories: str | None) -> str:
    """Project instructions, long-term memory (facts about the user) and short-term summary (earlier in this chat)."""
    about = user_memories or "Nothing yet."
    return project_section() + (
        "\nWhat you know about the user (long-term memory, from earlier conversations)\n"
        f"{about}\n"
        "Use these when relevant; don't recite them unprompted.\n"
        "\nConversation summary (earlier in this chat)\n"
        f"{summary or 'No earlier conversation.'}\n"
    )


def build_chat_prompt(summary: str | None, user_memories: str | None = None) -> str:
    return SYSTEM_PROMPT.format(
        today=datetime.now().strftime("%A, %d %B %Y"),
        memory=memory_sections(summary, user_memories),
    )
