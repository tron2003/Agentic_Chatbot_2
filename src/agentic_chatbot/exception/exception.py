"""
Application exceptions.

Each exception carries a stable ``error_code``, an HTTP ``status_code`` and a
user-safe ``public_message``. The full message (which may contain internal
details) is logged; only the public message is ever returned to clients.

The constructors still accept the legacy ``(message, sys)`` call style used in
older code, so ``raise LLMException("...", sys)`` keeps working.
"""

from __future__ import annotations

from typing import Any

from agentic_chatbot.core.context import get_request_id


class CustomException(Exception):
    error_code = "INTERNAL_ERROR"
    status_code = 500
    public_message = "Something went wrong while handling the request."

    def __init__(
        self,
        error_message: str,
        error_detail: Any = None,  # legacy positional arg (was `sys`); ignored
        correlation_id: str | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
        public_message: str | None = None,
    ):
        super().__init__(error_message)
        self.error_message = error_message
        self.correlation_id = correlation_id or get_request_id()
        if error_code:
            self.error_code = error_code
        if status_code:
            self.status_code = status_code
        if public_message:
            self.public_message = public_message
        self.details = details or {}

    def __str__(self) -> str:
        return self.error_message

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.error_code,
                "message": self.public_message,
                "request_id": self.correlation_id,
                "details": self.details,
            }
        }


class ValidationException(CustomException):
    error_code = "VALIDATION_ERROR"
    status_code = 400
    public_message = "The request was not valid."


class DatabaseException(CustomException):
    error_code = "DATABASE_ERROR"
    status_code = 503
    public_message = "The database is unavailable. Check DB_URI and that Postgres is running."


class LLMException(CustomException):
    error_code = "LLM_ERROR"
    status_code = 502
    public_message = "The language model request failed."


class LLMConfigError(LLMException):
    error_code = "LLM_NOT_CONFIGURED"
    status_code = 503
    public_message = "The language model is not configured."


class VectorStoreException(CustomException):
    error_code = "VECTOR_STORE_ERROR"
    status_code = 503
    public_message = "The knowledge base is unavailable."


class FileProcessingException(CustomException):
    error_code = "FILE_PROCESSING_ERROR"
    status_code = 400
    public_message = "The file could not be processed."


class ToolExecutionException(CustomException):
    error_code = "TOOL_EXECUTION_ERROR"
    status_code = 500
    public_message = "A tool failed while answering."


class NotFoundException(CustomException):
    error_code = "NOT_FOUND"
    status_code = 404
    public_message = "Not found."
