"""DB_URI set but Postgres not running (the most common local-setup mistake):
in development the app must start quickly, fall back to in-memory storage for
chat history, conversation memory and the document library, and keep working."""

import time

from fastapi.testclient import TestClient

UNREACHABLE = "postgresql://u:p@127.0.0.1:1/db"  # nothing listens on port 1


def test_unreachable_postgres_falls_back_to_memory(monkeypatch):
    monkeypatch.setenv("DB_URI", UNREACHABLE)
    from agentic_chatbot.core.settings import reset_caches

    reset_caches()
    from agentic_chatbot.api.app import create_app

    started = time.monotonic()
    with TestClient(create_app()) as client:
        startup = time.monotonic() - started
        assert startup < 10, f"startup took {startup:.1f}s"

        ready = client.get("/ready").json()
        assert ready["store_backend"] == "memory"
        assert ready["memory_backend"] == "memory"
        assert ready["vector_backend"] == "memory"
        assert client.get("/api/meta").json()["knowledge_base"]["backend"] == "memory"

        files = [("files", ("notes.md", b"# Notes\n\nPostgres fallback keeps uploads working.\n", "text/markdown"))]
        result = client.post("/api/documents", files=files).json()["results"][0]
        assert result["status"] == "ok", result
        assert client.get("/ready").json()["vector_backend"] == "memory"


def test_unreachable_hint_never_leaks_password():
    from agentic_chatbot.core.db import check_postgres, unreachable_hint

    reason = check_postgres("postgresql://user:s3cret@127.0.0.1:1/db")
    assert reason
    hint = unreachable_hint("postgresql://user:s3cret@127.0.0.1:1/db", reason)
    assert "127.0.0.1:1/db" in hint and "s3cret" not in hint
