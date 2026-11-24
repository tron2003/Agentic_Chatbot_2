"""Small logging helpers: an execution timer and a decorator for async functions.

Correlation IDs come from the request context (see ``core.context``), so every
log line written while handling a request shares the same ID.
"""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any

from agentic_chatbot.core.context import get_request_id

logger = logging.getLogger("agentic_chatbot")


def get_correlation_id() -> str:
    """Return the current request's ID (``-`` outside a request)."""
    return get_request_id()


class ExecutionTimer:
    """``with ExecutionTimer("rag_node", logger=log): ...`` logs duration at DEBUG."""

    def __init__(self, operation_name: str, correlation_id: str | None = None, logger_instance: logging.Logger | None = None):
        self.operation_name = operation_name
        self.logger = logger_instance or logger
        self.start = 0.0
        self.elapsed_ms = 0.0

    def __enter__(self) -> ExecutionTimer:
        self.start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.elapsed_ms = round((time.perf_counter() - self.start) * 1000, 1)
        if exc_type is None:
            self.logger.debug("%s completed", self.operation_name, extra={"elapsed_ms": self.elapsed_ms})
        else:
            self.logger.warning(
                "%s failed: %s", self.operation_name, exc, extra={"elapsed_ms": self.elapsed_ms}
            )
        return False


def log_async(correlation_id: str | None = None, logger_instance: logging.Logger | None = None) -> Callable:
    """Decorator that logs entry/exit/duration of an async function at DEBUG."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            with ExecutionTimer(func.__name__, logger_instance=logger_instance):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
