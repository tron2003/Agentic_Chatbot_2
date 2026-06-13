"""
Chat persistence utilities for ensuring all messages are stored in PostgreSQL.
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

DB_URI = os.getenv("DB_URI")


class ChatPersistence:
    """Handle chat message persistence to PostgreSQL."""

    def __init__(self):
        self._pool = None

    async def _get_pool(self):
        """Get or create database connection pool."""
        if self._pool is not None:
            return self._pool

        if not DB_URI:
            logger.warning("DB_URI not set — chat persistence disabled")
            return None

        try:
            import psycopg_pool

            self._pool = psycopg_pool.AsyncConnectionPool(
                conninfo=DB_URI,
                max_size=10,
                kwargs={"autocommit": True, "prepare_threshold": 0},
                open=False,
            )
            await self._pool.open()
            return self._pool
        except Exception as e:
            logger.error(f"Failed to initialize chat persistence pool: {e}")
            return None

    async def ensure_table(self):
        """Create chat_history table if it doesn't exist."""
        pool = await self._get_pool()
        if not pool:
            return

        try:
            async with pool.connection() as conn:
                # Execute each statement separately
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_history (
                        chat_id TEXT NOT NULL,
                        message_id TEXT PRIMARY KEY,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)

                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chat_history_chat_id ON chat_history(chat_id)"
                )

                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_chat_history_timestamp ON chat_history(timestamp)"
                )
        except Exception as e:
            logger.error(f"Failed to create chat_history table: {e}")

    async def save_message(
        self,
        chat_id: str,
        message_id: str,
        role: str,
        content: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        """
        Save a single message to the database immediately.

        Args:
            chat_id: Conversation thread ID
            message_id: Unique message identifier
            role: "user" or "assistant"
            content: Message content
            timestamp: ISO 8601 timestamp (auto-generated if not provided)

        Returns:
            True if saved successfully, False otherwise
        """
        pool = await self._get_pool()
        if not pool:
            logger.warning(f"Cannot save message {message_id} — no database connection")
            return False

        try:
            if timestamp is None:
                timestamp = datetime.utcnow().isoformat()

            async with pool.connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO chat_history (chat_id, message_id, role, content, timestamp)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (message_id) DO UPDATE SET
                        content = EXCLUDED.content,
                        updated_at = NOW()
                    """,
                    (chat_id, message_id, role, content, timestamp),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to save message {message_id}: {e}")
            return False

    async def get_chat_messages(self, chat_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve all messages for a chat session.

        Args:
            chat_id: Conversation thread ID
            limit: Maximum number of messages to retrieve

        Returns:
            List of message dictionaries
        """
        pool = await self._get_pool()
        if not pool:
            logger.warning(f"Cannot retrieve messages for {chat_id} — no database connection")
            return []

        try:
            async with pool.connection() as conn:
                rows = await conn.execute(
                    """
                    SELECT message_id, role, content, timestamp
                    FROM chat_history
                    WHERE chat_id = %s
                    ORDER BY timestamp ASC
                    LIMIT %s
                    """,
                    (chat_id, limit),
                )
                results = await rows.fetchall()

            messages = [
                {
                    "message_id": row[0],
                    "role": row[1],
                    "content": row[2],
                    "timestamp": row[3].isoformat() if row[3] else None,
                }
                for row in results
            ]
            return messages
        except Exception as e:
            logger.error(f"Failed to retrieve messages for {chat_id}: {e}")
            return []

    async def delete_chat(self, chat_id: str) -> bool:
        """Delete all messages for a chat session."""
        pool = await self._get_pool()
        if not pool:
            return False

        try:
            async with pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM chat_history WHERE chat_id = %s",
                    (chat_id,),
                )
            return True
        except Exception as e:
            logger.error(f"Failed to delete chat {chat_id}: {e}")
            return False

    async def close(self):
        """Close the database connection pool."""
        if self._pool:
            await self._pool.close()


# Global instance
_persistence = ChatPersistence()


async def get_persistence() -> ChatPersistence:
    """Get the global chat persistence instance."""
    return _persistence
