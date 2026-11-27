"""
MCP servers added in the UI, and per-tool settings, saved as JSON.

``config/connections.json`` by default (``CONNECTIONS_PATH`` to move it), git-ignored
like ``model_selection.json``. Servers from ``config/mcp_servers.yaml`` are not copied
here: only whether they are switched on. Shape:

    {
      "servers": {"notes": {"transport": "http", "url": "https://…/mcp", "headers": {...}, "enabled": true}},
      "file_servers": {"github": {"enabled": false}},
      "tools": {"github/create_issue": "ask", "builtin/web_search": "off"},
      "updated_at": "…"
    }

Tool settings: ``auto`` (run without asking), ``ask`` (wait for approval) or ``off``
(hidden from the agent). A tool with no entry uses the default for its kind.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from agentic_chatbot.core.settings import PROJECT_ROOT

logger = logging.getLogger(__name__)

ToolSetting = Literal["auto", "ask", "off"]
TOOL_SETTINGS: tuple[str, ...] = ("auto", "ask", "off")

# Shown in place of secret env and header values. Sending it back means "keep the stored value".
MASK = "••••••••"
_ENV_REF = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}$")
NAME_PATTERN = r"^[a-z][a-z0-9_-]{1,39}$"
RESERVED_NAMES = {"tools", "test", "builtin", "agents"}

_lock = threading.Lock()
_cache: tuple[str, int, dict[str, Any]] | None = None  # (path, mtime_ns, data)


def connections_path() -> Path:
    return Path(os.environ.get("CONNECTIONS_PATH") or PROJECT_ROOT / "config" / "connections.json")


def _empty() -> dict[str, Any]:
    return {"servers": {}, "file_servers": {}, "tools": {}}


def load() -> dict[str, Any]:
    """The saved connections (a copy). Re-read only when the file changes."""
    global _cache
    path = connections_path()
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return _empty()
    if _cache and _cache[0] == str(path) and _cache[1] == mtime:
        return deepcopy(_cache[2])
    data = _empty()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for key in data:
            if isinstance(raw.get(key), dict):
                data[key] = raw[key]
        data["tools"] = {k: v for k, v in data["tools"].items() if v in TOOL_SETTINGS}
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning("Ignoring unreadable connections file %s: %s", path, exc)
    with _lock:
        _cache = (str(path), mtime, data)
    return deepcopy(data)


def save(data: dict[str, Any]) -> None:
    global _cache
    path = connections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {**{k: data.get(k) or {} for k in ("servers", "file_servers", "tools")},
            "updated_at": datetime.now(UTC).isoformat()}
    tmp = path.with_suffix(".tmp")
    with _lock:
        tmp.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)  # atomic, so a reader never sees half a file
        # Two saves can land in the same file-time tick on Windows, so never trust the mtime cache after our own write.
        _cache = None


# ── tool settings ────────────────────────────────────────────────────────────

def tool_settings() -> dict[str, str]:
    return load()["tools"]


def set_tool_setting(key: str, setting: str | None) -> None:
    """``setting=None`` goes back to the default for the tool's kind."""
    data = load()
    if setting is None:
        data["tools"].pop(key, None)
    else:
        data["tools"][key] = setting
    save(data)


# ── servers ──────────────────────────────────────────────────────────────────

def is_secret_ref(value: str) -> bool:
    """``${VAR}`` references are shown as they are; only literal values are secret."""
    return bool(_ENV_REF.match(value or ""))


def mask(values: dict[str, str] | None) -> dict[str, str]:
    return {k: (v if is_secret_ref(str(v)) else MASK) for k, v in (values or {}).items()}


def unmask(new: dict[str, str] | None, old: dict[str, str] | None) -> dict[str, str]:
    """Values sent back as MASK keep what was stored."""
    old = old or {}
    return {k: (old.get(k, "") if v == MASK else v) for k, v in (new or {}).items()}


class ServerIn(BaseModel):
    """An MCP server added from the Connections panel."""

    name: str = Field(..., pattern=NAME_PATTERN, description="Lowercase letters, digits, - and _; starts with a letter")
    label: str | None = Field(None, max_length=60)
    transport: Literal["http", "sse", "stdio"] = "http"
    url: str | None = Field(None, max_length=500)
    headers: dict[str, str] = Field(default_factory=dict)
    command: str | None = Field(None, max_length=200)
    args: list[str] = Field(default_factory=list, max_length=40)
    env: dict[str, str] = Field(default_factory=dict)
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if v in RESERVED_NAMES:
            raise ValueError(f"'{v}' is reserved; pick another name")
        return v

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        v = (v or "").strip() or None
        if v and not re.match(r"^https?://", v):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("headers", "env")
    @classmethod
    def _keys(cls, v: dict[str, str]) -> dict[str, str]:
        clean = {}
        for key, value in v.items():
            key = key.strip()
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_\-]{0,80}$", key):
                raise ValueError(f"'{key}' isn't a valid name")
            clean[key] = str(value)
        return clean

    @model_validator(mode="after")
    def _shape(self) -> ServerIn:
        if self.transport == "stdio":
            if not (self.command or "").strip():
                raise ValueError("A command is required for a local (stdio) server")
            if re.search(r"[\s;&|<>`$]", self.command.strip()):
                raise ValueError("Put only the program in Command (like npx or uvx) and each argument on its own line")
            self.command = self.command.strip()
            self.url, self.headers = None, {}
        else:
            if not self.url:
                raise ValueError("A URL is required for a remote server")
            self.command, self.args, self.env = None, [], {}
        return self

    def stored(self) -> dict[str, Any]:
        """What goes in connections.json."""
        data = self.model_dump(exclude={"name"}, exclude_none=True)
        return {k: v for k, v in data.items() if v not in ({}, [])}


def adapter_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Map a stored server to the dict langchain-mcp-adapters expects."""
    transport = cfg.get("transport", "http")
    if transport == "stdio":
        out: dict[str, Any] = {"transport": "stdio", "command": cfg["command"], "args": list(cfg.get("args") or [])}
        if cfg.get("env"):
            out["env"] = dict(cfg["env"])
        return out
    out = {"transport": "streamable_http" if transport == "http" else "sse", "url": cfg["url"]}
    if cfg.get("headers"):
        out["headers"] = dict(cfg["headers"])
    return out
