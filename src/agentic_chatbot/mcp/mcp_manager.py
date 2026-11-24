"""MCP server manager.

Each server in ``config/mcp_servers.yaml`` is loaded independently with a
timeout. A server that is disabled, missing a required env var, or fails to
start is skipped with a warning instead of taking the whole API down.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from typing import Any

import yaml
from langchain_core.tools import BaseTool

from agentic_chatbot.core.settings import expand_env, get_settings

logger = logging.getLogger(__name__)

_SHELL_COMMANDS = {"npx", "npm", "node", "yarn", "pnpm"}


class MCPManager:
    def __init__(self) -> None:
        self.tools: list[BaseTool] = []
        self.status: dict[str, str] = {}

    def _load_config(self) -> dict[str, Any]:
        path = get_settings().mcp_config_path
        if not path.exists():
            return {}
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return dict(raw.get("servers") or {})

    @staticmethod
    def _prepare(cfg: dict[str, Any]) -> dict[str, Any]:
        cfg = expand_env({k: v for k, v in cfg.items() if k not in ("enabled", "requires_env")})
        if cfg.get("transport") == "stdio":
            env = {**os.environ, **{k: str(v) for k, v in (cfg.get("env") or {}).items()}}
            cfg["env"] = env
            if sys.platform == "win32" and cfg.get("command") in _SHELL_COMMANDS:
                cfg["args"] = ["/c", cfg["command"], *cfg.get("args", [])]
                cfg["command"] = "cmd"
        return cfg

    async def _load_server(self, name: str, cfg: dict[str, Any], timeout: float) -> list[BaseTool]:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient({name: cfg})
        return await asyncio.wait_for(client.get_tools(), timeout=timeout)

    async def initialize(self, timeout: float = 30.0) -> None:
        self.tools, self.status = [], {}
        if not get_settings().enable_mcp:
            logger.info("MCP disabled (ENABLE_MCP=false)")
            return
        get_settings().workspace_dir.mkdir(parents=True, exist_ok=True)

        for name, raw in self._load_config().items():
            if not raw.get("enabled", True):
                self.status[name] = "disabled"
                continue
            missing = [v for v in raw.get("requires_env", []) if not os.getenv(v)]
            if missing:
                self.status[name] = f"skipped: {', '.join(missing)} not set"
                logger.info("MCP server %s skipped (%s not set)", name, ", ".join(missing))
                continue
            if raw.get("transport") == "stdio" and not shutil.which(str(raw.get("command", ""))):
                self.status[name] = f"skipped: '{raw.get('command')}' not found on PATH"
                logger.warning("MCP server %s skipped: %s not on PATH", name, raw.get("command"))
                continue
            try:
                tools = await self._load_server(name, self._prepare(raw), timeout)
                self.tools.extend(tools)
                self.status[name] = f"ok ({len(tools)} tools)"
                logger.info("MCP server %s loaded %d tools", name, len(tools))
            except Exception as exc:  # pragma: no cover - depends on external processes
                self.status[name] = f"failed: {type(exc).__name__}"
                logger.warning("MCP server %s failed to load: %s", name, exc)

    def get_tools(self) -> list[BaseTool]:
        return list(self.tools)


mcp_manager = MCPManager()
