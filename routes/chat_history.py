"""
Chat History Router
Stores and retrieves chat history from PostgreSQL database.
Includes comprehensive error handling and structured logging.
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from dotenv import load_dotenv

from agentic_chatbot.exception.exception import DatabaseException
from agentic_chatbot.logging.logging_utils import (
    ExecutionTimer,
    get_correlation_id,
    create_structured_log
)


load_dotenv()

logger = logging.getLogger(__name__)

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

async def _get_pool(correlation_id: str):
    """Lazy-init a connection pool for chat history."""
    global _pool
    if _pool is not None:
        return _pool

    if not DB_URI:
        logger.error(
            "DB_URI not set",
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=500,
            detail="DB_URI not set — cannot use PostgreSQL for chat history",
        )

    try:
        logger.debug(
            "Initializing database connection pool",
            extra={"correlation_id": correlation_id}
        )

        import psycopg_pool
        _pool = psycopg_pool.AsyncConnectionPool(
            conninfo=DB_URI,
            max_size=5,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            open=False,
        )
        await _pool.open()

        logger.info(
            "Database connection pool initialized",
            extra={"correlation_id": correlation_id}
        )

        return _pool
    except Exception as e:
        logger.error(
            f"Failed to connect to database: {str(e)}",
            extra={"correlation_id": correlation_id},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to database: {str(e)}",
        )


async def _ensure_table(correlation_id: str):
    """Create the chat_history table if it doesn't exist."""
    with ExecutionTimer("ensure_table", correlation_id, logger):
        try:
            pool = await _get_pool(correlation_id)
            async with pool.connection() as conn:
                logger.debug(
                    "Creating chat_history table",
                    extra={"correlation_id": correlation_id}
                )

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        chat_id    TEXT PRIMARY KEY,
                        title      TEXT NOT NULL DEFAULT 'New Chat',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        messages   JSONB NOT NULL DEFAULT '[]'::jsonb
                    );
                """)

                logger.info(
                    "Chat history table ensured",
                    extra={"correlation_id": correlation_id}
                )
        except Exception as e:
            logger.error(
                f"Failed to ensure table: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise


_table_ready = False

async def _ensure_ready(correlation_id: str):
    global _table_ready
    if not _table_ready:
        await _ensure_table(correlation_id)
        _table_ready = True


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/chats", response_model=List[ChatHistoryItem])
async def get_chat_history(request: Request):
    """Get list of all chats."""
    correlation_id = request.headers.get("X-Correlation-ID") or get_correlation_id()

    with ExecutionTimer("get_chat_history", correlation_id, logger):
        try:
            await _ensure_ready(correlation_id)
            pool = await _get_pool(correlation_id)

            logger.debug(
                "Retrieving all chat history",
                extra={"correlation_id": correlation_id}
            )

            async with pool.connection() as conn:
                rows = await conn.execute(
                    """
                    SELECT chat_id, title, created_at, jsonb_array_length(messages) as msg_count
                    FROM chat_history
                    ORDER BY updated_at DESC
                    """
                )
                results = await rows.fetchall()

            chats = [
                ChatHistoryItem(
                    chat_id=row[0],
                    title=row[1],
                    created_at=row[2].isoformat() if row[2] else "",
                    message_count=row[3] or 0,
                )
                for row in results
            ]

            logger.info(
                f"Retrieved {len(chats)} chats",
                extra={"correlation_id": correlation_id}
            )

            return chats
        except Exception as e:
            logger.error(
                f"Failed to get chat history: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve chat history: {str(e)}"
            )


@router.get("/chats/{chat_id}", response_model=ChatSession)
async def get_chat(chat_id: str, request: Request):
    """Get a specific chat session."""
    correlation_id = request.headers.get("X-Correlation-ID") or get_correlation_id()

    with ExecutionTimer("get_chat", correlation_id, logger):
        try:
            await _ensure_ready(correlation_id)
            pool = await _get_pool(correlation_id)

            logger.debug(
                f"Retrieving chat {chat_id}",
                extra={"correlation_id": correlation_id}
            )

            async with pool.connection() as conn:
                row = await conn.execute(
                    "SELECT chat_id, title, created_at, messages FROM chat_history WHERE chat_id = %s",
                    (chat_id,),
                )
                result = await row.fetchone()

            if not result:
                logger.warning(
                    f"Chat not found: {chat_id}",
                    extra={"correlation_id": correlation_id}
                )
                raise HTTPException(status_code=404, detail="Chat not found")

            messages_data = result[3] if result[3] else []

            logger.info(
                f"Retrieved chat {chat_id} with {len(messages_data)} messages",
                extra={"correlation_id": correlation_id}
            )

            return ChatSession(
                chat_id=result[0],
                title=result[1],
                created_at=result[2].isoformat() if result[2] else "",
                messages=[ChatMessage(**m) for m in messages_data],
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to get chat {chat_id}: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve chat: {str(e)}"
            )


@router.post("/chats")
async def save_chat(request: SaveChatRequest, req: Request):
    """Save or update a chat session."""
    correlation_id = req.headers.get("X-Correlation-ID") or get_correlation_id()

    with ExecutionTimer("save_chat", correlation_id, logger):
        try:
            await _ensure_ready(correlation_id)
            pool = await _get_pool(correlation_id)

            logger.debug(
                f"Saving chat {request.chat_id}",
                extra={"correlation_id": correlation_id}
            )

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

            logger.info(
                f"Chat {request.chat_id} saved with {len(request.messages)} messages",
                extra={"correlation_id": correlation_id}
            )

            return {
                "success": True,
                "chat_id": request.chat_id,
                "message": "Chat saved successfully",
            }
        except Exception as e:
            logger.error(
                f"Failed to save chat {request.chat_id}: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save chat: {str(e)}"
            )


@router.put("/chats/{chat_id}/title")
async def update_chat_title(chat_id: str, request: UpdateChatTitleRequest, req: Request):
    """Update chat title."""
    correlation_id = req.headers.get("X-Correlation-ID") or get_correlation_id()

    with ExecutionTimer("update_chat_title", correlation_id, logger):
        try:
            await _ensure_ready(correlation_id)
            pool = await _get_pool(correlation_id)

            logger.debug(
                f"Updating title for chat {chat_id}",
                extra={"correlation_id": correlation_id}
            )

            async with pool.connection() as conn:
                result = await conn.execute(
                    "UPDATE chat_history SET title = %s, updated_at = NOW() WHERE chat_id = %s",
                    (request.title, chat_id),
                )

            logger.info(
                f"Chat {chat_id} title updated",
                extra={"correlation_id": correlation_id}
            )

            return {
                "success": True,
                "chat_id": chat_id,
                "title": request.title,
            }
        except Exception as e:
            logger.error(
                f"Failed to update chat title {chat_id}: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update chat title: {str(e)}"
            )


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: str, req: Request):
    """Delete a chat session."""
    correlation_id = req.headers.get("X-Correlation-ID") or get_correlation_id()

    with ExecutionTimer("delete_chat", correlation_id, logger):
        try:
            await _ensure_ready(correlation_id)
            pool = await _get_pool(correlation_id)

            logger.debug(
                f"Deleting chat {chat_id}",
                extra={"correlation_id": correlation_id}
            )

            async with pool.connection() as conn:
                result = await conn.execute(
                    "DELETE FROM chat_history WHERE chat_id = %s RETURNING chat_id",
                    (chat_id,),
                )
                deleted = await result.fetchone()

            if not deleted:
                logger.warning(
                    f"Chat not found for deletion: {chat_id}",
                    extra={"correlation_id": correlation_id}
                )
                raise HTTPException(status_code=404, detail="Chat not found")

            logger.info(
                f"Chat {chat_id} deleted successfully",
                extra={"correlation_id": correlation_id}
            )

            return {
                "success": True,
                "chat_id": chat_id,
                "message": "Chat deleted successfully",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(
                f"Failed to delete chat {chat_id}: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete chat: {str(e)}"
            )


@router.delete("/chats")
async def clear_all_chats(req: Request):
    """Delete all chat sessions."""
    correlation_id = req.headers.get("X-Correlation-ID") or get_correlation_id()

    with ExecutionTimer("clear_all_chats", correlation_id, logger):
        try:
            await _ensure_ready(correlation_id)
            pool = await _get_pool(correlation_id)

            logger.warning(
                "Clearing all chats",
                extra={"correlation_id": correlation_id}
            )

            async with pool.connection() as conn:
                result = await conn.execute("DELETE FROM chat_history")

            logger.info(
                "All chats cleared successfully",
                extra={"correlation_id": correlation_id}
            )

            return {
                "success": True,
                "message": "All chats cleared",
            }
        except Exception as e:
            logger.error(
                f"Failed to clear all chats: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to clear chats: {str(e)}"
            )


@router.get("/stats")
async def get_chat_stats(req: Request):
    """Get chat statistics."""
    correlation_id = req.headers.get("X-Correlation-ID") or get_correlation_id()

    with ExecutionTimer("get_chat_stats", correlation_id, logger):
        try:
            await _ensure_ready(correlation_id)
            pool = await _get_pool(correlation_id)

            logger.debug(
                "Retrieving chat statistics",
                extra={"correlation_id": correlation_id}
            )

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

            logger.info(
                f"Chat statistics retrieved: {total_chats} chats, {total_messages} messages",
                extra={"correlation_id": correlation_id}
            )

            return {
                "total_chats": total_chats,
                "total_messages": total_messages,
                "average_messages_per_chat": total_messages / total_chats if total_chats > 0 else 0,
            }
        except Exception as e:
            logger.error(
                f"Failed to get chat statistics: {str(e)}",
                extra={"correlation_id": correlation_id},
                exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve statistics: {str(e)}"
            )
