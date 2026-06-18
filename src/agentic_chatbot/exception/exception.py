"""
Enhanced exception handling for the agentic chatbot.
Provides structured error handling with correlation IDs and better formatting.
"""

import sys
import json
import uuid
from typing import Optional, Dict, Any


def error_message_detail(error, error_detail: sys) -> str:
    """Format error message with file, line, and message."""
    _, _, exc_tb = error_detail.exc_info()
    if exc_tb is None:
        return str(error)

    file_name = exc_tb.tb_frame.f_code.co_filename
    error_message = (
        f"\nError occurred\n"
        f"File: {file_name}\n"
        f"Line: {exc_tb.tb_lineno}\n"
        f"Message: {str(error)}"
    )
    return error_message


class CustomException(Exception):
    """Base custom exception with structured error handling."""

    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        correlation_id: Optional[str] = None,
        error_code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(error_message)

        self.error_message = error_message_detail(error_message, error_detail)
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}

    def __str__(self) -> str:
        return self.error_message

    def to_dict(self) -> Dict[str, Any]:
        """Return structured error response."""
        return {
            "error": {
                "code": self.error_code,
                "message": str(self),
                "correlation_id": self.correlation_id,
                "details": self.details,
            }
        }

    def to_json(self) -> str:
        """Return JSON-formatted error response."""
        return json.dumps(self.to_dict())


class ValidationException(CustomException):
    """Raised when input validation fails."""

    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            error_message,
            error_detail,
            correlation_id=correlation_id,
            error_code="VALIDATION_ERROR",
            status_code=400,
            details=details,
        )


class DatabaseException(CustomException):
    """Raised when database operations fail."""

    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            error_message,
            error_detail,
            correlation_id=correlation_id,
            error_code="DATABASE_ERROR",
            status_code=500,
            details=details,
        )


class LLMException(CustomException):
    """Raised when LLM operations fail."""

    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            error_message,
            error_detail,
            correlation_id=correlation_id,
            error_code="LLM_ERROR",
            status_code=500,
            details=details,
        )


class VectorStoreException(CustomException):
    """Raised when vector store operations fail."""

    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            error_message,
            error_detail,
            correlation_id=correlation_id,
            error_code="VECTOR_STORE_ERROR",
            status_code=500,
            details=details,
        )


class FileProcessingException(CustomException):
    """Raised when file processing fails."""

    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            error_message,
            error_detail,
            correlation_id=correlation_id,
            error_code="FILE_PROCESSING_ERROR",
            status_code=400,
            details=details,
        )


class ToolExecutionException(CustomException):
    """Raised when tool execution fails."""

    def __init__(
        self,
        error_message: str,
        error_detail: sys,
        correlation_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            error_message,
            error_detail,
            correlation_id=correlation_id,
            error_code="TOOL_EXECUTION_ERROR",
            status_code=500,
            details=details,
        )
