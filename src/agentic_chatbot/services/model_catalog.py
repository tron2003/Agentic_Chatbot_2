"""What the model picker can offer: each provider, whether it's usable, and its models.

Model lists come from the providers themselves (Ollama's installed models,
OpenRouter's catalogue, the OpenAI/Anthropic model lists, an OpenAI-compatible
server's /models) with short timeouts, and are cached for a few minutes.
When a list can't be fetched the picker still offers the configured default
and accepts any model id typed in.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from agentic_chatbot.components.llm_loader import KEY_ENV, default_model, provider_config

logger = logging.getLogger(__name__)

LABELS = {
    "openrouter": "OpenRouter",
    "ollama": "Ollama (this computer)",
    "claude": "Anthropic Claude",
    "openai": "OpenAI",
    "local": "OpenAI-compatible server",
    "demo": "Demo (no model)",
}
ORDER = ["openrouter", "ollama", "claude", "openai", "local", "demo"]
TIMEOUT = httpx.Timeout(6.0, connect=3.0)
CACHE_SECONDS = 300

Model = dict[str, Any]  # {"id", "label"?, "free"?, "tools"?}

_cache: dict[str, tuple[float, list[Model]]] = {}


async def _openrouter(block: dict[str, Any]) -> list[Model]:
    base = str(block.get("base_url") or "https://openrouter.ai/api/v1").rstrip("/")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.get(f"{base}/models")
        res.raise_for_status()
    models = []
    for m in res.json().get("data", []):
        pricing = m.get("pricing") or {}
        free = m["id"].endswith(":free") or (str(pricing.get("prompt")) in {"0", "0.0"} and str(pricing.get("completion")) in {"0", "0.0"})
        params = m.get("supported_parameters")
        models.append({
            "id": m["id"],
            "label": m.get("name") or m["id"],
            "free": free,
            # Research needs tool calling; say so when OpenRouter tells us.
            "tools": ("tools" in params) if isinstance(params, list) else None,
        })
    return sorted(models, key=lambda m: (not m["free"], m["label"].lower()))


async def _ollama(block: dict[str, Any]) -> list[Model]:
    base = str(block.get("base_url") or "http://127.0.0.1:11434").rstrip("/")
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.get(f"{base}/api/tags")
        res.raise_for_status()
    names = [m.get("name") or m.get("model") for m in res.json().get("models", [])]
    # Embedding models can't chat.
    return [{"id": n, "label": n} for n in sorted(filter(None, names)) if "embed" not in n.lower()]


async def _openai_compatible(base: str, key: str | None) -> list[Model]:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.get(f"{base.rstrip('/')}/models", headers=headers)
        res.raise_for_status()
    return [{"id": m["id"], "label": m["id"]} for m in res.json().get("data", []) if m.get("id")]


async def _openai(block: dict[str, Any]) -> list[Model]:
    models = await _openai_compatible(str(block.get("base_url") or "https://api.openai.com/v1"), block.get("api_key"))
    chat = [m for m in models if m["id"].startswith(("gpt-", "o1", "o3", "o4", "chatgpt"))]
    return sorted(chat, key=lambda m: m["id"])


async def _local(block: dict[str, Any]) -> list[Model]:
    return await _openai_compatible(str(block.get("base_url") or "http://localhost:8000/v1"), block.get("api_key"))


async def _claude(block: dict[str, Any]) -> list[Model]:
    headers = {"x-api-key": str(block.get("api_key")), "anthropic-version": "2023-06-01"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        res = await client.get("https://api.anthropic.com/v1/models", params={"limit": 100}, headers=headers)
        res.raise_for_status()
    return [{"id": m["id"], "label": m.get("display_name") or m["id"]} for m in res.json().get("data", [])]


async def _demo(block: dict[str, Any]) -> list[Model]:
    return [{"id": "demo", "label": "Scripted demo replies"}]


FETCHERS: dict[str, Callable[[dict[str, Any]], Awaitable[list[Model]]]] = {
    "openrouter": _openrouter,
    "ollama": _ollama,
    "claude": _claude,
    "openai": _openai,
    "local": _local,
    "demo": _demo,
}


def _why_unusable(provider: str, block: dict[str, Any]) -> str | None:
    if provider in KEY_ENV and not block.get("api_key"):
        return f"Needs {KEY_ENV[provider]} in .env"
    return None


def _friendly(provider: str, exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        where = provider_config(provider).get("base_url") or "the server"
        return f"Couldn't reach {LABELS[provider]} at {where}."
    if isinstance(exc, httpx.TimeoutException):
        return f"{LABELS[provider]} took too long to list its models."
    if isinstance(exc, httpx.HTTPStatusError):
        return f"{LABELS[provider]} refused the model list ({exc.response.status_code})."
    return f"Couldn't list {LABELS[provider]} models."


async def _provider_entry(provider: str, refresh: bool) -> dict[str, Any]:
    block = provider_config(provider)
    default = default_model(provider) or ("demo" if provider == "demo" else "")
    entry: dict[str, Any] = {
        "id": provider,
        "label": LABELS[provider],
        "configured": True,
        "needs": None,
        "default_model": default,
        "models": [],
        "error": None,
    }
    needs = _why_unusable(provider, block)
    if needs:
        entry.update(configured=False, needs=needs)
        return entry

    cached = _cache.get(provider)
    if cached and not refresh and time.monotonic() - cached[0] < CACHE_SECONDS:
        entry["models"] = cached[1]
    else:
        try:
            models = await FETCHERS[provider](block)
            _cache[provider] = (time.monotonic(), models)
            entry["models"] = models
        except Exception as exc:
            logger.info("Model list for %s unavailable: %s", provider, exc)
            entry["error"] = _friendly(provider, exc)

    if default and not any(m["id"] == default for m in entry["models"]):
        entry["models"] = [{"id": default, "label": f"{default} (from config)"}, *entry["models"]]
    return entry


async def catalog(refresh: bool = False) -> list[dict[str, Any]]:
    return list(await asyncio.gather(*(_provider_entry(p, refresh) for p in ORDER)))


def clear_catalog_cache() -> None:
    _cache.clear()
