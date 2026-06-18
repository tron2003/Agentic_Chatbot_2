"""
Logging utilities for the agentic chatbot.
Provides decorators for automatic function logging, execution time tracking, and error logging.
"""

import logging
import time
import json
import functools
import asyncio
from typing import Any, Callable, Optional, Dict
from datetime import datetime
from uuid import uuid4

logger = logging.getLogger("agentic_chatbot")


def get_correlation_id() -> str:
    """Generate a unique correlation ID for request tracking."""
    return str(uuid4())


def log_function_call(
    func: Callable,
    correlation_id: str,
    args: tuple,
    kwargs: dict,
    logger_instance: logging.Logger,
) -> None:
    """Log function call with parameters."""
    try:
        # Sanitize sensitive parameters
        safe_kwargs = {
            k: "***" if k in ["password", "api_key", "token"] else v
            for k, v in kwargs.items()
        }

        log_data = {
            "correlation_id": correlation_id,
            "function": func.__name__,
            "args_count": len(args),
            "kwargs": safe_kwargs,
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger_instance.debug(f"Function call: {json.dumps(log_data)}")
    except Exception as e:
        logger_instance.debug(f"Error logging function call: {e}")


def log_function_result(
    func: Callable,
    correlation_id: str,
    result: Any,
    execution_time: float,
    logger_instance: logging.Logger,
) -> None:
    """Log function result and execution time."""
    try:
        # Truncate large results
        result_str = str(result)
        if len(result_str) > 500:
            result_str = result_str[:500] + "..."

        log_data = {
            "correlation_id": correlation_id,
            "function": func.__name__,
            "execution_time_ms": round(execution_time * 1000, 2),
            "result_type": type(result).__name__,
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger_instance.debug(f"Function result: {json.dumps(log_data)}")
    except Exception as e:
        logger_instance.debug(f"Error logging function result: {e}")


def log_exception(
    func: Callable,
    correlation_id: str,
    exception: Exception,
    execution_time: float,
    logger_instance: logging.Logger,
) -> None:
    """Log exception with context."""
    try:
        log_data = {
            "correlation_id": correlation_id,
            "function": func.__name__,
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "execution_time_ms": round(execution_time * 1000, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }
        logger_instance.error(
            f"Function exception: {json.dumps(log_data)}", exc_info=True
        )
    except Exception as e:
        logger_instance.error(f"Error logging exception: {e}")


def log_sync(
    correlation_id: Optional[str] = None,
    logger_instance: Optional[logging.Logger] = None,
) -> Callable:
    """
    Decorator for synchronous functions.
    Logs function calls, results, and exceptions with execution time.

    Args:
        correlation_id: Optional correlation ID for request tracking
        logger_instance: Optional custom logger instance
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            _correlation_id = correlation_id or get_correlation_id()
            _logger = logger_instance or logger

            start_time = time.time()
            try:
                log_function_call(func, _correlation_id, args, kwargs, _logger)
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                log_function_result(
                    func, _correlation_id, result, execution_time, _logger
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                log_exception(func, _correlation_id, e, execution_time, _logger)
                raise

        return wrapper

    return decorator


def log_async(
    correlation_id: Optional[str] = None,
    logger_instance: Optional[logging.Logger] = None,
) -> Callable:
    """
    Decorator for asynchronous functions.
    Logs function calls, results, and exceptions with execution time.

    Args:
        correlation_id: Optional correlation ID for request tracking
        logger_instance: Optional custom logger instance
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            _correlation_id = correlation_id or get_correlation_id()
            _logger = logger_instance or logger

            start_time = time.time()
            try:
                log_function_call(func, _correlation_id, args, kwargs, _logger)
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                log_function_result(
                    func, _correlation_id, result, execution_time, _logger
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                log_exception(func, _correlation_id, e, execution_time, _logger)
                raise

        return wrapper

    return decorator


class ExecutionTimer:
    """Context manager for timing code execution."""

    def __init__(
        self,
        operation_name: str,
        correlation_id: Optional[str] = None,
        logger_instance: Optional[logging.Logger] = None,
    ):
        self.operation_name = operation_name
        self.correlation_id = correlation_id or get_correlation_id()
        self.logger = logger_instance or logger
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        log_data = {
            "correlation_id": self.correlation_id,
            "operation": self.operation_name,
            "status": "started",
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.logger.debug(f"Operation started: {json.dumps(log_data)}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        execution_time = time.time() - self.start_time

        if exc_type is not None:
            log_data = {
                "correlation_id": self.correlation_id,
                "operation": self.operation_name,
                "status": "failed",
                "exception_type": exc_type.__name__,
                "exception_message": str(exc_val),
                "execution_time_ms": round(execution_time * 1000, 2),
                "timestamp": datetime.utcnow().isoformat(),
            }
            self.logger.error(f"Operation failed: {json.dumps(log_data)}")
            return False

        log_data = {
            "correlation_id": self.correlation_id,
            "operation": self.operation_name,
            "status": "completed",
            "execution_time_ms": round(execution_time * 1000, 2),
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.logger.debug(f"Operation completed: {json.dumps(log_data)}")
        return True


def create_structured_log(
    level: str, message: str, correlation_id: str, **additional_fields
) -> Dict[str, Any]:
    """Create a structured log entry as a dictionary."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "message": message,
        "correlation_id": correlation_id,
    }
    log_entry.update(additional_fields)
    return log_entry
