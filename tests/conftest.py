"""Test setup: every test runs against the scripted demo model, fake embeddings,
in-memory stores and no MCP servers, so the suite needs no keys or services."""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

os.environ.update(
    {
        "ENVIRONMENT": "development",
        "LLM_PROVIDER": "demo",
        "ROUTER_PROVIDER": "",
        "EMBEDDING_PROVIDER": "fake",
        "ENABLE_MCP": "false",
        "SERVE_FRONTEND": "false",
        "DB_URI": "",
        "VECTOR_DB_URI": "",
        "TAVILY_API_KEY": "",
        "WEB_SEARCH_PROVIDER": "off",  # never reach the internet from tests
        "OLLAMA_AUTOSTART": "false",   # never start processes from tests
        "API_KEYS": "",
        "RATE_LIMIT_PER_MINUTE": "1000",
        "DEMO_TOKEN_DELAY": "0",
        "LOG_LEVEL": "WARNING",
        "INTEGRATIONS_CONFIG_PATH": str(ROOT / "tests" / "_no_integrations.yaml"),
    }
)


@pytest.fixture(autouse=True)
def _fresh_state(tmp_path, monkeypatch):
    """Isolate settings caches, stores, vector store and rate limiter per test."""
    from agentic_chatbot.api.security import limiter
    from agentic_chatbot.components.llm_loader import reset_llm_cache
    from agentic_chatbot.components.vector_store_loader import reset_vector_store
    from agentic_chatbot.core.db import reset_postgres_check
    from agentic_chatbot.core.settings import reset_caches
    from agentic_chatbot.integrations.config import reset_integrations
    from agentic_chatbot.services import knowledge_base, long_term_memory, store

    monkeypatch.setenv("WORKSPACE_DIR", str(tmp_path / "workspace"))
    # Never read or write the real model picker choice from tests.
    monkeypatch.setenv("MODEL_SELECTION_PATH", str(tmp_path / "model_selection.json"))
    reset_caches()
    reset_integrations()
    reset_llm_cache()
    reset_vector_store()
    reset_postgres_check()
    limiter.reset()
    store.set_store(None)
    long_term_memory.set_memory_store(None)
    knowledge_base.get_knowledge_base()._invalidate()
    yield
    reset_caches()
    reset_integrations()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from agentic_chatbot.api.app import create_app

    with TestClient(create_app()) as c:
        yield c


def parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        data = "\n".join(line[5:].lstrip() for line in block.splitlines() if line.startswith("data:"))
        if data:
            events.append(json.loads(data))
    return events


@pytest.fixture
def stream(client):
    def _stream(body: dict, headers: dict | None = None) -> list[dict]:
        with client.stream("POST", "/api/chat/stream", json=body, headers=headers or {}) as res:
            assert res.status_code == 200, res.read()
            assert res.headers["content-type"].startswith("text/event-stream")
            return parse_sse(res.read().decode())

    return _stream
