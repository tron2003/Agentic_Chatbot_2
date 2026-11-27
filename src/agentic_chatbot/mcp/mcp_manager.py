"""MCP server manager.

Servers come from two places: ``config/mcp_servers.yaml`` (origin ``file``) and the
Connections panel (origin ``ui``, saved in ``config/connections.json``). Each one is
loaded on its own with a timeout, so a server that is disabled, missing an env var or
failing to start is reported and skipped instead of taking the API down. Servers can
be connected, reloaded and removed one at a time while the app runs.

Every tool gets ``metadata["mcp_server"]`` so the approval policy and the UI know
where it came from.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import yaml
from langchain_core.tools import BaseTool

from agentic_chatbot.core.settings import expand_env, get_settings
from agentic_chatbot.services import connections

logger = logging.getLogger(__name__)

_SHELL_COMMANDS = {"npx", "npm", "node", "yarn", "pnpm"}
CONNECT_TIMEOUT = 30.0


@dataclass
class ServerState:
    name: str
    origin: str  # file | ui
    config: dict[str, Any]
    enabled: bool = True
    status: str = "idle"  # idle | connecting | connected | failed | skipped | disabled
    detail: str = ""
    tools: list[BaseTool] = field(default_factory=list)
    checked_at: str | None = None

    @property
    def summary(self) -> str:
        """One-line status, kept for /ready (``ok (3 tools)``, ``failed: …``)."""
        if self.status == "connected":
            return f"ok ({len(self.tools)} tools)"
        return f"{self.status}: {self.detail}" if self.detail else self.status


class MCPManager:
    def __init__(self) -> None:
        self.servers: dict[str, ServerState] = {}
        self._lock = asyncio.Lock()

    # ── configuration ────────────────────────────────────────────────────────
    def _file_config(self) -> dict[str, Any]:
        path = get_settings().mcp_config_path
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("Couldn't read %s: %s", path, exc)
            return {}
        return dict(raw.get("servers") or {})

    def configured(self) -> dict[str, ServerState]:
        """Every server from both sources, with its saved on/off state (no connection made)."""
        saved = connections.load()
        out: dict[str, ServerState] = {}
        for name, raw in self._file_config().items():
            raw = dict(raw or {})
            enabled = bool(raw.get("enabled", True))
            if name in saved["file_servers"]:
                enabled = bool(saved["file_servers"][name].get("enabled", enabled))
            out[name] = ServerState(name, "file", raw, enabled)
        for name, raw in saved["servers"].items():
            if name in out:
                logger.warning("Connections panel server '%s' has the same name as one in mcp_servers.yaml; skipped", name)
                continue
            raw = dict(raw or {})
            out[name] = ServerState(name, "ui", raw, bool(raw.get("enabled", True)))
        return out

    @staticmethod
    def _prepare(state: ServerState) -> dict[str, Any]:
        """Config for the adapter: env vars expanded, Windows shims for npx and friends."""
        if state.origin == "ui":
            cfg = connections.adapter_config(state.config)
        else:
            cfg = {k: v for k, v in state.config.items() if k not in ("enabled", "requires_env", "label")}
        cfg = expand_env(cfg)
        if cfg.get("transport") == "stdio":
            cfg["env"] = {**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}}
            if sys.platform == "win32" and cfg.get("command") in _SHELL_COMMANDS:
                cfg["args"] = ["/c", cfg["command"], *cfg.get("args", [])]
                cfg["command"] = "cmd"
        return cfg

    @staticmethod
    def _precheck(state: ServerState) -> tuple[str, str] | None:
        """(status, detail) when the server can't be started, else None."""
        if not get_settings().enable_mcp:
            return "disabled", "MCP is off (ENABLE_MCP=false)"
        if not state.enabled:
            return "disabled", "switched off"
        missing = [v for v in state.config.get("requires_env", []) if not os.getenv(v)]
        if missing:
            return "skipped", f"{', '.join(missing)} not set"
        if state.config.get("transport") == "stdio" and not shutil.which(str(state.config.get("command", ""))):
            return "skipped", f"'{state.config.get('command')}' not found on PATH"
        return None

    async def _load_server(self, name: str, cfg: dict[str, Any], timeout: float) -> list[BaseTool]:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient({name: cfg})
        return await asyncio.wait_for(client.get_tools(), timeout=timeout)

    async def _connect(self, state: ServerState, timeout: float) -> ServerState:
        state.tools, state.checked_at = [], datetime.now(UTC).isoformat()
        blocked = self._precheck(state)
        if blocked:
            state.status, state.detail = blocked
            return state
        state.status, state.detail = "connecting", ""
        try:
            tools = await self._load_server(state.name, self._prepare(state), timeout)
        except TimeoutError:
            state.status, state.detail = "failed", f"no answer within {timeout:.0f}s"
            logger.warning("MCP server %s timed out", state.name)
            return state
        except Exception as exc:  # depends on external processes
            state.status, state.detail = "failed", _reason(exc)
            logger.warning("MCP server %s failed to load: %s", state.name, exc)
            return state
        for tool in tools:
            tool.metadata = {**(tool.metadata or {}), "mcp_server": state.name}
        state.tools, state.status, state.detail = list(tools), "connected", ""
        logger.info("MCP server %s loaded %d tools", state.name, len(tools))
        return state

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def initialize(self, timeout: float = CONNECT_TIMEOUT) -> None:
        async with self._lock:
            states = self.configured()
            if not get_settings().enable_mcp:
                logger.info("MCP disabled (ENABLE_MCP=false)")
            get_settings().workspace_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.gather(*(self._connect(s, timeout) for s in states.values()))
            self.servers = states

    async def reload(self, name: str, timeout: float = CONNECT_TIMEOUT) -> ServerState | None:
        """Re-read one server's settings and connect it again (or drop it if it was removed)."""
        async with self._lock:
            state = self.configured().get(name)
            if state is None:
                self.servers.pop(name, None)
                return None
            self.servers[name] = await self._connect(state, timeout)
            return self.servers[name]

    def remove(self, name: str) -> None:
        self.servers.pop(name, None)

    async def test(self, name: str, config: dict[str, Any], timeout: float = 20.0) -> ServerState:
        """Connect to a server that isn't saved yet and report what it offers."""
        state = ServerState(name, "ui", config, True)
        return await self._connect(state, timeout)

    # ── reads ────────────────────────────────────────────────────────────────
    def get_tools(self) -> list[BaseTool]:
        return [t for s in self.servers.values() if s.status == "connected" for t in s.tools]

    @property
    def status(self) -> dict[str, str]:
        return {name: s.summary for name, s in self.servers.items()}

    def state(self, name: str) -> ServerState | None:
        return self.servers.get(name)


def _reason(exc: BaseException) -> str:
    """A short, readable cause; ExceptionGroups from anyio wrap the real one."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    text = str(exc).strip().splitlines()[0][:200] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


mcp_manager = MCPManager()
