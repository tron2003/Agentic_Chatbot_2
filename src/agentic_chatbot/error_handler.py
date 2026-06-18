"""
Global error handling middleware for the agentic chatbot.
Catches all exceptions, logs them with context, and returns structured error responses.
"""

import logging
import json
from typing import Callable, Optional, Dict, Any
from datetime import datetime
from uuid import uuid4

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException

from agentic_chatbot.exception.exception import CustomException

logger = logging.getLogger("agentic_chatbot")


class ErrorContext:
    """Captures context about an error for structured logging."""

    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id or str(uuid4())
        self.timestamp = datetime.utcnow().isoformat()
        self.method: Optional[str] = None
        self.path: Optional[str] = None
        self.status_code: Optional[int] = None
        self.error_type: Optional[str] = None
        self.error_message: Optional[str] = None
        self.execution_time_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "method": self.method,
            "path": self.path,
            "status_code": self.status_code,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "execution_time_ms": self.execution_time_ms,
        }

    def to_json(self) -> str:
        """Convert context to JSON."""
        return json.dumps(self.to_dict())


def format_error_response(
    status_code: int,
    error_code: str,
    error_message: str,
    correlation_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Format a structured error response."""
    return {
        "error": {
            "status_code": status_code,
            "code": error_code,
            "message": error_message,
            "correlation_id": correlation_id,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {},
        }
    }


class GlobalErrorHandler(BaseHTTPMiddleware):
    """
    Middleware to catch all exceptions and return structured error responses.
    Logs all exceptions with correlation IDs and request context.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and handle any exceptions."""
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())

        # Add correlation ID to request state for downstream use
        request.state.correlation_id = correlation_id

        error_context = ErrorContext(correlation_id)
        error_context.method = request.method
        error_context.path = request.url.path

        start_time = datetime.utcnow().timestamp()

        try:
            response = await call_next(request)
            error_context.status_code = response.status_code
            error_context.execution_time_ms = (
                datetime.utcnow().timestamp() - start_time
            ) * 1000

            # Log successful requests (non-error status codes)
            if response.status_code >= 400:
                logger.warning(f"HTTP Error: {json.dumps(error_context.to_dict())}")

            return response

        except CustomException as e:
            error_context.status_code = e.status_code
            error_context.error_type = e.error_code
            error_context.error_message = str(e)
            error_context.execution_time_ms = (
                datetime.utcnow().timestamp() - start_time
            ) * 1000

            logger.error(
                f"Custom Exception: {json.dumps(error_context.to_dict())}",
                exc_info=True,
            )

            error_response = format_error_response(
                status_code=e.status_code,
                error_code=e.error_code,
                error_message=str(e),
                correlation_id=correlation_id,
                details=e.details,
            )

            return JSONResponse(status_code=e.status_code, content=error_response)

        except HTTPException as e:
            error_context.status_code = e.status_code
            error_context.error_type = "HTTP_ERROR"
            error_context.error_message = e.detail
            error_context.execution_time_ms = (
                datetime.utcnow().timestamp() - start_time
            ) * 1000

            logger.warning(f"HTTP Exception: {json.dumps(error_context.to_dict())}")

            # Return the original HTTPException as-is
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "status_code": e.status_code,
                        "message": str(e.detail),
                        "correlation_id": correlation_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                },
            )

        except ValueError as e:
            error_context.status_code = 400
            error_context.error_type = "VALIDATION_ERROR"
            error_context.error_message = str(e)
            error_context.execution_time_ms = (
                datetime.utcnow().timestamp() - start_time
            ) * 1000

            logger.error(
                f"Validation Error: {json.dumps(error_context.to_dict())}",
                exc_info=True,
            )

            error_response = format_error_response(
                status_code=400,
                error_code="VALIDATION_ERROR",
                error_message=str(e),
                correlation_id=correlation_id,
            )

            return JSONResponse(status_code=400, content=error_response)

        except Exception as e:
            error_context.status_code = 500
            error_context.error_type = "INTERNAL_SERVER_ERROR"
            error_context.error_message = str(e)
            error_context.execution_time_ms = (
                datetime.utcnow().timestamp() - start_time
            ) * 1000

            logger.error(
                f"Unhandled Exception: {json.dumps(error_context.to_dict())}",
                exc_info=True,
            )

            error_response = format_error_response(
                status_code=500,
                error_code="INTERNAL_SERVER_ERROR",
                error_message="An unexpected error occurred. Please try again later.",
                correlation_id=correlation_id,
            )

            return JSONResponse(status_code=500, content=error_response)


def setup_global_exception_handlers(app):
    """Setup global exception handlers for the FastAPI app."""
    app.add_middleware(GlobalErrorHandler)
    logger.info("Global error handler middleware installed")
