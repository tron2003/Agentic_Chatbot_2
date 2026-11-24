"""
Expose Junction as an MCP server (streamable HTTP at ``/mcp``).

Any MCP client (Claude Desktop, Hermes Agent, Cursor, OpenClaw via an MCP
bridge, custom agents) gets three tools:

    ask                – ask Junction a question (routing, documents, research)
    search_documents   – search the document library directly
    list_documents     – list what's in the library

The server is stateless (no MCP session affinity), so it works behind several
workers. Auth uses ``mcp_server.api_keys`` or, if empty, the app's API_KEYS.
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import Callable
from typing import Any

from starlette.responses import JSONResponse
from starlette.routing import Route

from agentic_chatbot.core.settings import get_settings
from agentic_chatbot.integrations.config import McpServerConfig
from agentic_chatbot.services.chat_service import TurnError, prepare_turn
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.services.store import get_store

logger = logging.getLogger(__name__)


def build_mcp_server(get_pipeline: Callable[[], Any], cfg: McpServerConfig):
    from mcp.server.fastmcp import FastMCP
    from mcp.server.transport_security import TransportSecuritySettings

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=bool(cfg.allowed_hosts),
        allowed_hosts=list(cfg.allowed_hosts),
        allowed_origins=[f"https://{h}" for h in cfg.allowed_hosts] + [f"http://{h}" for h in cfg.allowed_hosts],
    )
    mcp = FastMCP(
        name=get_settings().app_name,
        instructions=(
            "Junction is the user's assistant with a document library and research tools. "
            "Use `ask` for questions (it decides whether to answer directly, search the user's documents, "
            "or research with tools) and pass conversation_id back for follow-ups. "
            "Use `search_documents` to pull raw passages from the user's files."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        transport_security=security,
    )

    @mcp.tool(
        description=(
            "Ask Junction a question. It routes to a direct answer, the user's document library (with citations) "
            "or web/tool research, and returns the answer with its sources. Pass the returned conversation_id to "
            "continue the same conversation."
        )
    )
    async def ask(question: str, conversation_id: str | None = None) -> dict[str, Any]:
        pipeline = get_pipeline()
        if pipeline is None:
            return {"error": "Junction is still starting."}
        try:
            turn = await prepare_turn(pipeline, get_store(), conversation_id=conversation_id,
                                      message=question.strip(), source="mcp")
        except TurnError as exc:
            return {"error": exc.message}
        result: dict[str, Any] = {"conversation_id": turn.conversation_id}
        async for ev in turn.events():
            if ev["type"] == "error":
                return {**result, "error": ev["message"]}
            if ev["type"] == "done":
                meta = ev["message"]["metadata"]
                result.update(
                    answer=ev["message"]["content"],
                    route=meta.get("route"),
                    sources=[{k: s.get(k) for k in ("title", "url", "page") if s.get(k)} for s in meta.get("sources", [])],
                )
        return result

    @mcp.tool(description="Search the user's document library and return the most relevant passages.")
    async def search_documents(query: str, limit: int = 5) -> list[dict[str, Any]]:
        docs = await get_knowledge_base().search(query)
        return [
            {"document": d.metadata.get("source_name"), "page": d.metadata.get("page"), "text": d.page_content}
            for d in docs[: max(1, min(limit, 10))]
        ]

    @mcp.tool(description="List the documents in the user's library.")
    async def list_documents() -> list[dict[str, Any]]:
        return [{"id": d["id"], "name": d["name"], "passages": d["chunks"]} for d in await get_store().list_documents()]

    return mcp


class _RequireKey:
    """ASGI wrapper enforcing a bearer key in front of the MCP endpoint."""

    def __init__(self, app, cfg: McpServerConfig):
        self.app = app
        self.cfg = cfg

    async def __call__(self, scope, receive, send):
        keys = self.cfg.key_set()
        if keys and scope["type"] == "http":
            headers = dict(scope.get("headers") or [])
            auth = headers.get(b"authorization", b"").decode("latin-1")
            presented = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
            if not any(hmac.compare_digest(presented, k) for k in keys):
                response = JSONResponse(
                    {"error": {"code": "HTTP_401", "message": "Missing or invalid API key."}},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
                return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def mcp_routes(mcp, cfg: McpServerConfig) -> list[Route]:
    """The FastMCP app's routes, each wrapped with key auth, ready to add to FastAPI."""
    routes = []
    for route in mcp.streamable_http_app().routes:
        if isinstance(route, Route):
            routes.append(Route(route.path, endpoint=_RequireKey(route.app, cfg), methods=route.methods,
                                name="mcp", include_in_schema=False))
    return routes
