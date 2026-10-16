#!/usr/bin/env python
"""
Start the API server.

    python run.py                         # uses ENVIRONMENT from .env (development by default)
    python run.py --env production --workers 2
    python run.py --port 9000

Environment variables come from .env (see .env.example). In development the
server reloads on code changes. With more than one worker, set DB_URI so all
workers share conversation memory through Postgres.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    from agentic_chatbot.core.settings import get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the agentic chatbot API")
    parser.add_argument("--env", "--environment", dest="env", default=settings.environment,
                        choices=["development", "staging", "production"])
    parser.add_argument("--host", default=os.getenv("SERVER_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", os.getenv("SERVER_PORT", "8001"))))
    parser.add_argument("--workers", type=int, default=int(os.getenv("WEB_CONCURRENCY", "1")))
    args = parser.parse_args()

    os.environ["ENVIRONMENT"] = args.env
    from agentic_chatbot.core.settings import reset_caches

    reset_caches()
    dev = args.env == "development"
    if args.workers > 1 and not settings.db_uri:
        print("Warning: several workers without DB_URI means each worker has its own memory. "
              "Set DB_URI (Postgres) or use --workers 1.", file=sys.stderr)

    import uvicorn

    uvicorn.run(
        "backend_api:app",
        app_dir=str(ROOT),
        host=args.host,
        port=args.port,
        workers=1 if dev else args.workers,
        reload=dev,
        reload_dirs=[str(ROOT / "src")] if dev else None,
        proxy_headers=True,
        forwarded_allow_ips=os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        timeout_graceful_shutdown=20,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
