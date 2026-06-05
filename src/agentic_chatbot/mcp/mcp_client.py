from langchain_mcp_adapters.client import MultiServerMCPClient


async def create_mcp_client(server_config: dict):
    return MultiServerMCPClient(server_config)
