"""What the rest of the app asks about integrations: tools, titles, status."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.tools import BaseTool

from agentic_chatbot.integrations.agent_bridge import make_agent_tool, probe_agent
from agentic_chatbot.integrations.config import get_integrations
from agentic_chatbot.integrations.webhooks import dispatcher

logger = logging.getLogger(__name__)

_agent_status: dict[str, str] = {}


def agent_tools() -> list[BaseTool]:
    return [make_agent_tool(a) for a in get_integrations().enabled_agents]


def tool_titles() -> dict[str, str]:
    return {a.tool_name: f"Asking {a.display}" for a in get_integrations().enabled_agents}


def agent_capabilities() -> list[tuple[str, str]]:
    """(label, description) for the router prompt."""
    return [(a.display, a.description.strip()) for a in get_integrations().enabled_agents]


async def probe_agents() -> dict[str, str]:
    agents = get_integrations().enabled_agents
    if not agents:
        return {}
    results = await asyncio.gather(*(probe_agent(a) for a in agents))
    for agent, status in zip(agents, results, strict=True):
        _agent_status[agent.name] = status
        log = logger.info if status == "ok" else logger.warning
        log("External agent %s at %s: %s", agent.display, agent.base_url, status)
    return dict(_agent_status)


def describe(base_path: str = "") -> dict[str, Any]:
    cfg = get_integrations()
    items: list[dict[str, Any]] = []
    if cfg.openai_api.enabled:
        items.append({
            "name": "openai_api", "label": "OpenAI-compatible API", "kind": "inbound",
            "status": "ok", "detail": f"{base_path}/v1/chat/completions, model '{cfg.openai_api.model_name}'",
        })
    if cfg.mcp_server.enabled:
        items.append({"name": "mcp_server", "label": "MCP server", "kind": "inbound", "status": "ok",
                      "detail": f"{base_path}/mcp"})
    for a in cfg.enabled_agents:
        items.append({"name": a.name, "label": a.display, "kind": "agent",
                      "status": _agent_status.get(a.name, "unknown"), "detail": f"tool {a.tool_name}"})
    from agentic_chatbot.mcp.mcp_manager import mcp_manager  # imported late: the manager imports tool settings

    for name, server in mcp_manager.servers.items():
        if not server.enabled or server.status == "disabled":
            continue
        items.append({"name": f"mcp:{name}", "label": server.config.get("label") or name, "kind": "mcp",
                      "status": "ok" if server.status == "connected" else server.status,
                      "detail": f"{len(server.tools)} tools" if server.status == "connected" else server.detail})
    for w in cfg.enabled_webhooks:
        items.append({"name": w.name, "label": w.name, "kind": "webhook",
                      "status": dispatcher.last_status.get(w.name, "idle"),
                      "detail": ", ".join(w.events)})
    return {"items": items, "error": cfg.error}
