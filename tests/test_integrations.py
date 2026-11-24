"""Optional integrations: external agents (OpenClaw-style), OpenAI-compatible API,
webhooks and the MCP server. External services are simulated with httpx.MockTransport;
the MCP test drives a real server with the official MCP client."""

import asyncio
import hashlib
import hmac
import json
import socket
import threading
import time

import httpx
import pytest
import yaml

from agentic_chatbot.integrations import agent_bridge
from tests.conftest import parse_sse


def write_config(tmp_path, monkeypatch, data: dict):
    path = tmp_path / "integrations.yaml"
    path.write_text(yaml.safe_dump(data))
    monkeypatch.setenv("INTEGRATIONS_CONFIG_PATH", str(path))
    from agentic_chatbot.core.settings import reset_caches
    from agentic_chatbot.integrations.config import reset_integrations

    reset_caches()
    reset_integrations()


class FakeServices:
    """Records every outbound HTTP request and answers like OpenClaw would."""

    def __init__(self, fail: bool = False):
        self.requests: list[httpx.Request] = []
        self.fail = fail

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"object": "list", "data": [{"id": "openclaw/default"}]})
        if request.url.path.endswith("/chat/completions"):
            task = json.loads(request.content)["messages"][0]["content"]
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": f"Sent it. ({task[:30]})"}}]})
        return httpx.Response(200, json={"ok": True})

    def install(self, monkeypatch):
        transport = httpx.MockTransport(self.handler)
        monkeypatch.setattr(agent_bridge, "client_factory", lambda timeout: httpx.AsyncClient(transport=transport, timeout=timeout))
        return self

    def to(self, suffix: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path.endswith(suffix)]

    def wait_for(self, suffix: str, count: int = 1, timeout: float = 3.0) -> list[httpx.Request]:
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.to(suffix)
            if len(found) >= count:
                return found
            time.sleep(0.02)
        return self.to(suffix)


OPENCLAW = {
    "enabled": True,
    "label": "OpenClaw",
    "base_url": "http://claw.test/v1",
    "api_key": "gateway-token",
    "model": "openclaw/default",
    "description": "Sends messages on the user's chat apps and sets reminders.",
}


# ── external agents ──────────────────────────────────────────────────────────


def test_delegates_to_external_agent_with_session_and_auth(tmp_path, monkeypatch, client, stream):
    fake = FakeServices().install(monkeypatch)
    write_config(tmp_path, monkeypatch, {"agents": {"openclaw": OPENCLAW}})

    events = stream({"message": "Ask openclaw to message Priya that I'm running late"})
    assert next(e for e in events if e["type"] == "route")["route"] == "agent"
    steps = [e["step"] for e in events if e["type"] == "step" and e["step"].get("tool") == "ask_openclaw"]
    assert steps[0]["title"] == "Asking OpenClaw"
    assert [s["status"] for s in steps] == ["running", "done"]

    call = fake.to("/chat/completions")[0]
    body = json.loads(call.content)
    conversation_id = events[0]["conversation_id"]
    assert str(call.url) == "http://claw.test/v1/chat/completions"
    assert call.headers["authorization"] == "Bearer gateway-token"
    assert body["model"] == "openclaw/default"
    assert body["user"] == f"junction:{conversation_id}", "each conversation keeps its own OpenClaw session"
    assert "Priya" in body["messages"][0]["content"]
    assert "Sent it." in events[-1]["message"]["content"]

    integrations = client.get("/api/integrations?refresh=true").json()["items"]
    assert {"name": "openclaw", "status": "ok"}.items() <= next(i for i in integrations if i["name"] == "openclaw").items()


def test_unreachable_agent_is_reported_not_fatal(tmp_path, monkeypatch, stream):
    FakeServices(fail=True).install(monkeypatch)
    write_config(tmp_path, monkeypatch, {"agents": {"openclaw": OPENCLAW}})
    events = stream({"message": "ask openclaw to set a reminder for 6pm"})
    step = [e["step"] for e in events if e["type"] == "step" and e["step"].get("tool") == "ask_openclaw"][-1]
    assert step["status"] == "error" and "Couldn't reach OpenClaw" in step["result"]
    assert events[-1]["type"] == "done"


def test_disabled_agents_add_no_tools(client):
    assert not any(t.startswith("ask_") for t in client.get("/api/meta").json()["tools"])


# ── OpenAI-compatible API ────────────────────────────────────────────────────


def test_openai_api_off_by_default(client):
    assert client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 404


@pytest.fixture
def oai(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"openai_api": {"enabled": True, "model_name": "junction"}})


def test_openai_models_and_stateless_completion(oai, client):
    assert client.get("/v1/models").json()["data"][0]["id"] == "junction"
    res = client.post("/v1/chat/completions", json={
        "model": "junction",
        "messages": [
            {"role": "system", "content": "You are OpenClaw. (client prompt, ignored)"},
            {"role": "user", "content": "My name is Kanish"},
            {"role": "assistant", "content": "Nice to meet you."},
            {"role": "user", "content": [{"type": "text", "text": "hello there"}]},
        ],
        "tools": [{"type": "function", "function": {"name": "exec", "parameters": {}}}],
    })
    body = res.json()
    assert res.status_code == 200 and body["object"] == "chat.completion"
    assert body["choices"][0]["finish_reason"] == "stop"
    assert "hello there" in body["choices"][0]["message"]["content"]
    assert "tool_calls" not in body["choices"][0]["message"]
    assert client.get("/api/conversations").json() == [], "stateless calls aren't stored"

    checkpointer = client.app.state.pipeline.checkpointer
    deadline = time.time() + 2
    while time.time() < deadline and any(str(k).startswith("oai_tmp_") for k in checkpointer.storage):
        time.sleep(0.02)
    assert not any(str(k).startswith("oai_tmp_") for k in checkpointer.storage), "temporary threads are cleaned up"


