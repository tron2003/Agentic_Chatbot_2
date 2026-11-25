"""Model picker API, DuckDuckGo fallback for web search, and Excel/Word uploads."""

import asyncio
import io
import json

import pytest

from agentic_chatbot.core.settings import reset_caches
from agentic_chatbot.services import model_catalog
from agentic_chatbot.services.model_selection import selection_path
from agentic_chatbot.tools import web_tool


@pytest.fixture
def fake_catalog(monkeypatch):
    """No network: every provider 'lists' one model, Ollama is unreachable."""
    model_catalog.clear_catalog_cache()

    async def listed(block):
        return [{"id": "listed-model", "label": "Listed model"}]

    async def unreachable(block):
        raise model_catalog.httpx.ConnectError("refused")

    fetchers = {p: listed for p in model_catalog.ORDER}
    fetchers["ollama"] = unreachable
    monkeypatch.setattr(model_catalog, "FETCHERS", fetchers)
    for key in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.setenv(key, "")
    reset_caches()
    yield
    model_catalog.clear_catalog_cache()


def test_catalog_lists_providers_and_says_what_is_missing(client, fake_catalog):
    body = client.get("/api/models").json()
    assert body["current"]["source"] == "env" and body["current"]["main"]["provider"] == "demo"
    by_id = {p["id"]: p for p in body["providers"]}
    assert set(by_id) == {"openrouter", "ollama", "claude", "openai", "local", "demo"}
    assert by_id["openrouter"]["configured"] is False and "OPENROUTER_API_KEY" in by_id["openrouter"]["needs"]
    assert by_id["ollama"]["error"].startswith("Couldn't reach Ollama")
    # An unreachable provider still offers its configured default.
    assert by_id["ollama"]["models"][0]["id"] == by_id["ollama"]["default_model"]
    assert any(m["id"] == "listed-model" for m in by_id["demo"]["models"])


def test_choose_model_persists_overrides_env_and_resets(client, fake_catalog):
    res = client.put("/api/models", json={"main": {"provider": "demo", "model": "demo"}})
    assert res.status_code == 200 and res.json()["source"] == "ui"
    saved = json.loads(selection_path().read_text(encoding="utf-8"))
    assert saved["main"] == {"provider": "demo", "model": "demo"} and saved["router"] is None
    meta = client.get("/api/meta").json()
    assert meta["model_source"] == "ui" and meta["llm_ready"] is True

    res = client.delete("/api/models")
    assert res.json()["source"] == "env" and not selection_path().exists()


def test_choice_needing_a_missing_key_is_refused_and_not_saved(client, fake_catalog):
    res = client.put("/api/models", json={"main": {"provider": "claude", "model": "claude-sonnet-5-5"}})
    assert res.status_code == 400 and "ANTHROPIC_API_KEY" in res.json()["error"]["message"]
    assert not selection_path().exists()
    assert client.put("/api/models", json={"main": {"provider": "nope", "model": "x"}}).status_code == 422


def test_ui_choice_wins_over_llm_provider(client, fake_catalog, monkeypatch):
    from agentic_chatbot.components.llm_loader import describe_llm

    # .env says claude (no key); the UI picked demo, so the app works.
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    reset_caches()
    assert describe_llm()["configured"] is False
    client.put("/api/models", json={"main": {"provider": "demo", "model": "demo"}})
    info = describe_llm()
    assert info["configured"] is True and info["main"]["provider"] == "demo" and info["router"]["provider"] == "demo"


def test_corrupt_selection_file_is_ignored(client, fake_catalog):
    selection_path().write_text("{not json", encoding="utf-8")
    assert client.get("/api/meta").json()["model_source"] == "env"


# ── web search ──────────────────────────────────────────────────────────────

def _use(monkeypatch, provider_pref: str, tavily_key: str, ddg: bool):
    monkeypatch.setenv("WEB_SEARCH_PROVIDER", provider_pref)
    monkeypatch.setenv("TAVILY_API_KEY", tavily_key)
    monkeypatch.setattr(web_tool, "duckduckgo_installed", lambda: ddg)
    reset_caches()


