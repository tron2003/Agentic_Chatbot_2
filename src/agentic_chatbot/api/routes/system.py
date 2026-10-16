"""Health, readiness and capability metadata."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from agentic_chatbot.components.llm_loader import describe_llm
from agentic_chatbot.core.settings import get_settings
from agentic_chatbot.mcp.mcp_manager import mcp_manager
from agentic_chatbot.services.knowledge_base import get_knowledge_base
from agentic_chatbot.services.store import get_store
from agentic_chatbot.tools.mcp_tools import get_agent_tools
from agentic_chatbot.tools.web_tool import web_search_available

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    """Liveness: the process is up."""
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@router.get("/ready")
async def ready(request: Request):
    """Readiness: dependencies are usable. Returns 503 when the app can't answer."""
    llm = describe_llm()
    store_ok = await get_store().ping()
    pipeline_ok = getattr(request.app.state, "pipeline", None) is not None
    checks = {
        "pipeline": pipeline_ok,
        "llm": llm["configured"],
        "store": store_ok,
    }
    body = {
        "status": "ready" if all(checks.values()) else "degraded",
        "checks": checks,
        "llm_error": llm["error"],
        "memory_backend": getattr(request.app.state, "memory_backend", "unknown"),
        "store_backend": get_store().backend,
        "vector_backend": get_knowledge_base().backend,
        "mcp": mcp_manager.status,
    }
    return JSONResponse(body, status_code=200 if all(checks.values()) else 503)


@router.get("/api/meta")
async def meta():
    """What this deployment can do; used by the UI. Contains no secrets."""
    settings = get_settings()
    llm = describe_llm()
    kb = get_knowledge_base()
    return {
        "app_name": settings.app_name,
        "version": settings.app_version,
        "model": llm["main"],
        "router_model": llm["router"],
        "llm_ready": llm["configured"],
        "llm_error": llm["error"],
        "auth_required": bool(settings.api_key_set),
        "web_search": web_search_available(),
        "tools": [t.name for t in get_agent_tools()],
        "knowledge_base": {"backend": kb.backend, "documents": len(await kb.document_names())},
        "persistence": get_store().backend,
        "limits": {"max_upload_mb": settings.max_upload_mb, "max_message_chars": settings.max_message_chars},
    }
