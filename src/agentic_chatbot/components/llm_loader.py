"""
LLM factory.

``get_llm("main")`` returns the answering model; ``get_llm("router")`` returns the
(optionally cheaper) model used for routing, titles and summaries. Instances are
created lazily and cached, so importing a node no longer opens network clients
or fails at import time when an API key is missing.

Which model is used, highest priority first:
1. the choice saved from the UI's model picker (services/model_selection.py);
2. LLM_PROVIDER / ROUTER_PROVIDER and the model names in .env / config.yaml.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel

from agentic_chatbot.core.settings import config_section, get_settings, reload_if_changed
from agentic_chatbot.exception.exception import LLMConfigError
from agentic_chatbot.services.model_selection import load_selection

logger = logging.getLogger(__name__)

Role = Literal["main", "router"]

_ALIASES = {"local2": "ollama", "anthropic": "claude"}
KEY_ENV = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}
_KEY_ENV = KEY_ENV  # old name, kept for imports elsewhere


def _normalise(provider: str) -> str:
    provider = str(provider).strip().lower()
    return _ALIASES.get(provider, provider)


def _ui_choice(role: Role) -> dict[str, str] | None:
    """The model picked in the UI for this role (the router falls back to the main pick)."""
    selection = load_selection()
    if not selection:
        return None
    if role == "router":
        return selection.get("router") or selection["main"]
    return selection["main"]


def selection_source() -> str:
    return "ui" if load_selection() else "env"


def _provider_name(role: Role) -> str:
    choice = _ui_choice(role)
    if choice:
        return _normalise(choice["provider"])
    cfg = config_section("llm")
    provider = get_settings().llm_provider or cfg.get("active_provider") or "claude"
    if role == "router" and cfg.get("router_provider"):
        provider = cfg["router_provider"]
    return _normalise(provider)


def provider_config(provider: str) -> dict[str, Any]:
    cfg = config_section("llm")
    block = cfg.get(provider)
    if block is None:
        # accept the legacy key name for ollama
        legacy = {v: k for k, v in _ALIASES.items()}.get(provider)
        block = cfg.get(legacy) if legacy else None
    return dict(block or {})


_provider_config = provider_config  # old name


def default_model(provider: str, role: Role = "main") -> str:
    """Model name from config.yaml / .env for this provider."""
    block = provider_config(provider)
    if role == "router" and block.get("router_model_name"):
        return str(block["router_model_name"])
    return str(block.get("model_name") or "")


def _model_name(provider: str, role: Role) -> str:
    choice = _ui_choice(role)
    if choice and _normalise(choice["provider"]) == provider and choice["model"]:
        return choice["model"]
    return default_model(provider, role)


def sync_config() -> None:
    """Pick up edits to .env / config.yaml without restarting the server."""
    if reload_if_changed():
        reset_llm_cache()


def describe_llm() -> dict[str, Any]:
    """Non-secret description of the configured models, for /api/meta."""
    sync_config()
    info: dict[str, Any] = {"source": selection_source()}
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


def build_llm(provider: str, model: str, role: Role) -> BaseChatModel:
    """Create a chat model. Raises LLMConfigError with a user-safe message when it can't."""
    provider = _normalise(provider)
    block = provider_config(provider)
    common = config_section("llm")
    timeout = float(common.get("request_timeout_seconds", 120))
    retries = int(common.get("max_retries", 2))
    temperature = float(block.get("temperature", 0.3)) if role == "main" else 0.0

    if provider == "demo":
        from agentic_chatbot.components.demo_llm import DemoChatModel

        return DemoChatModel()

    if provider in KEY_ENV and not block.get("api_key"):
        source = "The model picker" if selection_source() == "ui" else f"LLM_PROVIDER is '{provider}', which"
        raise LLMConfigError(
            f"{KEY_ENV[provider]} is not set",
            public_message=(
                f"{source} needs {KEY_ENV[provider]} for '{provider}'. Add the key to .env "
                "(saved changes apply without a restart), or choose another model."
            ),
        )
    if not model:
        raise LLMConfigError(
            f"No model_name configured for provider '{provider}'",
            public_message=f"No model is set for provider '{provider}'. Pick one in the model picker or set it in config.yaml.",
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


@lru_cache(maxsize=8)
def _cached(provider: str, model: str, role: Role) -> BaseChatModel:
    llm = build_llm(provider, model, role)
    logger.info("LLM ready", extra={"provider": provider, "role": role, "model": model})
    return llm


def get_llm(role: Role = "main") -> BaseChatModel:
    sync_config()
    provider = _provider_name(role)
    # The model is part of the cache key, so a new pick in the UI takes effect on the next request.
    return _cached(provider, _model_name(provider, role), role)


def reset_llm_cache() -> None:
    _cached.cache_clear()


class LLMLoader:
    """Backwards-compatible wrapper for code that used ``LLMLoader().load_llm()``."""

    def load_llm(self) -> BaseChatModel:
        return get_llm("main")
