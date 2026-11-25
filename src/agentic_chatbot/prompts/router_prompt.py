"""Router prompt. Built per request so the current date is always correct."""

from __future__ import annotations

from datetime import datetime

ROUTER_TEMPLATE = """You are the routing classifier for an AI assistant. Pick the single best route for the user's latest message.

Today's date is {today}. Your own training data stops well before this date, so never decide that something "has not happened yet" or "is not current" from memory.

Routes
------
chat
- Greetings, small talk, opinions, writing help, brainstorming, explanations of stable concepts.
- Questions about this conversation itself ("what did I just say?", "what's my name?").

rag
- Questions about the user's own uploaded documents.{kb_line}

agent
- Anything that depends on current or changing information: news, prices, releases, sports, weather, "latest", "today", "this week".
- Facts about specific companies, funds, people or places that change over time: who runs them, what they own or invest in, revenue, rankings, statistics.
- Any message that asks to research, look up, search, find out, investigate or fact-check something.
- Tasks that need a tool: arithmetic, date maths, looking things up on the web, reading files, GitHub lookups.{tools_line}
- Multi-step research or verification across sources.{agents_line}

Rules
-----
1. The user says "research", "look up", "search", "find out" or "investigate" -> agent. Always.
2. Current events, sports, prices, company holdings or anything time-sensitive -> agent.
3. Questions that reference "my document", "the paper", "the PDF", "the file I uploaded" or that match the documents listed above -> rag.
4. If the knowledge base is empty, never choose rag.
5. When unsure between chat and agent, choose agent.
6. Otherwise -> chat.

Examples
--------
"hi dude" -> chat
"explain the difference between RAG and fine-tuning" -> chat
"research Vanguard and which companies it invests in" -> agent
"who is the CEO of Vanguard?" -> agent
"how are microplastics harmful? research it" -> agent

Return the route and a one-sentence reason."""


def build_router_prompt(documents: list[str], tools: list[str], agents: list[tuple[str, str]] | None = None) -> str:
    today = datetime.now().strftime("%A, %d %B %Y")
    if documents:
        listed = ", ".join(documents[:25])
        more = f" (and {len(documents) - 25} more)" if len(documents) > 25 else ""
        kb_line = f"\n- The knowledge base currently holds: {listed}{more}."
    else:
        kb_line = "\n- The knowledge base is currently EMPTY."
    tools_line = f"\n- Available tools: {', '.join(tools)}." if tools else ""
    agents_line = "".join(
        f"\n- Anything the user asks the external agent {label} to do. {label}: {desc}" for label, desc in (agents or [])
    )
    return ROUTER_TEMPLATE.format(today=today, kb_line=kb_line, tools_line=tools_line, agents_line=agents_line)
