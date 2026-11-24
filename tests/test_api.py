import asyncio

from tests.conftest import parse_sse


def types(events):
    return [e["type"] for e in events]


def test_health_ready_meta(client):
    assert client.get("/health").json()["status"] == "ok"
    ready = client.get("/ready")
    assert ready.status_code == 200 and ready.json()["checks"]["llm"] is True
    meta = client.get("/api/meta").json()
    assert meta["model"]["provider"] == "demo"
    assert "calculator" in meta["tools"]
    assert meta["auth_required"] is False
    assert client.get("/health").headers["x-request-id"]


def test_chat_stream_protocol_and_persistence(client, stream):
    events = stream({"message": "Hello, explain how you work"})
    kinds = types(events)
    assert kinds[0] == "meta" and kinds[-1] == "done"
    assert "route" in kinds and "token" in kinds and "title" in kinds
    route = next(e for e in events if e["type"] == "route")
    assert route["route"] == "chat"

    streamed = "".join(e["text"] for e in events if e["type"] == "token")
    done = events[-1]["message"]
    assert done["content"].strip() == streamed.strip()
    assert done["metadata"]["route"] == "chat"

    conv_id = events[0]["conversation_id"]
    detail = client.get(f"/api/conversations/{conv_id}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["conversation"]["title"]


def test_agent_route_streams_tool_steps(stream):
    events = stream({"message": "what is 17 * 23?"})
    assert next(e for e in events if e["type"] == "route")["route"] == "agent"
    assert "draft_reset" in types(events)
    tool_steps = [e["step"] for e in events if e["type"] == "step" and e["step"]["kind"] == "tool"]
    assert [s["status"] for s in tool_steps] == ["running", "done"]
    assert tool_steps[0]["id"] == tool_steps[1]["id"] and tool_steps[0]["tool"] == "calculator"
    assert "391" in events[-1]["message"]["content"]


def test_follow_up_and_regenerate(client, stream):
    first = stream({"message": "hello"})
    conv = first[0]["conversation_id"]
    stream({"message": "what is 2 + 2?", "conversation_id": conv})
    before = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert len(before) == 4

    regen = stream({"conversation_id": conv, "regenerate": True})
    assert types(regen)[-1] == "done"
    after = client.get(f"/api/conversations/{conv}").json()["messages"]
    assert len(after) == 4, "regenerate must replace the last answer, not append"
    assert after[-1]["id"] != before[-1]["id"]

    # The model's memory must not contain the question twice.
    pipeline = client.app.state.pipeline
    state = asyncio.run(pipeline.workflow.aget_state({"configurable": {"thread_id": conv}}))
    humans = [m.content for m in state.values["messages"] if m.type == "human"]
    assert humans == ["hello", "what is 2 + 2?"]


def test_regenerate_requires_existing_conversation(client):
    assert client.post("/api/chat/stream", json={"regenerate": True}).status_code == 422
    assert client.post("/api/chat/stream", json={"regenerate": True, "conversation_id": "nope"}).status_code == 404


def test_json_endpoint_and_legacy_alias(client):
    res = client.post("/api/chat", json={"message": "hi there"})
    body = res.json()
    assert res.status_code == 200 and body["response"] and body["conversation_id"]
    legacy = client.post("/chat", json={"message": "and again", "thread_id": body["conversation_id"]})
    assert legacy.status_code == 200
    assert legacy.json()["conversation_id"] == body["conversation_id"]


def test_validation_errors_are_structured(client):
    res = client.post("/api/chat", json={"message": "   "})
    assert res.status_code == 422
    err = res.json()["error"]
    assert err["code"] == "VALIDATION_ERROR" and err["message"] == "Message cannot be empty"
    long = client.post("/api/chat", json={"message": "x" * 20000})
    assert long.status_code == 422
    bad_id = client.post("/api/chat", json={"message": "hi", "conversation_id": "../../etc"})
    assert bad_id.status_code == 422


def test_documents_upload_rag_and_delete(client, stream):
    files = [
        ("files", ("../../evil/notes.md", b"# Notes\n\nThe chunk size is 1000 characters with 150 overlap.\n", "text/markdown")),
        ("files", ("tool.exe", b"MZ\x00\x00", "application/octet-stream")),
    ]
    res = client.post("/api/documents", files=files).json()
    ok = [r for r in res["results"] if r["status"] == "ok"]
    bad = [r for r in res["results"] if r["status"] == "error"]
    assert len(ok) == 1 and ok[0]["name"] == "notes.md"
    assert len(bad) == 1 and "isn't supported" in bad[0]["error"]
    doc_id = ok[0]["document"]["id"]
    assert [d["id"] for d in client.get("/api/documents").json()] == [doc_id]

    events = stream({"message": "What does my notes document say about chunk size?"})
    assert next(e for e in events if e["type"] == "route")["route"] == "rag"
    sources = next(e for e in events if e["type"] == "sources")["items"]
    assert sources[0]["title"] == "notes.md"
    assert events[-1]["message"]["metadata"]["sources"]

    assert client.delete(f"/api/documents/{doc_id}").status_code == 204
    assert client.get("/api/documents").json() == []
    # With the library empty, document questions fall back to chat.
    events = stream({"message": "What does my notes document say?"})
    assert next(e for e in events if e["type"] == "route")["route"] == "chat"


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_MB", "1")
    from agentic_chatbot.core.settings import reset_caches

    reset_caches()
    big = ("files", ("big.txt", b"a" * (1024 * 1024 + 10), "text/plain"))
    result = client.post("/api/documents", files=[big]).json()["results"][0]
    assert result["status"] == "error" and "larger than 1 MB" in result["error"]


def test_history_search_rename_export_delete(client, stream):
    conv = stream({"message": "Tell me about pgvector indexes"})[0]["conversation_id"]
    stream({"message": "Something unrelated about cooking"})

    found = client.get("/api/conversations", params={"q": "pgvector"}).json()
    assert [c["id"] for c in found] == [conv]

    renamed = client.patch(f"/api/conversations/{conv}", json={"title": "  Vector  notes "}).json()
    assert renamed["title"] == "Vector notes"

    export = client.get(f"/api/conversations/{conv}/export")
    assert export.status_code == 200 and export.text.startswith("# Vector notes")
    assert "attachment" in export.headers["content-disposition"]

    assert client.delete(f"/api/conversations/{conv}").status_code == 204
    assert client.get(f"/api/conversations/{conv}").status_code == 404
    assert client.delete("/api/conversations").status_code == 400
    assert client.delete("/api/conversations?confirm=true").json()["deleted"] == 1


def test_api_key_auth(client, monkeypatch):
    monkeypatch.setenv("API_KEYS", "secret-one,secret-two")
    from agentic_chatbot.core.settings import reset_caches

    reset_caches()
    assert client.get("/api/conversations").status_code == 401
    assert client.get("/api/conversations", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/conversations", headers={"Authorization": "Bearer secret-two"}).status_code == 200
    assert client.get("/api/conversations", headers={"X-API-Key": "secret-one"}).status_code == 200
    assert client.get("/health").status_code == 200  # probes stay open
    assert client.get("/api/meta").json()["auth_required"] is True


def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "2")
    from agentic_chatbot.core.settings import reset_caches

    reset_caches()
    assert client.post("/api/chat", json={"message": "one"}).status_code == 200
    assert client.post("/api/chat", json={"message": "two"}).status_code == 200
    blocked = client.post("/api/chat", json={"message": "three"})
    assert blocked.status_code == 429 and "Retry-After" in blocked.headers


def test_missing_api_key_reports_clearly(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from agentic_chatbot.components.llm_loader import reset_llm_cache
    from agentic_chatbot.core.settings import reset_caches

    reset_caches()
    reset_llm_cache()
    assert client.get("/ready").status_code == 503
    meta = client.get("/api/meta").json()
    assert meta["llm_ready"] is False and "ANTHROPIC_API_KEY" in meta["llm_error"]
    with client.stream("POST", "/api/chat/stream", json={"message": "hi"}) as res:
        events = parse_sse(res.read().decode())
    err = next(e for e in events if e["type"] == "error")
    assert err["code"] == "LLM_NOT_CONFIGURED" and "ANTHROPIC_API_KEY" in err["message"]
