"""
Deep research route (route id ``agent``, shown as "Deep research").

    research_plan ──quick──▶ agent (tool-using ReAct loop, for simple look-ups)
          │
          └─deep─▶ research_worker × N (parallel, one per sub-question, via Send)
                        │
                   research_review ──gaps──▶ research_worker × M (one follow-up round)
                        │
                   research_write (streams a cited Markdown report)

A request is "deep" when the user turned on Deep research in the composer, or
asks for research, a report, a comparison or an analysis. Quick look-ups
("weather in Pune", "who won yesterday") skip planning and go straight to the
tool agent, so they stay fast.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any, TypedDict

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send
from pydantic import BaseModel, Field

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.core.settings import config_section
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.exception.exception import LLMConfigError
from agentic_chatbot.logging.logging_utils import ExecutionTimer
from agentic_chatbot.nodes.events import emit, step
from agentic_chatbot.prompts.research_prompt import PLAN_PROMPT, REFLECT_PROMPT, WRITE_PROMPT, today
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.services.spreadsheets import mentions_sheets, sheets_available
from agentic_chatbot.tools.web_tool import PROVIDER_LABELS, search_results, web_search_available
from agentic_chatbot.utils.message_builder import context_window, latest_user_text, message_text, strip_think, transcript
from agentic_chatbot.utils.structured import structured_invoke

logger = logging.getLogger(__name__)

PLAN_EXAMPLE = '{"sub_questions": [{"question": "<focused sub-question>", "query": "<3 to 8 word search query>"}]}'
REFLECT_EXAMPLE = (
    '{"sufficient": false, "follow_ups": [{"question": "<sub-question for a gap>", "query": "<search query>"}]}\n'
    'or, when the notes are enough: {"sufficient": true, "follow_ups": []}'
)

# Requests that deserve a planned, multi-search report rather than a quick look-up.
DEEP_INTENT = re.compile(
    r"\b(research|investigat\w*|deep[- ]?dive|in[- ]depth|comprehensive|thorough|detailed|"
    r"report (?:on|about)|write (?:a|an|me a) (?:report|analysis|overview|brief)|compare|comparison|versus|vs\.?|"
    r"pros and cons|analy[sz]e|analysis|landscape|overview of|state of|everything about)\b",
    re.I,
)
SEARCH_TIMEOUT_SECONDS = 40.0
# Search the document library too only when the request is about the user's files;
# otherwise unrelated passages (a system-design PDF in a question about Vanguard) crowd out the web sources.
DOC_INTENT = re.compile(r"\b(document|docs|pdf|paper|report i (?:uploaded|attached)|file|uploaded|attached|my notes|library|knowledge base)\b", re.I)


class SubQuestion(BaseModel):
    question: str = Field(description="A focused sub-question")
    query: str = Field(description="A short web search query for it")


class ResearchPlan(BaseModel):
    """Sub-questions that together answer the request."""

    sub_questions: list[SubQuestion] = Field(default_factory=list)


class Reflection(BaseModel):
    """Whether the research so far is enough to write the report."""

    sufficient: bool = Field(True, description="True when the notes already cover the request well")
    follow_ups: list[SubQuestion] = Field(default_factory=list, description="New sub-questions for the gaps")


class ResearchTask(TypedDict, total=False):
    index: int
    round: int
    question: str
    query: str
    use_docs: bool  # also search the document library


def _cfg() -> dict[str, Any]:
    return config_section("research")


async def _can_research() -> bool:
    return web_search_available() or await get_knowledge_base().has_documents()


async def choose_depth(state: Chatbot) -> str:
    if not await _can_research():
        return "quick"  # nothing to search: the agent explains that web search is off
    if state.mode == "deep_research":
        return "deep"
    text = latest_user_text(state.messages)
    if sheets_available() and mentions_sheets(text):
        return "quick"  # "analyse my refund sheet" is a calculation for the SQL tool, not web research
    return "deep" if DEEP_INTENT.search(text) else "quick"


def fallback_plan(question: str, count: int) -> list[SubQuestion]:
    """Used when the model can't produce a plan: a few generic angles on the question."""
    q = " ".join(question.split())[:160]
    year = datetime.now().year
    angles = [
        SubQuestion(question=q, query=q[:100]),
        SubQuestion(question=f"Latest developments: {q}", query=f"{q[:80]} latest {year}"),
        SubQuestion(question=f"Key facts and figures: {q}", query=f"{q[:80]} facts statistics"),
        SubQuestion(question=f"Different views and criticism: {q}", query=f"{q[:80]} analysis criticism"),
    ]
    return angles[: max(1, count)]


