"""Prompt for the remember block (long-term memory extraction)."""

MEMORY_PROMPT = """You maintain the long-term memory an AI assistant keeps about its user, across all conversations.

Existing memories (id in brackets):
{existing}

Latest exchange:
User: {user}
Assistant: {assistant}

Decide what to change in memory, using only what the USER said about themselves in this exchange.

Save durable facts worth knowing in future conversations: their name, role, employer, location and time zone; projects, goals and tools they use; preferences about how answers should look; people and things they mention repeatedly.

Do not save:
- anything only the assistant said, or general knowledge
- one-off questions, requests or temporary states ("is tired today")
- passwords, API keys, card or account numbers, or other secrets
- health, religion, politics or other sensitive details, unless the user explicitly asks you to remember them

Rules:
- Write each memory as one short sentence about the user in the third person, e.g. "Name is Kanish", "Prefers answers in Python".
- If a new fact replaces an existing memory, put it in `update` with that memory's id instead of adding a duplicate.
- If the user asks to forget something, or says an existing memory is wrong, put its id in `delete`.
- If the user explicitly asks you to remember something, save it.
- If nothing should change, return empty lists. Most exchanges change nothing."""
