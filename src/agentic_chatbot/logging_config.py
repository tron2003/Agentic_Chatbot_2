"""
Logging configuration for the Agentic Chatbot.
Provides different logging levels for development and production.
"""

import logging
import os
from pathlib import Path


def configure_logging(environment: str = "production"):
    """
    Configure logging for the application.

    Args:
        environment: "development", "staging", or "production"
    """
    # Create logs directory
    log_dir = Path("artifacts/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Determine log level based on environment
    if environment == "development":
        log_level = logging.DEBUG
        console_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    else:
        log_level = logging.INFO
        console_format = "%(levelname)s - %(message)s"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler - verbose (for debugging)
    file_handler = logging.FileHandler(log_dir / "chatbot.log")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_formatter)

    # Console handler - less verbose
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(console_format)
    console_handler.setFormatter(console_formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress verbose third-party loggers
    verbose_loggers = [
        "httpx",
        "urllib3",
        "asyncio",
        "psycopg",
        "PIL",
    ]

    for logger_name in verbose_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    # Database persistence logger
    logging.getLogger("agentic_chatbot.utils.chat_persistence").setLevel(logging.ERROR)

    return root_logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)
