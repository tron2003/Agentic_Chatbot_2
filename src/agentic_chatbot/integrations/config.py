"""Typed loader for ``config/integrations.yaml``.

A broken integrations file never takes the API down: the error is logged,
every integration is treated as disabled, and ``/api/meta`` reports why.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator

from agentic_chatbot.core.settings import expand_env, get_settings

logger = logging.getLogger(__name__)

EVENTS = ("conversation.created", "answer.completed", "document.ingested", "document.deleted")


def _keys(value: str | None) -> set[str]:
    return {k.strip() for k in (value or "").split(",") if k.strip()}


class OpenAIApiConfig(BaseModel):
    enabled: bool = False
    model_name: str = "junction"
    api_keys: str | None = ""
    append_sources: bool = True
    persist_conversations: bool = True

    def key_set(self) -> set[str]:
        return _keys(self.api_keys) or get_settings().api_key_set


class ExternalAgentConfig(BaseModel):
    name: str
    enabled: bool = False
    label: str | None = None
    kind: Literal["openai"] = "openai"
    base_url: str
    api_key: str | None = None
    model: str = "default"
    session: Literal["per_conversation", "stateless"] = "per_conversation"
    timeout_seconds: float = Field(120, gt=0, le=900)
    headers: dict[str, str] = Field(default_factory=dict)
    description: str = "An external AI agent."

    @field_validator("name")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", v):
            raise ValueError("agent names must be lowercase letters, digits or _ (e.g. openclaw)")
        return v

    @property
    def display(self) -> str:
        return self.label or self.name.replace("_", " ").title()

    @property
    def tool_name(self) -> str:
        return f"ask_{self.name}"


class WebhookConfig(BaseModel):
    name: str
    enabled: bool = False
    format: Literal["json", "openclaw_agent"] = "json"
    url: str | None = None
    secret: str | None = None
    token: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    events: list[str] = Field(default_factory=lambda: ["*"])
    timeout_seconds: float = Field(10, gt=0, le=120)
    # openclaw_agent options
    deliver: bool = False
    channel: str | None = None
    to: str | None = None
    agent_id: str | None = None

    @field_validator("events")
    @classmethod
    def _events(cls, v: list[str]) -> list[str]:
        bad = [e for e in v if e != "*" and e not in EVENTS]
        if bad:
            raise ValueError(f"unknown webhook events {bad}; use {list(EVENTS)} or '*'")
        return v

    def wants(self, event: str) -> bool:
        return "*" in self.events or event in self.events


class McpServerConfig(BaseModel):
    enabled: bool = False
    api_keys: str | None = ""
    allowed_hosts: list[str] = Field(default_factory=list)

    def key_set(self) -> set[str]:
        return _keys(self.api_keys) or get_settings().api_key_set


class IntegrationsConfig(BaseModel):
    openai_api: OpenAIApiConfig = Field(default_factory=OpenAIApiConfig)
    agents: list[ExternalAgentConfig] = Field(default_factory=list)
    webhooks: list[WebhookConfig] = Field(default_factory=list)
    mcp_server: McpServerConfig = Field(default_factory=McpServerConfig)
    error: str | None = None

    @property
    def enabled_agents(self) -> list[ExternalAgentConfig]:
        return [a for a in self.agents if a.enabled]

    @property
    def enabled_webhooks(self) -> list[WebhookConfig]:
        return [w for w in self.webhooks if w.enabled and w.url]


def parse_integrations(raw: dict) -> IntegrationsConfig:
    raw = expand_env(raw or {})
    agents = raw.get("agents") or {}
    if isinstance(agents, dict):  # YAML mapping name -> settings
        agents = [{"name": name, **(cfg or {})} for name, cfg in agents.items()]
    return IntegrationsConfig.model_validate({**raw, "agents": agents})


@lru_cache(maxsize=1)
def get_integrations() -> IntegrationsConfig:
    path = get_settings().integrations_config_path
    if not path.exists():
        return IntegrationsConfig()
    try:
        with open(path, encoding="utf-8") as fh:
            return parse_integrations(yaml.safe_load(fh) or {})
    except (yaml.YAMLError, ValidationError, TypeError) as exc:
        logger.error("config/integrations.yaml is invalid, all integrations are off: %s", exc)
        return IntegrationsConfig(error=f"config/integrations.yaml is invalid: {str(exc).splitlines()[0]}")


def reset_integrations() -> None:
    get_integrations.cache_clear()
