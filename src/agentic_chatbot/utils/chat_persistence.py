"""
Chat persistence utilities for ensuring all messages are stored in PostgreSQL.
Provides async database operations with comprehensive error handling and logging.
"""

import sys
import os
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

from agentic_chatbot.exception.exception import DatabaseException
from agentic_chatbot.logging.logging_utils import get_correlation_id, ExecutionTimer


logger = logging.getLogger(__name__)

DB_URI = os.getenv("DB_URI")


class ChatPersistence:
    """Handle chat message persistence to PostgreSQL."""

    def __init__(self):
        self._pool = None
        self.correlation_id = get_correlation_id()

    async def _get_pool(self):
        """Get or create database connection pool."""
        if self._pool is not None:
            return self._pool

        if not DB_URI:
            logger.warning(
                "DB_URI not set — chat persistence disabled",
                extra={"correlation_id": self.correlation_id}
            )
            return None

        try:
            logger.debug(
                "Initializing database connection pool",
                extra={"correlation_id": self.correlation_id}
            )

            import psycopg_pool

            self._pool = psycopg_pool.AsyncConnectionPool(
                conninfo=DB_URI,
                max_size=10,
                kwargs={"autocommit": True, "prepare_threshold": 0},
                open=False,
            )
            await self._pool.open()

            logger.info(
                "Database connection pool initialized",
                extra={"correlation_id": self.correlation_id}
            )

            return self._pool
        except Exception as e:
            logger.error(
                f"Failed to initialize chat persistence pool: {str(e)}",
                extra={"correlation_id": self.correlation_id},
                exc_info=True
            )
            raise DatabaseException(
                f"Failed to initialize database pool: {str(e)}",
                sys,
                correlation_id=self.correlation_id
            )

    async def ensure_table(self):
        """Create chat_history table if it doesn't exist."""
        with ExecutionTimer("ensure_table", self.correlation_id, logger):
            pool = await self._get_pool()
            if not pool:
                logger.warning(
                    "No database pool available, skipping table creation",
                    extra={"correlation_id": self.correlation_id}
                )
                return

            try:
                async with pool.connection() as conn:
                    logger.debug(
                        "Creating chat_history table",
                        extra={"correlation_id": self.correlation_id}
                    )

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

                    logger.info(
                        "Chat history table ensured",
                        extra={"correlation_id": self.correlation_id}
                    )
            except Exception as e:
                logger.error(
                    f"Failed to create chat_history table: {str(e)}",
                    extra={"correlation_id": self.correlation_id},
                    exc_info=True
                )
                raise DatabaseException(
                    f"Failed to ensure chat history table: {str(e)}",
                    sys,
                    correlation_id=self.correlation_id
                )

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
            logger.warning(
                f"Cannot save message {message_id} — no database connection",
                extra={"correlation_id": self.correlation_id}
            )
            return False

        try:
            with ExecutionTimer("save_message", self.correlation_id, logger):
                if timestamp is None:
                    timestamp = datetime.utcnow().isoformat()

                logger.debug(
                    f"Saving message {message_id} for chat {chat_id}",
                    extra={"correlation_id": self.correlation_id}
                )

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

                logger.debug(
                    f"Message {message_id} saved successfully",
                    extra={"correlation_id": self.correlation_id}
                )
                return True
        except Exception as e:
            logger.error(
                f"Failed to save message {message_id}: {str(e)}",
                extra={"correlation_id": self.correlation_id},
                exc_info=True
            )
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
            logger.warning(
                f"Cannot retrieve messages for {chat_id} — no database connection",
                extra={"correlation_id": self.correlation_id}
            )
            return []

        try:
            with ExecutionTimer("get_chat_messages", self.correlation_id, logger):
                logger.debug(
                    f"Retrieving messages for chat {chat_id}",
                    extra={"correlation_id": self.correlation_id}
                )

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

                logger.info(
                    f"Retrieved {len(messages)} messages for chat {chat_id}",
                    extra={"correlation_id": self.correlation_id}
                )
                return messages
        except Exception as e:
            logger.error(
                f"Failed to retrieve messages for {chat_id}: {str(e)}",
                extra={"correlation_id": self.correlation_id},
                exc_info=True
            )
            return []

    async def delete_chat(self, chat_id: str) -> bool:
        """Delete all messages for a chat session."""
        pool = await self._get_pool()
        if not pool:
            logger.warning(
                f"Cannot delete chat {chat_id} — no database connection",
                extra={"correlation_id": self.correlation_id}
            )
            return False

        try:
            with ExecutionTimer("delete_chat", self.correlation_id, logger):
                logger.debug(
                    f"Deleting chat {chat_id}",
                    extra={"correlation_id": self.correlation_id}
                )

                async with pool.connection() as conn:
                    await conn.execute(
                        "DELETE FROM chat_history WHERE chat_id = %s",
                        (chat_id,),
                    )

                logger.info(
                    f"Chat {chat_id} deleted successfully",
                    extra={"correlation_id": self.correlation_id}
                )
                return True
        except Exception as e:
            logger.error(
                f"Failed to delete chat {chat_id}: {str(e)}",
                extra={"correlation_id": self.correlation_id},
                exc_info=True
            )
            return False

    async def close(self):
        """Close the database connection pool."""
        if self._pool:
            try:
                await self._pool.close()
                logger.info(
                    "Database connection pool closed",
                    extra={"correlation_id": self.correlation_id}
                )
            except Exception as e:
                logger.error(
                    f"Error closing database pool: {str(e)}",
                    extra={"correlation_id": self.correlation_id},
                    exc_info=True
                )


# Global instance
_persistence = ChatPersistence()


async def get_persistence() -> ChatPersistence:
    """Get the global chat persistence instance."""
    return _persistence
