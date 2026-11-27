"""Connections panel API: MCP servers, their tools, and which tools need approval.

    GET    /api/connections                  servers (both sources), tools, settings
    POST   /api/connections/test             try a server without saving it
    POST   /api/connections                  add a server (saved, then connected)
    PUT    /api/connections/{name}           change a server added in the app
    PATCH  /api/connections/{name}           switch any server on or off
    DELETE /api/connections/{name}           remove a server added in the app
    POST   /api/connections/{name}/reconnect connect again
    PUT    /api/connections/tools            Always allow / Ask first / Off for one tool
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from agentic_chatbot.api.security import require_api_key
from agentic_chatbot.core.settings import get_settings
from agentic_chatbot.mcp.mcp_manager import ServerState, mcp_manager
from agentic_chatbot.services import connections
from agentic_chatbot.services.connections import ServerIn, mask, unmask
from agentic_chatbot.services.tool_policy import approvals_on, describe_tool, server_of
from agentic_chatbot.tools.mcp_tools import all_agent_tools

router = APIRouter(prefix="/api/connections", tags=["connections"], dependencies=[Depends(require_api_key)])

STDIO_OFF = (
    "Adding local (command) servers from the app is turned off on this server, because they run a program here. "
    "Add it to config/mcp_servers.yaml instead, or set ALLOW_UI_STDIO=true in .env."
)


class EnabledIn(BaseModel):
    enabled: bool


class ToolSettingIn(BaseModel):
    key: str = Field(..., min_length=3, max_length=200, pattern=r"^[A-Za-z0-9_\-.]+/[A-Za-z0-9_\-.:]+$")
    setting: Literal["auto", "ask", "off"] | None = Field(None, description="null = the default for the tool's kind")


def _transport(cfg: dict) -> str:
    t = str(cfg.get("transport") or ("stdio" if cfg.get("command") else "http")).lower()
    return "stdio" if t == "stdio" else ("sse" if t == "sse" else "http")


def _view(conf: ServerState, live: ServerState | None, settings: dict[str, str]) -> dict:
    cfg = conf.config
    if live is None:
        state, detail, tools, checked = ("disabled" if not conf.enabled else "idle"), "", [], None
    else:
        state, detail, tools, checked = live.status, live.detail, live.tools, live.checked_at
    return {
        "name": conf.name,
        "label": cfg.get("label") or conf.name,
        "origin": conf.origin,  # file = config/mcp_servers.yaml, ui = added in the app
        "editable": conf.origin == "ui",
        "transport": _transport(cfg),
        "url": cfg.get("url"),
        "command": cfg.get("command"),
        "args": list(cfg.get("args") or []),
        "headers": mask(cfg.get("headers")),
        "env": mask(cfg.get("env")),
        "enabled": conf.enabled,
        "status": state,
        "detail": detail,
        "checked_at": checked,
        "tools": [describe_tool(t, settings) for t in tools],
    }


def _server(name: str) -> dict:
    conf = mcp_manager.configured().get(name)
    if conf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There's no server called '{name}'.")
    return _view(conf, mcp_manager.state(name), connections.tool_settings())


def _check_stdio(body: ServerIn) -> None:
    if body.transport == "stdio" and not get_settings().ui_stdio_allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, STDIO_OFF)


@router.get("")
async def list_connections():
    settings = connections.tool_settings()
    configured = mcp_manager.configured()
    builtin = [t for t in all_agent_tools(include_kb=True) if server_of(t) in ("builtin", "agents")]
    return {
        "mcp_enabled": get_settings().enable_mcp,
        "stdio_allowed": get_settings().ui_stdio_allowed,
        "approvals": approvals_on(),
        "servers": [_view(c, mcp_manager.state(n), settings) for n, c in configured.items()],
        "builtin": [describe_tool(t, settings) for t in builtin],
    }


@router.post("/test")
async def test_connection(body: ServerIn):
    """Connect once and list the tools, without saving anything."""
    _check_stdio(body)
    state = await mcp_manager.test(body.name, body.stored())
    return {"status": state.status, "detail": state.detail,
            "tools": [describe_tool(t, connections.tool_settings()) for t in state.tools]}


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_connection(body: ServerIn):
    """Save a server and connect it. It's saved even if the first connection fails, so it can be fixed."""
    _check_stdio(body)
    if body.name in mcp_manager.configured():
        raise HTTPException(status.HTTP_409_CONFLICT, f"A server called '{body.name}' already exists. Pick another name.")
    data = connections.load()
    data["servers"][body.name] = body.stored()
    connections.save(data)
    await mcp_manager.reload(body.name)
    return _server(body.name)


@router.put("/tools")
async def set_tool(body: ToolSettingIn):
    """Always allow (auto), Ask first (ask) or Off for one tool. Declared before /{name}, which would match it."""
    connections.set_tool_setting(body.key, body.setting)
    return {"key": body.key, "setting": body.setting}


@router.put("/{name}")
async def update_connection(name: str, body: ServerIn):
    conf = mcp_manager.configured().get(name)
    if conf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There's no server called '{name}'.")
    if conf.origin != "ui":
        raise HTTPException(status.HTTP_409_CONFLICT, "This server comes from config/mcp_servers.yaml. Edit it there.")
    _check_stdio(body)
    old = conf.config
    stored = body.stored()
    if stored.get("headers"):
        stored["headers"] = unmask(stored["headers"], old.get("headers"))
    if stored.get("env"):
        stored["env"] = unmask(stored["env"], old.get("env"))
    data = connections.load()
    data["servers"][name] = stored
    connections.save(data)
    await mcp_manager.reload(name)
    return _server(name)


@router.patch("/{name}")
async def switch_connection(name: str, body: EnabledIn):
    conf = mcp_manager.configured().get(name)
    if conf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There's no server called '{name}'.")
    data = connections.load()
    if conf.origin == "ui":
        data["servers"][name]["enabled"] = body.enabled
    else:
        data["file_servers"][name] = {"enabled": body.enabled}
    connections.save(data)
    await mcp_manager.reload(name)
    return _server(name)


@router.delete("/{name}")
async def delete_connection(name: str):
    conf = mcp_manager.configured().get(name)
    if conf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There's no server called '{name}'.")
    if conf.origin != "ui":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This server comes from config/mcp_servers.yaml. Switch it off here, or remove it there.")
    data = connections.load()
    data["servers"].pop(name, None)
    data["tools"] = {k: v for k, v in data["tools"].items() if not k.startswith(f"{name}/")}
    connections.save(data)
    mcp_manager.remove(name)
    return {"deleted": name}


@router.post("/{name}/reconnect")
async def reconnect(name: str):
    if name not in mcp_manager.configured():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"There's no server called '{name}'.")
    await mcp_manager.reload(name)
    return _server(name)
