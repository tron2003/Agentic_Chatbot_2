"""Tavily web search tool.

Returns readable text for the model *and* the structured results as the tool
message artifact, so the UI can show proper source links.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from langchain_core.tools import tool

from agentic_chatbot.core.settings import config_section

logger = logging.getLogger(__name__)


def web_search_available() -> bool:
    return bool(os.getenv("TAVILY_API_KEY"))


def _client():
    # Keyed by the key itself, so a TAVILY_API_KEY added or changed in .env is used without a restart.
    return _client_for(os.environ["TAVILY_API_KEY"])


@lru_cache(maxsize=2)
def _client_for(api_key: str):
    from langchain_tavily import TavilySearch

    return TavilySearch(
        api_key=api_key,
        max_results=int(config_section("agent").get("web_results", 5)),
        search_depth="advanced",
    )


def _normalise(raw: Any) -> tuple[str | None, list[dict]]:
    if isinstance(raw, list):
        return None, raw
    if isinstance(raw, dict):
        return raw.get("answer"), list(raw.get("results") or [])
    return None, []


@tool(response_format="content_and_artifact")
async def web_search(query: str) -> tuple[str, list[dict]]:
    """Search the web for current information: news, recent events, releases, prices, sports,
    people's current roles, or any fact that may have changed. Input is a focused search query."""
    try:
        raw = await _client().ainvoke({"query": query})
    except Exception as exc:
        logger.warning("Web search failed: %s", exc)
        return f"Web search failed: {exc}", []

    answer, results = _normalise(raw)
    if not results:
        return "No results found. Try a different or broader query.", []

    sources = [
        {
            "kind": "web",
            "title": r.get("title") or r.get("url", ""),
            "url": r.get("url", ""),
            "snippet": (r.get("content") or "")[:300],
        }
        for r in results
        if r.get("url")
    ]
    blocks = [
        f"[{i}] {r.get('title', '')}\nURL: {r.get('url', '')}\n{(r.get('content') or '').strip()}"
        for i, r in enumerate(results, start=1)
    ]
    header = f"Summary from search engine: {answer}\n\n" if answer else ""
    return header + "\n\n".join(blocks), sources
