"""
Chat History Router
Stores and retrieves chat history from PostgreSQL database.
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

router = APIRouter(prefix="/api/history", tags=["history"])

DB_URI = os.getenv("DB_URI")

# ── Pydantic Models ──────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str

class ChatSession(BaseModel):
    chat_id: str
    title: str
    created_at: str
    messages: List[ChatMessage]

class ChatHistoryItem(BaseModel):
    chat_id: str
    title: str
    created_at: str
    message_count: int

class SaveChatRequest(BaseModel):
    chat_id: str
    title: str
    messages: List[ChatMessage]

class UpdateChatTitleRequest(BaseModel):
    chat_id: str
    title: str


# ── Database helpers ─────────────────────────────────────────────────────────

import json

_pool = None

async def _get_pool():
    """Lazy-init a connection pool for chat history."""
    global _pool
    if _pool is not None:
        return _pool

    if not DB_URI:
        raise HTTPException(
            status_code=500,
            detail="DB_URI not set — cannot use PostgreSQL for chat history",
        )

    try:
        import psycopg_pool
        _pool = psycopg_pool.AsyncConnectionPool(
            conninfo=DB_URI,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await _pool.open()
        return _pool
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to database: {str(e)}",
        )


async def _ensure_table():
    """Create the chat_history table if it doesn't exist."""
    pool = await _get_pool()
    async with pool.connection() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                chat_id    TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                messages   JSONB NOT NULL DEFAULT '[]'::jsonb
            );
        """)


_table_ready = False

async def _ensure_ready():
    global _table_ready
    if not _table_ready:
        await _ensure_table()
        _table_ready = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/chats", response_model=List[ChatHistoryItem])
async def get_chat_history():
    """Get list of all chats."""
    await _ensure_ready()
    pool = await _get_pool()

    async with pool.connection() as conn:
        rows = await conn.execute(
            """
            SELECT chat_id, title, created_at, jsonb_array_length(messages) as msg_count
            FROM chat_history
            ORDER BY updated_at DESC
            """
        )
        results = await rows.fetchall()

    return [
        ChatHistoryItem(
            chat_id=row[0],
            title=row[1],
            created_at=row[2].isoformat() if row[2] else "",
            message_count=row[3] or 0,
        )
        for row in results
    ]


@router.get("/chats/{chat_id}", response_model=ChatSession)
async def get_chat(chat_id: str):
    """Get a specific chat session."""
    await _ensure_ready()
    pool = await _get_pool()

    async with pool.connection() as conn:
        row = await conn.execute(
            "SELECT chat_id, title, created_at, messages FROM chat_history WHERE chat_id = %s",
            (chat_id,),
        )
        result = await row.fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Chat not found")

    messages_data = result[3] if result[3] else []

    return ChatSession(
        chat_id=result[0],
        title=result[1],
        created_at=result[2].isoformat() if result[2] else "",
        messages=[ChatMessage(**m) for m in messages_data],
    )


@router.post("/chats")
async def save_chat(request: SaveChatRequest):
    """Save or update a chat session."""
    await _ensure_ready()
    pool = await _get_pool()

    messages_json = json.dumps([msg.dict() for msg in request.messages])

    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO chat_history (chat_id, title, created_at, updated_at, messages)
            VALUES (%s, %s, NOW(), NOW(), %s::jsonb)
            ON CONFLICT (chat_id) DO UPDATE SET
                title = EXCLUDED.title,
                updated_at = NOW(),
                messages = EXCLUDED.messages
            """,
            (request.chat_id, request.title, messages_json),
        )

    return {
        "success": True,
        "chat_id": request.chat_id,
        "message": "Chat saved successfully",
    }


@router.put("/chats/{chat_id}/title")
async def update_chat_title(chat_id: str, request: UpdateChatTitleRequest):
    """Update chat title."""
    await _ensure_ready()
    pool = await _get_pool()

    async with pool.connection() as conn:
        result = await conn.execute(
            "UPDATE chat_history SET title = %s, updated_at = NOW() WHERE chat_id = %s",
            (request.title, chat_id),
        )

    return {
        "success": True,
        "chat_id": chat_id,
        "title": request.title,
    }


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str):
    """Delete a chat session."""
    await _ensure_ready()
    pool = await _get_pool()

    async with pool.connection() as conn:
        result = await conn.execute(
            "DELETE FROM chat_history WHERE chat_id = %s RETURNING chat_id",
            (chat_id,),
        )
        deleted = await result.fetchone()

    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {
        "success": True,
        "chat_id": chat_id,
        "message": "Chat deleted successfully",
    }


@router.delete("/chats")
async def clear_all_chats():
    """Delete all chat sessions."""
    await _ensure_ready()
    pool = await _get_pool()

    async with pool.connection() as conn:
        result = await conn.execute("DELETE FROM chat_history")

    return {
        "success": True,
        "message": "All chats cleared",
    }


@router.get("/stats")
async def get_chat_stats():
    """Get chat statistics."""
    await _ensure_ready()
    pool = await _get_pool()

    async with pool.connection() as conn:
        row = await conn.execute(
            """
            SELECT
                COUNT(*) as total_chats,
                COALESCE(SUM(jsonb_array_length(messages)), 0) as total_messages
            FROM chat_history
            """
        )
        result = await row.fetchone()

    total_chats = result[0] or 0
    total_messages = result[1] or 0

    return {
        "total_chats": total_chats,
        "total_messages": total_messages,
        "average_messages_per_chat": total_messages / total_chats if total_chats > 0 else 0,
    }