def test_openai_streaming_chunks_and_withheld_planning(oai, client):
    with client.stream("POST", "/v1/chat/completions", json={
        "model": "junction", "stream": True, "messages": [{"role": "user", "content": "what is 6 * 7?"}],
    }) as res:
        raw = res.read().decode()
    assert raw.rstrip().endswith("data: [DONE]")
    chunks = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: {")]
    assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"
    assert chunks[-1]["junction"]["route"] == "agent"
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert "42" in text
    assert "Let me work that out" not in text, "agent planning must not leak into an OpenAI stream"


def test_openai_stateful_sessions_show_in_sidebar(oai, client):
    first = client.post("/v1/chat/completions", json={"user": "whatsapp:+91000", "messages": [{"role": "user", "content": "hi"}]})
    conv = first.headers["x-junction-conversation"]
    client.post("/v1/chat/completions", json={"user": "whatsapp:+91000", "messages": [
        {"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}, {"role": "user", "content": "and again"},
    ]})
    detail = client.get(f"/api/conversations/{conv}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert [m["content"] for m in detail["messages"] if m["role"] == "user"] == ["hi", "and again"]
    assert detail["messages"][0]["metadata"]["source"] == "openai_api"


def test_openai_api_keys(tmp_path, monkeypatch, client):
    write_config(tmp_path, monkeypatch, {"openai_api": {"enabled": True, "api_keys": "k-one,k-two"}})
    from fastapi.testclient import TestClient

    from agentic_chatbot.api.app import create_app

    with TestClient(create_app()) as c:
        msg = {"messages": [{"role": "user", "content": "hi"}]}
        assert c.post("/v1/chat/completions", json=msg).status_code == 401
        assert c.post("/v1/chat/completions", json=msg, headers={"Authorization": "Bearer k-two"}).status_code == 200


# ── webhooks ─────────────────────────────────────────────────────────────────


def test_webhooks_signed_json_and_openclaw_hooks(tmp_path, monkeypatch, client, stream):
    fake = FakeServices().install(monkeypatch)
    write_config(tmp_path, monkeypatch, {"webhooks": [
        {"name": "n8n", "enabled": True, "format": "json", "url": "http://n8n.test/hook", "secret": "s3cret", "events": ["*"]},
        {"name": "claw", "enabled": True, "format": "openclaw_agent", "url": "http://claw.test/hooks/agent",
         "token": "hook-token", "events": ["document.ingested"], "deliver": True, "channel": "whatsapp", "to": "+911"},
    ]})

    client.post("/api/documents", files=[("files", ("notes.md", b"# Notes\nSome text about pgvector.", "text/markdown"))])
    claw = fake.wait_for("/hooks/agent")
    n8n = fake.wait_for("/hook")
    assert len(claw) == 1 and claw[0].headers["authorization"] == "Bearer hook-token"
    claw_body = json.loads(claw[0].content)
    assert "notes.md" in claw_body["message"] and claw_body["deliver"] is True
    assert claw_body["channel"] == "whatsapp" and claw_body["to"] == "+911"
    assert claw[0].headers["idempotency-key"].startswith("evt_")

    ingest = next(r for r in n8n if r.headers["x-junction-event"] == "document.ingested")
    expected = "sha256=" + hmac.new(b"s3cret", ingest.content, hashlib.sha256).hexdigest()
    assert ingest.headers["x-junction-signature"] == expected
    assert json.loads(ingest.content)["data"]["name"] == "notes.md"

    stream({"message": "hello"})
    events = {r.headers.get("x-junction-event") for r in fake.wait_for("/hook", count=3)}
    assert {"conversation.created", "answer.completed"} <= events
    assert len(fake.to("/hooks/agent")) == 1, "OpenClaw hook only subscribed to document.ingested"


def test_invalid_integrations_file_is_reported(tmp_path, monkeypatch, client):
    write_config(tmp_path, monkeypatch, {"webhooks": [{"name": "x", "enabled": True, "url": "http://x", "events": ["nope"]}]})
    meta = client.get("/api/meta").json()
    assert "invalid" in meta["integrations"]["error"]
    assert client.get("/health").status_code == 200


# ── MCP server ───────────────────────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    write_config(tmp_path, monkeypatch, {"mcp_server": {"enabled": True, "api_keys": "mcp-key"}})
    import uvicorn

    from agentic_chatbot.api.app import create_app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_mcp_server_with_official_client(live_server):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    async def run():
        async with streamablehttp_client(f"{live_server}/mcp", headers={"Authorization": "Bearer mcp-key"}) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                tools = {t.name for t in (await session.list_tools()).tools}
                result = await session.call_tool("ask", {"question": "what is 2 + 3?"})
                docs = await session.call_tool("list_documents", {})
                return tools, result, docs

    tools, result, docs = asyncio.run(run())
    assert tools == {"ask", "search_documents", "list_documents"}
    payload = result.structuredContent or json.loads(result.content[0].text)
    assert payload["route"] == "agent" and "5" in payload["answer"]
    assert payload["conversation_id"]
    assert not docs.isError

    denied = httpx.post(f"{live_server}/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert denied.status_code == 401


def test_parse_sse_helper_handles_openai_lines():
    assert parse_sse('data: {"a": 1}\n\n') == [{"a": 1}]
