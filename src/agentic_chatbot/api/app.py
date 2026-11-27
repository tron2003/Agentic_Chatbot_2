"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from agentic_chatbot.api.middleware import RequestContextMiddleware
from agentic_chatbot.api.routes import chat, connections, documents, history, models, system
from agentic_chatbot.api.routes import memory as memory_routes
from agentic_chatbot.components.llm_loader import describe_llm
from agentic_chatbot.components.memory import MemoryLoader
from agentic_chatbot.core.context import get_request_id
from agentic_chatbot.core.db import check_postgres
from agentic_chatbot.core.logging import configure_logging
from agentic_chatbot.core.settings import get_settings
from agentic_chatbot.exception.exception import CustomException
from agentic_chatbot.integrations import openai_compat
from agentic_chatbot.integrations.config import get_integrations
from agentic_chatbot.integrations.mcp_server import build_mcp_server, mcp_routes
from agentic_chatbot.integrations.registry import probe_agents
from agentic_chatbot.integrations.webhooks import dispatcher
from agentic_chatbot.mcp.mcp_manager import mcp_manager
from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline
from agentic_chatbot.services.long_term_memory import set_memory_store
from agentic_chatbot.services.spreadsheets import warm_cache
from agentic_chatbot.services.store import init_store

logger = logging.getLogger("agentic_chatbot")

if sys.platform == "win32":  # psycopg's async driver needs the selector loop on Windows
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.workspace_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)

    store = await init_store()
    if settings.effective_vector_db_uri:  # warm the cached probe so /api/meta never waits on it
        await asyncio.to_thread(check_postgres, settings.effective_vector_db_uri)
    memory = MemoryLoader()
    checkpointer = await memory.load_memory()   # short-term memory (per conversation)
    long_term = await memory.load_store()       # long-term memory (across conversations)
    set_memory_store(long_term, memory.store_backend)
    await mcp_manager.initialize()

    app.state.pipeline = ChatbotPipeline(checkpointer=checkpointer, store=long_term)
    app.state.memory_backend = memory.backend
    app.state.store_backend = memory.store_backend

    llm = describe_llm()
    if llm["configured"]:
        logger.info("Ready: model %s (%s)", llm["main"]["model"], llm["main"]["provider"])
    else:
        logger.warning("Started without a usable model: %s", llm["error"])

    _warn_open_integrations()
    try:
        async with AsyncExitStack() as stack:
            mcp_server = getattr(app.state, "mcp_server", None)
            if mcp_server is not None:
                await stack.enter_async_context(mcp_server.session_manager.run())
                logger.info("MCP server listening at /mcp")
            probe = asyncio.create_task(probe_agents())  # don't block startup on slow agents
            # Parse stored spreadsheets in the background (keep a reference so the task isn't garbage-collected).
            app.state.sheet_warmup = asyncio.create_task(asyncio.to_thread(warm_cache))
            try:
                yield
            finally:
                probe.cancel()
                app.state.pipeline = None
                await dispatcher.drain()
    finally:
        set_memory_store(None)
        await memory.close()
        await store.close()
        logger.info("Shut down cleanly")


def _warn_open_integrations() -> None:
    cfg = get_integrations()
    if cfg.error:
        logger.error(cfg.error)
    if cfg.openai_api.enabled and not cfg.openai_api.key_set():
        logger.warning("OpenAI-compatible API is on without keys; set OPENAI_API_KEYS or API_KEYS before exposing it")
    if cfg.mcp_server.enabled and not cfg.mcp_server.key_set():
        logger.warning("MCP server is on without keys; set MCP_SERVER_API_KEYS or API_KEYS before exposing it")
    for agent in cfg.enabled_agents:
        logger.info("External agent enabled: %s (%s) as tool %s", agent.display, agent.base_url, agent.tool_name)


def _error(status_code: int, code: str, message: str, details: object | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": get_request_id()}}
    if details:
        body["error"]["details"] = details
    # `detail` kept for clients written against the previous API.
    body["detail"] = message
    return JSONResponse(body, status_code=status_code)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format or ("json" if settings.is_production else "text"),
        log_file=settings.log_file,
    )

    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.app_version,
        description="Agentic chatbot: routing between chat, document Q&A (RAG) and Deep research, "
                    "with short-term and long-term memory.",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else "/api/docs",
        redoc_url=None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(CustomException)
    async def _custom(_: Request, exc: CustomException):
        logger.warning("%s: %s", exc.error_code, exc.error_message)
        return _error(exc.status_code, exc.error_code, exc.public_message, exc.details or None)

    @app.exception_handler(HTTPException)
    async def _http(_: Request, exc: HTTPException):
        resp = _error(exc.status_code, f"HTTP_{exc.status_code}", str(exc.detail))
        for k, v in (exc.headers or {}).items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(p) for p in e.get("loc", [])[1:]), "message": e.get("msg", "").removeprefix("Value error, ")}
            for e in exc.errors()
        ]
        message = errors[0]["message"] if errors else "Invalid request."
        return _error(422, "VALIDATION_ERROR", message, errors)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return _error(500, "INTERNAL_ERROR", "An unexpected error occurred. Please try again.")

    app.include_router(system.router)
    app.include_router(chat.router)
    app.include_router(history.router)
    app.include_router(documents.router)
    app.include_router(models.router)
    app.include_router(memory_routes.router)
    app.include_router(connections.router)

    integrations = get_integrations()
    if integrations.openai_api.enabled:
        app.include_router(openai_compat.router)
    if integrations.mcp_server.enabled:
        server = build_mcp_server(lambda: getattr(app.state, "pipeline", None), integrations.mcp_server)
        app.state.mcp_server = server
        app.router.routes.extend(mcp_routes(server, integrations.mcp_server))

    _mount_frontend(app, settings.frontend_dist, settings.serve_frontend)
    return app


def _mount_frontend(app: FastAPI, dist: Path, enabled: bool) -> None:
    """Serve the built React app (frontend/dist) from the API for single-container deploys."""
    index = dist / "index.html"
    if not enabled or not index.exists():
        @app.get("/", include_in_schema=False)
        async def root():
            return {"name": get_settings().app_name, "status": "ok", "docs": app.docs_url}
        return

    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith(("api/", "v1/", "mcp", "docs", "openapi.json")):
            raise HTTPException(404, "Not found.")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
