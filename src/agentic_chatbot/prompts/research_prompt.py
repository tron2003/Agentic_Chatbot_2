"""Prompts for Deep research: planner, gap check and report writer."""

from __future__ import annotations

from datetime import datetime


def today() -> str:
    return datetime.now().strftime("%A, %d %B %Y")


PLAN_PROMPT = """You plan web research. Today's date is {today}.

Break the user's request into {count} or fewer focused sub-questions that together cover it well: background and key facts, the current state and recent developments, numbers worth checking, and different viewpoints or comparisons where relevant.

For each sub-question give a short web search query (3 to 8 words, no quotes or operators). Include the year in queries about recent events. Resolve words like "it" or "they" using the conversation.
{context}
User request:
{question}"""


REFLECT_PROMPT = """You review research notes before a report is written. Today's date is {today}.

Request:
{question}

Sub-questions researched so far:
{covered}

What the searches found (titles and snippets):
{findings}

Is there an important gap: a part of the request with no good evidence, a claim needing a second source, or an obvious follow-up? If the notes are enough, set sufficient to true and leave follow_ups empty. Otherwise give at most {count} new sub-questions with search queries. Never repeat a query already run."""


WRITE_PROMPT = """You are a research analyst writing a report for the user. Today's date is {today}.

Write a well-structured Markdown report that answers the request below, using the numbered sources.

Structure:
- Start with a level-2 heading that names the topic, then a short **Summary** paragraph (3 to 5 sentences) with the direct answer.
- Then sections with level-3 headings, organised by theme rather than by source. Use bullet points and a table where they make comparisons or figures clearer.
- End with a short **Open questions** section only if something important could not be verified.

Citations:
- Back every factual claim with its source number as a Markdown link right after the claim, like [3](https://example.com/page). Use the exact URLs given. Several sources: [2](url)[5](url).
- Use only the sources below. If they conflict, say so and give both. If they don't cover something, say it couldn't be verified rather than guessing.
- Do not add a separate list of sources at the end; the app shows them.

Be specific: names, dates, numbers. No filler.
{user_context}
Request:
{question}

Sources:
{sources}"""