def _dedupe(questions: list[SubQuestion], seen: set[str], limit: int) -> list[SubQuestion]:
    out: list[SubQuestion] = []
    for sq in questions:
        query = " ".join((sq.query or sq.question).split())[:160]
        key = query.casefold()
        if not query or key in seen:
            continue
        seen.add(key)
        out.append(SubQuestion(question=" ".join(sq.question.split())[:240] or query, query=query))
        if len(out) >= limit:
            break
    return out


async def research_plan(state: Chatbot, config: RunnableConfig) -> dict:
    """Decide quick vs deep; for deep, break the request into sub-questions."""
    depth = await choose_depth(state)
    reset = {"research_notes": None, "research_questions": [], "research_round": 0}
    if depth == "quick":
        return {"research_depth": "quick", **reset}

    with ExecutionTimer("research_plan", logger_instance=logger):
        question = latest_user_text(state.messages)
        count = int(_cfg().get("max_sub_questions", 4))
        step("thinking", "Planning the research", question[:200], step_id="research-plan", status="running")

        history = context_window(state.messages[:-1], max_tokens=800)
        context = ""
        if state.summary or history:
            context = "\nConversation so far:\n" + (state.summary + "\n" if state.summary else "") + transcript(history, 400) + "\n"
        prompt = PLAN_PROMPT.format(today=today(), count=count, context=context, question=question)
        try:
            plan = await structured_invoke(ResearchPlan, prompt, PLAN_EXAMPLE, config=config)
            questions = _dedupe(plan.sub_questions, set(), count)
        except LLMConfigError:
            raise
        except Exception as exc:
            logger.warning("Research planning failed (%s: %s); using generic angles", type(exc).__name__, exc)
            questions = []
        if not questions:
            questions = _dedupe(fallback_plan(question, count), set(), count)

        step("thinking", f"Planned {len(questions)} sub-question{'s' if len(questions) != 1 else ''}",
             "\n".join(f"{i}. {q.question}" for i, q in enumerate(questions, 1)), step_id="research-plan")
        use_docs = bool(DOC_INTENT.search(question)) or not web_search_available()
        tasks = [{"index": i, "round": 1, "question": q.question, "query": q.query, "use_docs": use_docs}
                 for i, q in enumerate(questions)]
        return {**reset, "research_depth": "deep", "research_round": 1, "research_questions": tasks}


def _pending(state: Chatbot) -> list[dict]:
    done = {(n.get("round"), n.get("index")) for n in state.research_notes}
    return [q for q in state.research_questions
            if q.get("round") == state.research_round and (q.get("round"), q.get("index")) not in done]


def route_after_plan(state: Chatbot) -> Any:
    if state.research_depth != "deep":
        return "agent"
    tasks = _pending(state)
    return [Send("research_worker", ResearchTask(**t)) for t in tasks] if tasks else "research_write"


def route_after_review(state: Chatbot) -> Any:
    tasks = _pending(state)
    return [Send("research_worker", ResearchTask(**t)) for t in tasks] if tasks else "research_write"


async def research_worker(task: ResearchTask, config: RunnableConfig) -> dict:
    """Search one sub-question (web, plus the document library when it has files). Runs in parallel."""
    cfg = _cfg()
    per_query = int(cfg.get("results_per_query", 5))
    chars = int(cfg.get("note_chars", 1200))
    step_id = f"research-{task['round']}-{task['index']}"
    step("tool", task["question"], task["query"], step_id=step_id, status="running", tool="web_search")

    note: dict[str, Any] = {**task, "provider": None, "answer": None, "results": [], "docs": [], "problem": ""}
    if web_search_available():
        try:
            provider, answer, results, problem = await asyncio.wait_for(
                search_results(task["query"]), timeout=SEARCH_TIMEOUT_SECONDS
            )
            note.update(provider=provider, answer=answer, problem=problem, results=[
                {"title": r.get("title") or r.get("url", ""), "url": r["url"], "content": (r.get("content") or "").strip()[:chars]}
                for r in results[:per_query]
            ])
        except TimeoutError:
            note["problem"] = f"Search timed out after {SEARCH_TIMEOUT_SECONDS:.0f}s."
        except Exception as exc:
            logger.warning("Research search failed for %r: %s", task["query"], exc)
            note["problem"] = f"Search failed ({type(exc).__name__})."

    kb = get_knowledge_base()
    if task.get("use_docs") and await kb.has_documents():
        try:
            docs = await kb.search(task["question"])
            note["docs"] = [
                {"title": d.metadata.get("source_name", "document"), "page": d.metadata.get("page"),
                 "content": d.page_content.strip()[:chars]}
                for d in docs[:3]
            ]
        except Exception as exc:
            logger.info("Document search skipped in research: %s", exc)

    found = len(note["results"]) + len(note["docs"])
    via = PROVIDER_LABELS.get(note["provider"] or "", "")
    result = f"{found} source{'s' if found != 1 else ''}" + (f" via {via}" if via else "") if found else (note["problem"] or "Nothing found")
    items = [{"title": r["title"][:120], "url": r["url"]} for r in note["results"][:5]]
    items += [{"title": d["title"], "url": None} for d in note["docs"][:2]]
    step("tool", task["question"], task["query"], step_id=step_id, status="done" if found else "error",
         tool="web_search", result=result, items=items)
    return {"research_notes": [note]}


