"""Prompts for the conversation summariser and the title generator."""

SUMMARY_PROMPT = """You maintain a running summary of a conversation between a user and an AI assistant.

Existing summary:
{existing}

New messages to fold in:
{transcript}

Write the updated running summary. Keep: the user's name and identity, preferences, important facts, ongoing projects, technical decisions, goals and open questions. Drop greetings, small talk and anything repeated. Return only the summary, in at most 200 words."""

TITLE_PROMPT = """Write a short conversation title (3 to 6 words) for a chat that starts with the message below.
Use sentence case, no quotes, no trailing punctuation. Return only the title.

Message:
{message}"""