@pytest.mark.parametrize(
    ("pref", "key", "ddg", "expected"),
    [
        ("auto", "tvly-x", True, ["tavily", "duckduckgo"]),
        ("auto", "", True, ["duckduckgo"]),
        ("auto", "", False, []),
        ("tavily", "", True, []),
        ("duckduckgo", "tvly-x", True, ["duckduckgo"]),
        ("off", "tvly-x", True, []),
    ],
)
def test_web_search_provider_order(monkeypatch, pref, key, ddg, expected):
    _use(monkeypatch, pref, key, ddg)
    assert web_tool.web_search_providers() == expected
    assert web_tool.web_search_available() is bool(expected)


def test_tavily_failure_falls_back_to_duckduckgo(monkeypatch):
    _use(monkeypatch, "auto", "tvly-x", True)

    async def tavily(query):
        raise RuntimeError("432 usage limit")

    async def ddg(query):
        return None, [{"title": "Vanguard holdings", "url": "https://example.com/v", "content": "Apple, Microsoft"}]

    monkeypatch.setattr(web_tool, "SEARCHERS", {"tavily": tavily, "duckduckgo": ddg})
    msg = asyncio.run(web_tool.web_search.ainvoke({"type": "tool_call", "id": "1", "name": "web_search", "args": {"query": "vanguard"}}))
    assert "Results from DuckDuckGo" in msg.content
    assert msg.artifact[0]["url"] == "https://example.com/v"


def test_no_results_anywhere_says_why(monkeypatch):
    _use(monkeypatch, "auto", "tvly-x", True)

    async def empty(query):
        return None, []

    monkeypatch.setattr(web_tool, "SEARCHERS", {"tavily": empty, "duckduckgo": empty})
    msg = asyncio.run(web_tool.web_search.ainvoke({"type": "tool_call", "id": "1", "name": "web_search", "args": {"query": "x"}}))
    assert "Tavily found nothing" in msg.content and "DuckDuckGo found nothing" in msg.content


def test_duckduckgo_tries_other_engines_when_one_has_no_results(monkeypatch):
    import sys
    import types

    calls = []

    class FakeDDGS:
        def text(self, query, max_results, backend):
            calls.append(backend)
            if backend != "duckduckgo":
                raise RuntimeError("No results found.")
            return [{"title": "t", "href": "https://example.com", "body": "b"}]

    monkeypatch.setitem(sys.modules, "ddgs", types.SimpleNamespace(DDGS=FakeDDGS))
    monkeypatch.setattr(web_tool, "DDG_RETRY_DELAY", 0)
    assert web_tool._ddg_text("q", 5)[0]["href"] == "https://example.com"
    assert calls == ["auto", "bing", "duckduckgo"]


# ── Excel and Word uploads ──────────────────────────────────────────────────

def _xlsx() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Refund"
    ws.append(["Month", "IGST refund"])
    ws.append(["April", 125000.5])
    ws.append(["July", 98000])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _docx() -> bytes:
    import docx

    d = docx.Document()
    d.add_paragraph("Launch plan: the beta opens on 3 March.")
    table = d.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Owner"
    table.rows[0].cells[1].text = "Kanish"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def test_excel_and_word_files_are_indexed(client):
    xlsx_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    docx_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    files = [("files", ("refund.xlsx", _xlsx(), xlsx_type)), ("files", ("plan.docx", _docx(), docx_type))]
    res = client.post("/api/documents", files=files).json()
    assert [r["status"] for r in res["results"]] == ["ok", "ok"], res
    assert all(r["document"]["chunks"] >= 1 for r in res["results"])


def test_excel_rows_become_readable_text(tmp_path):
    from agentic_chatbot.utils.document_loader import DocumentLoader

    path = tmp_path / "refund.xlsx"
    path.write_bytes(_xlsx())
    text = "\n".join(d.page_content for d in DocumentLoader().load_documents(path))
    assert "Sheet: Refund" in text and "Month | IGST refund" in text and "April | 125000.5" in text