def _findings(notes: list[dict], per_note: int = 3) -> str:
    lines = []
    for n in sorted(notes, key=lambda x: (x.get("round", 0), x.get("index", 0))):
        lines.append(f"- {n['question']} (query: {n['query']})")
        items = n.get("results", [])[:per_note] + n.get("docs", [])[:1]
        if not items:
            lines.append("    nothing found")
        for r in items:
            lines.append(f"    * {r.get('title', '')}: {r.get('content', '')[:220]}")
    return "\n".join(lines)


async def research_review(state: Chatbot, config: RunnableConfig) -> dict:
    """Gap check: one model call deciding whether a follow-up round is worth it."""
    cfg = _cfg()
    if state.research_round >= int(cfg.get("max_rounds", 2)):
        return {}
    count = max(1, int(cfg.get("max_sub_questions", 4)) // 2)
    step("thinking", "Checking for gaps", "Reading what the searches found", step_id="research-review", status="running")
    prompt = REFLECT_PROMPT.format(
        today=today(),
        question=latest_user_text(state.messages),
        covered="\n".join(f"- {q['question']} (query: {q['query']})" for q in state.research_questions),
        findings=_findings(state.research_notes)[:9000],
        count=count,
    )
    try:
        reflection = await structured_invoke(Reflection, prompt, REFLECT_EXAMPLE, config=config)
    except LLMConfigError:
        raise
    except Exception as exc:
        logger.warning("Research gap check failed (%s); writing the report", exc)
        step("thinking", "Checked for gaps", "Skipped: the model couldn't review the notes.", step_id="research-review")
        return {}

    seen = {q["query"].casefold() for q in state.research_questions}
    follow = [] if reflection.sufficient else _dedupe(reflection.follow_ups, seen, count)
    if not follow:
        step("thinking", "Checked for gaps", "The sources cover the request.", step_id="research-review")
        return {}
    step("thinking", f"Found {len(follow)} gap{'s' if len(follow) != 1 else ''} to fill",
         "\n".join(f"- {q.question}" for q in follow), step_id="research-review")
    start = len(state.research_questions)
    nxt = state.research_round + 1
    use_docs = any(q.get("use_docs") for q in state.research_questions)
    tasks = [{"index": start + i, "round": nxt, "question": q.question, "query": q.query, "use_docs": use_docs}
             for i, q in enumerate(follow)]
    return {"research_round": nxt, "research_questions": [*state.research_questions, *tasks]}


def _candidates(notes: list[dict]) -> list[tuple[dict, dict, str]]:
    """Every result as (note, item, kind), interleaved across sub-questions: each one's best result
    first, then each one's second best, and so on, so a size limit keeps every angle covered."""
    ordered = sorted(notes, key=lambda x: (x.get("round", 0), x.get("index", 0)))
    lists = [[(n, r, "web") for r in n.get("results", [])] + [(n, d, "doc") for d in n.get("docs", [])] for n in ordered]
    out: list[tuple[dict, dict, str]] = []
    for rank in range(max((len(x) for x in lists), default=0)):
        out.extend(x[rank] for x in lists if rank < len(x))
    return out


def number_sources(notes: list[dict], max_sources: int | None = None,
                   budget_chars: int | None = None) -> tuple[list[dict], str]:
    """Number distinct sources across all notes: (sources for the UI, text block for the writer).

    At most ``max_sources`` are kept, and their text is trimmed to share
    ``budget_chars``, so the writer's prompt fits a small model's context window.
    """
    cfg = _cfg()
    max_sources = int(max_sources or cfg.get("max_report_sources", 16))
    budget_chars = int(budget_chars or cfg.get("source_budget_chars", 14000))

    picked: list[tuple[dict, dict, str]] = []
    seen: set[str] = set()
    for note, item, kind in _candidates(notes):
        key = item.get("url") if kind == "web" else f"doc:{item.get('title')}:{item.get('page')}:{item.get('content', '')[:40]}"
        if not key or key in seen:
            continue
        seen.add(key)
        picked.append((note, item, kind))
        if len(picked) >= max_sources:
            break

    per_source = max(200, budget_chars // max(len(picked), 1))
    sources: list[dict] = []
    blocks: list[str] = []
    for idx, (note, item, kind) in enumerate(picked, start=1):
        text = (item.get("content") or "")[:per_source]
        if kind == "web":
            sources.append({"kind": "web", "index": idx, "title": item.get("title") or item["url"], "url": item["url"],
                            "snippet": text[:280]})
            blocks.append(f"[{idx}] {item.get('title', '')}\nURL: {item['url']}\nFor: {note['question']}\n{text}")
        else:
            where = f"{item.get('title')}, page {item['page']}" if item.get("page") else item.get("title")
            sources.append({"kind": "doc", "index": idx, "title": item.get("title"), "page": item.get("page"),
                            "snippet": text[:280]})
            blocks.append(f"[{idx}] Uploaded document: {where} (cite as [{idx}] without a link)\n{text}")
    return sources, "\n\n".join(blocks)


def findings_digest(sources: list[dict]) -> str:
    """Last resort when the model writes nothing: the sources found, so the search isn't wasted."""
    lines = [
        "## Research notes",
        "",
        "The model couldn't write the report this time (it returned an empty answer), so here is what the searches found. "
        "Try again, or pick a larger model in the model picker for full reports.",
        "",
    ]
    for s in sources:
        link = f"[{s['title']}]({s['url']})" if s.get("url") else f"{s['title']}" + (f", page {s['page']}" if s.get("page") else "")
        snippet = " ".join((s.get("snippet") or "").split())[:220]
        lines.append(f"{s['index']}. {link}" + (f": {snippet}" if snippet else ""))
    return "\n".join(lines)


async def research_write(state: Chatbot, config: RunnableConfig) -> dict:
    """Write the cited report. Its tokens stream to the client as the answer.

    Small models sometimes return nothing when the prompt is long, so an empty
    answer is retried once with half the sources and shorter excerpts; if that
    is empty too, the user still gets the list of sources found.
    """
    with ExecutionTimer("research_write", logger_instance=logger):
        cfg = _cfg()
        max_sources = int(cfg.get("max_report_sources", 16))
        budget = int(cfg.get("source_budget_chars", 14000))
        searches = len(state.research_notes)
        question = latest_user_text(state.messages)

        user_context = ""
        if state.user_memories:
            user_context += f"\nAbout the user (from long-term memory):\n{state.user_memories}\n"
        if state.summary:
            user_context += f"\nEarlier in this conversation:\n{state.summary}\n"

        answer, response_id, sources = "", None, []
        limit, chars = max_sources, budget
        for attempt in range(2):
            if attempt:  # the retry: half the sources (at least 2), a third of the text
                limit, chars = max(2, len(sources) // 2), budget // 3
            sources, block = number_sources(state.research_notes, limit, chars)
            step("thinking", "Writing the report" if attempt == 0 else "Writing the report again, with fewer sources",
                 f"{len(sources)} sources from {searches} searches", step_id="research-write", status="running")
            if sources:
                emit({"type": "sources", "items": sources})
            system = WRITE_PROMPT.format(
                today=today(),
                user_context=user_context,
                question=question,
                sources=block or "(No sources were found. Say so plainly, then give what you know and mark it as unverified.)",
            )
            messages = [SystemMessage(content=system), *context_window(state.messages, max_tokens=1200)]
            response = await get_llm("main").ainvoke(messages, config=config)
            answer, response_id = strip_think(message_text(response.content)), response.id
            if answer or not sources:
                break
            logger.warning("Report writer returned nothing (attempt %d, %d sources)", attempt + 1, len(sources))
            emit({"type": "draft_reset"})

        if not answer:
            answer = findings_digest(sources) if sources else "I couldn't find sources for this, so there is no report."
            step("thinking", "Listed the sources found", "The model returned an empty report twice.",
                 step_id="research-write", status="error")
        else:
            step("thinking", "Wrote the report", f"{len(sources)} sources", step_id="research-write")
        # Notes are only needed for this turn; clearing them keeps the saved thread small.
        return {"messages": [AIMessage(content=answer, id=response_id)], "research_notes": None}
