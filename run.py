#!/usr/bin/env python
"""
Production startup script for the Agentic Chatbot.
Handles environment configuration, dependency checks, and server startup.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_environment(environment: str = "production"):
    """Load environment variables from .env file."""
    env_file = Path(f".env.{environment}")
    if not env_file.exists():
        env_file = Path(".env")

    if env_file.exists():
        logger.info(f"📋 Loading environment from {env_file}")
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    key, _, value = line.partition("=")
                    os.environ[key] = value
    else:
        logger.warning("⚠️  No .env file found. Using system environment variables.")


def check_requirements():
    """Check that all required dependencies are installed."""
    try:
        import fastapi
        import langchain
        import langgraph
        import psycopg
        logger.info("✅ All required dependencies are installed")
        return True
    except ImportError as e:
        logger.error(f"❌ Missing dependency: {e}")
        return False


def ensure_directories():
    """Ensure all required directories exist."""
    directories = [
        "artifacts/logs",
        "workspace/uploads",
        "config",
    ]
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    logger.info("✅ All required directories created")


def start_server(environment: str = "production", workers: int = 1):
    """Start the FastAPI server."""
    logger.info(f"🚀 Starting Agentic Chatbot in {environment} environment...")

    # Check database connection
    db_uri = os.getenv("DB_URI")
    if not db_uri:
        logger.error("❌ Error: DB_URI not set. Please configure your database connection.")
        sys.exit(1)

    logger.info(f"🔗 Database: {db_uri[:50]}...")

    # Start the server
    import uvicorn

    server_host = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port = int(os.getenv("SERVER_PORT", "8001"))

    logger.info(f"🌍 Server: {server_host}:{server_port}")

    uvicorn.run(
        "backend_api:app",
        host=server_host,
        port=server_port,
        workers=workers,
        reload=environment == "development",
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Start the Agentic Chatbot API server"
    )
    parser.add_argument(
        "--environment",
        choices=["development", "staging", "production"],
        default="production",
        help="Deployment environment",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of Uvicorn worker processes",
    )

    args = parser.parse_args()

    # Setup environment
    load_environment(args.environment)

    # Ensure directories exist
    ensure_directories()

    # Check requirements
    if not check_requirements():
        logger.error("❌ Failed dependency check. Run: pip install -r requirements.txt")
        sys.exit(1)

    # Start server
    try:
        start_server(args.environment, args.workers)
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down gracefully...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
