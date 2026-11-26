"""Chat endpoints: streaming (SSE) and plain JSON."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from agentic_chatbot.api.schemas import ChatRequest, ChatResponse
from agentic_chatbot.api.security import rate_limit, require_api_key
from agentic_chatbot.core.context import get_request_id
from agentic_chatbot.services.chat_service import ChatTurn, TurnError, prepare_turn
from agentic_chatbot.services.store import get_store

router = APIRouter(tags=["chat"], dependencies=[Depends(require_api_key)])


def _pipeline(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant is still starting. Try again shortly.")
    return pipeline


async def _prepare_turn(body: ChatRequest, request: Request) -> ChatTurn:
    try:
        return await prepare_turn(
            _pipeline(request),
            get_store(),
            conversation_id=body.conversation_id,
            message=body.message,
            regenerate=body.regenerate,
            attachments=[a.model_dump() for a in body.attachments],
            mode=body.mode,
        )
    except TurnError as exc:
        raise HTTPException(exc.status, exc.message)


async def _sse(turn: ChatTurn) -> AsyncIterator[str]:
    yield "retry: 3000\n\n"
    async for event in turn.events():
        if event["type"] == "ping":
            yield ": ping\n\n"
        else:
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/api/chat/stream", dependencies=[Depends(rate_limit)])
async def chat_stream(body: ChatRequest, request: Request) -> StreamingResponse:
    """Stream a reply as Server-Sent Events (route, reasoning steps, tokens, sources, done)."""
    turn = await _prepare_turn(body, request)
    return StreamingResponse(
        _sse(turn),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(rate_limit)])
async def chat(body: ChatRequest, request: Request) -> ChatResponse:
    """Non-streaming reply. Same pipeline as the stream, returned in one JSON object."""
    turn = await _prepare_turn(body, request)
    title: str | None = None
    async for event in turn.events():
        if event["type"] == "title":
            title = event["title"]
        elif event["type"] == "error":
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{event['message']} (request {get_request_id()})")
        elif event["type"] == "done":
            msg = event["message"]
            return ChatResponse(
                conversation_id=turn.conversation_id,
                title=title,
                message=msg,
                response=msg["content"],
                message_id=msg["id"],
                timestamp=msg["created_at"],
            )
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "No answer was produced.")


# Legacy paths used by the previous frontend and scripts.
router.add_api_route("/chat", chat, methods=["POST"], include_in_schema=False,
                     response_model=ChatResponse, dependencies=[Depends(rate_limit)])
router.add_api_route("/chat/stream", chat_stream, methods=["POST"], include_in_schema=False,
                     dependencies=[Depends(rate_limit)])
