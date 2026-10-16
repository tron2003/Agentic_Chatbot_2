"""Chat endpoints: streaming (SSE) and plain JSON."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from agentic_chatbot.api.schemas import ChatRequest, ChatResponse
from agentic_chatbot.api.security import rate_limit, require_api_key
from agentic_chatbot.core.context import get_request_id
from agentic_chatbot.services.chat_service import ChatTurn, fallback_title
from agentic_chatbot.services.store import get_store

router = APIRouter(tags=["chat"], dependencies=[Depends(require_api_key)])


def _pipeline(request: Request):
    pipeline = getattr(request.app.state, "pipeline", None)
    if pipeline is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant is still starting. Try again shortly.")
    return pipeline


async def _prepare_turn(body: ChatRequest, request: Request) -> ChatTurn:
    pipeline = _pipeline(request)
    store = get_store()
    conversation_id = body.conversation_id or f"c_{uuid.uuid4().hex[:20]}"
    existing = await store.get_conversation(conversation_id)

    if body.regenerate:
        if not existing:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
        checkpoint_id = await pipeline.regenerate_checkpoint(conversation_id)
        if not checkpoint_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "There is no answer to regenerate in this conversation.")
        await store.delete_last_assistant(conversation_id)
        return ChatTurn(pipeline, store, conversation_id=conversation_id, is_new=False, message=None,
                        model_message=None, user_message_id=None, checkpoint_id=checkpoint_id)

    assert body.message is not None
    if not existing:
        await store.create_conversation(conversation_id, fallback_title(body.message))

    model_message = body.message
    metadata: dict[str, Any] = {}
    if body.attachments:
        names = ", ".join(a.name for a in body.attachments)
        model_message += f"\n\n[The user attached these files, now in the knowledge base: {names}]"
        metadata["attachments"] = [a.model_dump() for a in body.attachments]

    user_id = f"msg_{uuid.uuid4().hex[:20]}"
    await store.add_message(conversation_id, user_id, "user", body.message, metadata)
    return ChatTurn(pipeline, store, conversation_id=conversation_id, is_new=not existing,
                    message=body.message, model_message=model_message, user_message_id=user_id)


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
