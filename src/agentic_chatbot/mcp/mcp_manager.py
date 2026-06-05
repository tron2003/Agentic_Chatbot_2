import os

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
            return os.getenv(obj[2:-1])

        return obj

    async def initialize(self):

        config = load_mcp_config("config/mcp_servers.yaml")

        servers = self._resolve_env(config["servers"])

        client = await create_mcp_client(servers)

        self.tools = await client.get_tools()

        print("\nLoaded MCP Tools")

        for tool in self.tools:
            print(f" - {tool.name}")

    def get_tools(self):
        return self.tools


mcp_manager = MCPManager()
