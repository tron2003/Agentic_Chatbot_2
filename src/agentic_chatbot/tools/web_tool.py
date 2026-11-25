"""Web search tool: Tavily when a key is set, DuckDuckGo otherwise or as a fallback.

Returns readable text for the model *and* the structured results as the tool
message artifact, so the UI can show proper source links.

Which provider is used comes from ``agent.web_search`` in config.yaml
(``WEB_SEARCH_PROVIDER`` in .env):

* ``auto`` (default): Tavily if TAVILY_API_KEY is set, else DuckDuckGo. If
  Tavily fails or finds nothing, DuckDuckGo is tried before giving up.
* ``tavily`` / ``duckduckgo``: only that provider.
* ``off``: no web search.

DuckDuckGo needs no key (package ``ddgs``) but is rate limited and less
thorough than Tavily, so Tavily stays first when it's available.
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import time
from functools import lru_cache
from typing import Any

from langchain_core.tools import tool

from agentic_chatbot.core.settings import config_section

logger = logging.getLogger(__name__)

PROVIDER_LABELS = {"tavily": "Tavily", "duckduckgo": "DuckDuckGo"}


def _tavily_key() -> str:
    return os.getenv("TAVILY_API_KEY") or ""


@lru_cache(maxsize=1)
def duckduckgo_installed() -> bool:
    return importlib.util.find_spec("ddgs") is not None or importlib.util.find_spec("duckduckgo_search") is not None


def _preference() -> str:
    raw = config_section("agent").get("web_search", "auto")
    if isinstance(raw, bool):  # YAML reads a bare `off` / `no` as False
        return "auto" if raw else "off"
    pref = str(raw or "auto").strip().lower()
    return pref if pref in {"auto", "tavily", "duckduckgo", "off"} else "auto"


def web_search_providers() -> list[str]:
    """Providers to try, in order. Empty when web search is off or unavailable."""
    pref = _preference()
    tavily = bool(_tavily_key())
    ddg = duckduckgo_installed()
    if pref == "off":
        return []
    if pref == "tavily":
        return ["tavily"] if tavily else []
    if pref == "duckduckgo":
        return ["duckduckgo"] if ddg else []
    return [p for p, ok in (("tavily", tavily), ("duckduckgo", ddg)) if ok]


def web_search_available() -> bool:
    return bool(web_search_providers())


def web_search_provider_label() -> str | None:
    """Name of the first provider, for /api/meta and the UI."""
    providers = web_search_providers()
    return PROVIDER_LABELS[providers[0]] if providers else None


def _max_results() -> int:
    return int(config_section("agent").get("web_results", 5))


def _client():
    # Keyed by the key itself, so a TAVILY_API_KEY added or changed in .env is used without a restart.
    return _client_for(_tavily_key())


@lru_cache(maxsize=2)
def _client_for(api_key: str):
    from langchain_tavily import TavilySearch

    return TavilySearch(api_key=api_key, max_results=_max_results(), search_depth="advanced")


def _normalise(raw: Any) -> tuple[str | None, list[dict]]:
    if isinstance(raw, list):
        return None, raw
    if isinstance(raw, dict):
        return raw.get("answer"), list(raw.get("results") or [])
    return None, []


async def _search_tavily(query: str) -> tuple[str | None, list[dict]]:
    return _normalise(await _client().ainvoke({"query": query}))


# ddgs is free but flaky: it answers "No results found." when a search engine
# rate-limits it, and which engine answers varies. Try a few before giving up.
DDG_BACKENDS = ("auto", "bing", "duckduckgo")
DDG_RETRY_DELAY = 0.8


def _ddg_text(query: str, max_results: int) -> list[dict]:
    try:
        from ddgs import DDGS
    except ImportError:  # older package name
        from duckduckgo_search import DDGS
    error: Exception | None = None
    for i, backend in enumerate(DDG_BACKENDS):
        if i:
            time.sleep(DDG_RETRY_DELAY)
        try:
            results = DDGS().text(query, max_results=max_results, backend=backend)
        except Exception as exc:
            if "no results" not in str(exc).lower():
                error = exc
            continue
        if results:
            return list(results)
    if error:
        raise error
    return []


async def _search_duckduckgo(query: str) -> tuple[str | None, list[dict]]:
    raw = await asyncio.to_thread(_ddg_text, query, _max_results())
    # Same shape as Tavily results: title, url, content.
    return None, [{"title": r.get("title", ""), "url": r.get("href", ""), "content": r.get("body", "")} for r in raw]


SEARCHERS = {"tavily": _search_tavily, "duckduckgo": _search_duckduckgo}


def _format(answer: str | None, results: list[dict], provider: str) -> tuple[str, list[dict]]:
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
    footer = f"\n\n(Results from {PROVIDER_LABELS[provider]}.)"
    return header + "\n\n".join(blocks) + footer, sources


@tool(response_format="content_and_artifact")
async def web_search(query: str) -> tuple[str, list[dict]]:
    """Search the web for current information: news, recent events, releases, prices, sports,
    people's current roles, or any fact that may have changed. Input is a focused search query."""
    providers = web_search_providers()
    if not providers:
        return "Web search is not configured on this server.", []

    problems: list[str] = []
    for provider in providers:
        try:
            answer, results = await SEARCHERS[provider](query)
        except Exception as exc:
            logger.warning("Web search via %s failed: %s", provider, exc)
            problems.append(f"{PROVIDER_LABELS[provider]} failed ({type(exc).__name__})")
            continue
        if results:
            if problems:
                logger.info("Web search fell back to %s", provider)
            return _format(answer, results, provider)
        problems.append(f"{PROVIDER_LABELS[provider]} found nothing")

    return "No results: " + "; ".join(problems) + ". Try a different or broader query.", []
