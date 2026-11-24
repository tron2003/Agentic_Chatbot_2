"""Conversation history: list, search, open, rename, export, delete."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from agentic_chatbot.api.schemas import ConversationDetail, ConversationOut, RenameRequest
from agentic_chatbot.api.security import require_api_key
from agentic_chatbot.services.store import get_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["conversations"], dependencies=[Depends(require_api_key)])


async def _forget_thread(request: Request, conversation_id: str) -> None:
    pipeline = getattr(request.app.state, "pipeline", None)
    checkpointer = getattr(pipeline, "checkpointer", None)
    if checkpointer is not None:
        try:
            await checkpointer.adelete_thread(conversation_id)
        except Exception as exc:  # pragma: no cover
            logger.warning("Could not delete checkpoints for %s: %s", conversation_id, exc)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(q: str | None = Query(None, max_length=200), limit: int = Query(100, ge=1, le=500)):
    return await get_store().list_conversations(q.strip() if q else None, limit)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(conversation_id: str):
    store = get_store()
    conv = await store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return {"conversation": conv, "messages": await store.get_messages(conversation_id)}


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def rename_conversation(conversation_id: str, body: RenameRequest):
    store = get_store()
    if not await store.rename_conversation(conversation_id, body.title):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    return await store.get_conversation(conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: str, request: Request):
    if not await get_store().delete_conversation(conversation_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    await _forget_thread(request, conversation_id)


@router.delete("/conversations")
async def delete_all_conversations(request: Request, confirm: bool = Query(False)):
    if not confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pass ?confirm=true to delete every conversation.")
    store = get_store()
    ids = [c["id"] for c in await store.list_conversations(limit=10_000)]
    deleted = await store.delete_all_conversations()
    for cid in ids:
        await _forget_thread(request, cid)
    return {"deleted": deleted}


@router.get("/conversations/{conversation_id}/export", response_class=PlainTextResponse)
async def export_conversation(conversation_id: str):
    store = get_store()
    conv = await store.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found.")
    lines = [f"# {conv['title']}", "", f"_Exported {datetime.now():%d %B %Y, %H:%M}_", ""]
    for m in await store.get_messages(conversation_id):
        who = "You" if m["role"] == "user" else "Assistant"
        lines += [f"## {who}", "", m["content"], ""]
        sources = (m.get("metadata") or {}).get("sources") or []
        if sources:
            lines.append("Sources:")
            for s in sources:
                lines.append(f"- [{s.get('title')}]({s['url']})" if s.get("url") else f"- {s.get('title')}")
            lines.append("")
    slug = re.sub(r"[^a-z0-9]+", "-", conv["title"].lower()).strip("-")[:50] or "conversation"
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
    )


@router.get("/stats")
async def stats():
    return await get_store().stats()
