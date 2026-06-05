from agentic_chatbot.mcp.client import create_mcp_client
from agentic_chatbot.utils.config_loader import load_mcp_tools


async def load_mcp_tools():

    config = load_mcp_config(
        "src/agentic_chatbot/config/mcp_servers.yaml"
    )

    client = await create_mcp_client(config)

    tools = await client.get_tools()

    return tools