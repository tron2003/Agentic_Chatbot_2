import os
import sys

from agentic_chatbot.utils.config_loader import (
    load_mcp_config,
)

from agentic_chatbot.mcp.mcp_client import (
    create_mcp_client,
)


class MCPManager:

    def __init__(self):
        self.tools = []

    def _resolve_env(self, obj):

        if isinstance(obj, dict):
            return {k: self._resolve_env(v) for k, v in obj.items()}

        if isinstance(obj, list):
            return [self._resolve_env(v) for v in obj]

        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_value = os.getenv(obj[2:-1])
            if env_value is None:
                print(f"Warning: Environment variable {obj[2:-1]} not set, using empty string")
                return ""
            return env_value

        return obj

    def _fix_windows_commands(self, servers: dict) -> dict:
        """On Windows, wrap bare commands like 'npx' with 'cmd /c' so .cmd scripts resolve."""
        if sys.platform != "win32":
            return servers
        needs_shell = {"npx", "npm", "node", "yarn", "pnpm"}
        fixed = {}
        for name, cfg in servers.items():
            cfg = dict(cfg)
            cmd = cfg.get("command", "")
            if cmd in needs_shell:
                cfg["args"] = ["/c", cmd] + list(cfg.get("args", []))
                cfg["command"] = "cmd"
            fixed[name] = cfg
        return fixed

    async def initialize(self):

        config = load_mcp_config("config/mcp_servers.yaml")

        servers = self._resolve_env(config["servers"])
        servers = self._fix_windows_commands(servers)

        client = await create_mcp_client(servers)

        self.tools = await client.get_tools()

        print("\nLoaded MCP Tools")

        for tool in self.tools:
            print(f" - {tool.name}")

    def get_tools(self):
        return self.tools


mcp_manager = MCPManager()
