"""
LLM factory.

``get_llm("main")`` returns the answering model; ``get_llm("router")`` returns the
(optionally cheaper) model used for routing, titles and summaries. Instances are
created lazily and cached, so importing a node no longer opens network clients
or fails at import time when an API key is missing.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel

from agentic_chatbot.core.settings import config_section, get_settings, reload_if_changed
from agentic_chatbot.exception.exception import LLMConfigError

logger = logging.getLogger(__name__)

Role = Literal["main", "router"]

_ALIASES = {"local2": "ollama", "anthropic": "claude"}
_KEY_ENV = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _provider_name(role: Role) -> str:
    cfg = config_section("llm")
    provider = get_settings().llm_provider or cfg.get("active_provider") or "claude"
    if role == "router" and cfg.get("router_provider"):
        provider = cfg["router_provider"]
    provider = str(provider).strip().lower()
    return _ALIASES.get(provider, provider)


def _provider_config(provider: str) -> dict[str, Any]:
    cfg = config_section("llm")
    block = cfg.get(provider)
    if block is None:
        # accept the legacy key name for ollama
        legacy = {v: k for k, v in _ALIASES.items()}.get(provider)
        block = cfg.get(legacy) if legacy else None
    return dict(block or {})


def _model_name(provider: str, role: Role) -> str:
    block = _provider_config(provider)
    if role == "router" and block.get("router_model_name"):
        return str(block["router_model_name"])
    return str(block.get("model_name") or "")


def sync_config() -> None:
    """Pick up edits to .env / config.yaml without restarting the server."""
    if reload_if_changed():
        reset_llm_cache()


def describe_llm() -> dict[str, Any]:
    """Non-secret description of the configured models, for /api/meta."""
    sync_config()
    info: dict[str, Any] = {}
    for role in ("main", "router"):
        provider = _provider_name(role)  # type: ignore[arg-type]
        info[role] = {"provider": provider, "model": _model_name(provider, role) or provider}  # type: ignore[arg-type]
    try:
        get_llm("main")
        info["configured"] = True
        info["error"] = None
    except LLMConfigError as exc:
        info["configured"] = False
        info["error"] = exc.public_message
    return info


def _build(provider: str, role: Role) -> BaseChatModel:
    block = _provider_config(provider)
    common = config_section("llm")
    timeout = float(common.get("request_timeout_seconds", 120))
    retries = int(common.get("max_retries", 2))
    model = _model_name(provider, role)
    temperature = float(block.get("temperature", 0.3)) if role == "main" else 0.0

    if provider == "demo":
        from agentic_chatbot.components.demo_llm import DemoChatModel

        return DemoChatModel()

    if provider in _KEY_ENV and not block.get("api_key"):
        raise LLMConfigError(
            f"{_KEY_ENV[provider]} is not set",
            public_message=(
                f"LLM_PROVIDER is '{provider}', which needs {_KEY_ENV[provider]}. Add the key to .env, "
                "or change LLM_PROVIDER (demo works without a key). Saved changes apply without a restart."
            ),
        )
    if not model:
        raise LLMConfigError(
            f"No model_name configured for provider '{provider}'",
            public_message=f"config.yaml has no model_name for provider '{provider}'.",
        )

    if provider == "claude":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            api_key=block["api_key"],
            temperature=temperature,
            max_tokens=int(block.get("max_tokens", 4096)) if role == "main" else 1024,
            timeout=timeout,
            max_retries=retries,
        )

    if provider in ("openai", "openrouter", "local"):
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = dict(
            model=model,
            api_key=block.get("api_key") or "not-needed",
            temperature=temperature,
            timeout=timeout,
            max_retries=retries,
        )
        if block.get("base_url"):
            kwargs["base_url"] = block["base_url"]
        return ChatOpenAI(**kwargs)

    if provider == "ollama":
        from langchain_ollama import ChatOllama

        kwargs = dict(model=model, base_url=block.get("base_url"), temperature=temperature)
        if "reasoning" in block and "reasoning" in ChatOllama.model_fields:
            kwargs["reasoning"] = bool(block["reasoning"])
        return ChatOllama(**kwargs)

    raise LLMConfigError(
        f"Unknown LLM provider: {provider}",
        public_message=(
            f"Unknown LLM provider '{provider}'. Use one of: claude, openai, openrouter, ollama, local, demo."
        ),
    )


@lru_cache(maxsize=4)
def _cached(provider: str, role: Role) -> BaseChatModel:
    llm = _build(provider, role)
    logger.info("LLM ready", extra={"provider": provider, "role": role, "model": _model_name(provider, role)})
    return llm


def get_llm(role: Role = "main") -> BaseChatModel:
    sync_config()
    return _cached(_provider_name(role), role)


def reset_llm_cache() -> None:
    _cached.cache_clear()


class LLMLoader:
    """Backwards-compatible wrapper for code that used ``LLMLoader().load_llm()``."""

    def load_llm(self) -> BaseChatModel:
        return get_llm("main")
