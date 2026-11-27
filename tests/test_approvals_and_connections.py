"""Approval step (pause before act tools, approve, decline, drop) and the Connections panel API."""

import asyncio

import pytest
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import InMemorySaver

from agentic_chatbot.mcp.mcp_manager import mcp_manager
from agentic_chatbot.services import connections, tool_policy
from tests.conftest import parse_sse
from tests.test_integrations import OPENCLAW, FakeServices, write_config


def _tool(name: str, server: str | None = None, calls: list | None = None, **meta) -> StructuredTool:
    async def _run() -> str:
        if calls is not None:
            calls.append(name)
        return f"{name} done"

    tool = StructuredTool.from_function(coroutine=_run, name=name, description=f"Test tool {name}.")
    tool.metadata = {**meta, **({"mcp_server": server} if server else {})}
    return tool


def _approve(client, first: list[dict], decision: str = "approve", always_allow: list[str] | None = None):
    paused = next(e for e in first if e["type"] == "approval_required")
    body = {"conversation_id": first[0]["conversation_id"], "message_id": first[0]["message_id"],
            "decisions": {a["id"]: decision for a in paused["actions"]}, "always_allow": always_allow or []}
    with client.stream("POST", "/api/chat/approve", json=body) as res:
        return res.status_code, (parse_sse(res.read().decode()) if res.status_code == 200 else res.read())


def _enable_mcp(monkeypatch):
    from agentic_chatbot.core.settings import reset_caches

    monkeypatch.setenv("ENABLE_MCP", "true")
    reset_caches()


# ── policy ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,kind", [
    ("list_issues", "read"), ("get_file_contents", "read"), ("search_repositories", "read"), ("directory_tree", "read"),
    ("read_multiple_files", "read"), ("get_label", "read"), ("listAllowedDirectories", "read"),
    ("create_issue", "act"), ("write_file", "act"), ("send_message", "act"), ("create_or_update_file", "act"),
    ("get_or_create_page", "act"), ("push_files", "act"), ("frobnicate", "act"),
])
def test_tool_kind_from_name(name, kind):
    assert tool_policy.kind_from_name(name) == kind


def test_kind_hints_builtins_and_agents():
    assert tool_policy.tool_kind(_tool("frobnicate", "x", readOnlyHint=True)) == "read"
    assert tool_policy.tool_kind(_tool("list_things", "x", readOnlyHint=False)) == "act"
    assert tool_policy.tool_kind(_tool("list_things", "x", destructiveHint=True)) == "act"
    assert tool_policy.tool_kind(_tool("web_search")) == "read"
    assert tool_policy.tool_kind(_tool("ask_openclaw")) == "act"
    assert tool_policy.tool_key(_tool("create_issue", "github")) == "github/create_issue"


def test_settings_override_and_global_switch(monkeypatch):
    act, read = _tool("create_issue", "github"), _tool("list_issues", "github")
    assert (tool_policy.decide(act), tool_policy.decide(read)) == ("ask", "run")
    connections.set_tool_setting("github/create_issue", "auto")
    connections.set_tool_setting("github/list_issues", "off")
    assert (tool_policy.decide(act), tool_policy.decide(read)) == ("run", "off")
    assert tool_policy.visible([act, read]) == [act]
    connections.set_tool_setting("github/create_issue", None)
    monkeypatch.setenv("TOOL_APPROVALS", "off")
    assert tool_policy.decide(act) == "run"


# ── approval step ────────────────────────────────────────────────────────────


def test_decline_runs_nothing_and_is_recorded(tmp_path, monkeypatch, client, stream):
    fake = FakeServices().install(monkeypatch)
    write_config(tmp_path, monkeypatch, {"agents": {"openclaw": OPENCLAW}})
    first = stream({"message": "ask openclaw to message Priya I'm late"})
    paused = first[-1]["message"]
    assert paused["metadata"]["pending_approval"]["actions"][0]["tool"] == "ask_openclaw"
    assert paused["metadata"]["pending_approval"]["actions"][0]["key"] == "agents/ask_openclaw"

    code, events = _approve(client, first, "decline")
    assert code == 200
    step = [e["step"] for e in events if e["type"] == "step" and e["step"].get("tool") == "ask_openclaw"][-1]
    assert step["status"] == "declined"
    assert not fake.to("/chat/completions")
    meta = events[-1]["message"]["metadata"]
    assert meta["approvals"][0]["decision"] == "decline" and "pending_approval" not in meta
    assert "declined" in events[-1]["message"]["content"]

    code, body = _approve(client, first)
    assert code == 409, "a finished answer can't be approved again"


def test_new_message_drops_the_waiting_action(tmp_path, monkeypatch, client, stream):
    fake = FakeServices().install(monkeypatch)
    write_config(tmp_path, monkeypatch, {"agents": {"openclaw": OPENCLAW}})
    first = stream({"message": "ask openclaw to book a table"})
    cid = first[0]["conversation_id"]
    later = stream({"message": "never mind, hello", "conversation_id": cid})
    assert later[-1]["type"] == "done" and not fake.to("/chat/completions")

    msgs = client.get(f"/api/conversations/{cid}").json()["messages"]
    paused = next(m for m in msgs if m["id"] == first[0]["message_id"])
    assert paused["metadata"]["approvals"][0]["decision"] == "dropped"
    assert "pending_approval" not in paused["metadata"]
    assert "new message was sent" in paused["content"]
    assert _approve(client, first)[0] == 409


def test_always_allow_skips_the_card_next_time(tmp_path, monkeypatch, client, stream):
    fake = FakeServices().install(monkeypatch)
    write_config(tmp_path, monkeypatch, {"agents": {"openclaw": OPENCLAW}})
    first = stream({"message": "ask openclaw to set a reminder"})
    code, _ = _approve(client, first, always_allow=["agents/ask_openclaw"])
    assert code == 200 and connections.tool_settings()["agents/ask_openclaw"] == "auto"

    again = stream({"message": "ask openclaw to set another reminder"})
    assert not any(e["type"] == "approval_required" for e in again)
    assert len(fake.to("/chat/completions")) == 2


def test_runs_with_nobody_to_approve_decline_act_tools(tmp_path, monkeypatch):
    """The OpenAI-compatible API and the MCP server run non-interactively."""
    fake = FakeServices().install(monkeypatch)
    write_config(tmp_path, monkeypatch, {"agents": {"openclaw": OPENCLAW}})
    from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline

    pipeline = ChatbotPipeline(InMemorySaver())

    async def run():
        return [e async for e in pipeline.stream("t-api", "ask openclaw to message Sam")]

    events = asyncio.run(run())
    assert not any(e["type"] == "approval_required" for e in events)
    step = [e["step"] for e in events if e["type"] == "step" and e["step"].get("tool") == "ask_openclaw"][-1]
    assert step["status"] == "declined" and "approval" in step["result"]
    assert not fake.to("/chat/completions")
    assert next(e for e in events if e["type"] == "answer")


def test_mcp_act_tool_pauses_and_read_tool_runs(monkeypatch, client, stream):
    _enable_mcp(monkeypatch)
    calls: list[str] = []
    tools = [_tool("create_note", calls=calls), _tool("list_notes", calls=calls)]

    async def fake_load(name, cfg, timeout):
        return tools

    monkeypatch.setattr(mcp_manager, "_load_server", fake_load)
    res = client.post("/api/connections", json={"name": "notes", "transport": "http", "url": "https://notes.test/mcp"})
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "connected"

    read = stream({"message": "please use list_notes"})
    assert not any(e["type"] == "approval_required" for e in read) and calls == ["list_notes"]

    first = stream({"message": "please use create_note"})
    assert any(e["type"] == "approval_required" for e in first) and calls == ["list_notes"]
    code, events = _approve(client, first)
    assert code == 200 and calls == ["list_notes", "create_note"]
    assert "create_note done" in events[-1]["message"]["content"]


# ── connections API ──────────────────────────────────────────────────────────


def test_connections_list_and_tool_settings(client):
    data = client.get("/api/connections").json()
    assert data["approvals"] is True and data["stdio_allowed"] is True
    builtin = {t["name"]: t for t in data["builtin"]}
    assert builtin["calculator"]["kind"] == "read" and builtin["calculator"]["decision"] == "run"

    assert client.put("/api/connections/tools", json={"key": "builtin/calculator", "setting": "off"}).status_code == 200
    assert "calculator" not in client.get("/api/meta").json()["tools"]
    assert client.put("/api/connections/tools", json={"key": "builtin/calculator", "setting": None}).status_code == 200
    assert "calculator" in client.get("/api/meta").json()["tools"]
    assert client.put("/api/connections/tools", json={"key": "nope", "setting": "auto"}).status_code == 422


def test_add_edit_switch_and_delete_a_server(monkeypatch, client):
    _enable_mcp(monkeypatch)

    async def fake_load(name, cfg, timeout):
        assert cfg["transport"] == "streamable_http" and cfg["headers"]["Authorization"] == "Bearer s3cret"
        return [_tool("search_docs", readOnlyHint=True), _tool("delete_doc")]

    monkeypatch.setattr(mcp_manager, "_load_server", fake_load)
    body = {"name": "docs", "label": "Team docs", "transport": "http", "url": "https://docs.test/mcp",
            "headers": {"Authorization": "Bearer s3cret"}}
    added = client.post("/api/connections", json=body).json()
    assert added["headers"]["Authorization"] == connections.MASK, "secrets never go back to the browser"
    kinds = {t["name"]: (t["kind"], t["decision"]) for t in added["tools"]}
    assert kinds == {"search_docs": ("read", "run"), "delete_doc": ("act", "ask")}

    assert client.post("/api/connections", json=body).status_code == 409
    assert client.post("/api/connections", json={**body, "name": "tools"}).status_code == 422

    edited = client.put("/api/connections/docs", json={**body, "label": "Docs", "headers": {"Authorization": connections.MASK}})
    assert edited.status_code == 200 and edited.json()["label"] == "Docs"
    assert connections.load()["servers"]["docs"]["headers"]["Authorization"] == "Bearer s3cret", "masked value kept"

    off = client.patch("/api/connections/docs", json={"enabled": False}).json()
    assert off["status"] == "disabled" and not off["tools"]
    assert not any(t.name == "search_docs" for t in mcp_manager.get_tools())

    assert client.delete("/api/connections/docs").status_code == 200
    assert client.get("/api/connections/docs/reconnect").status_code in (404, 405)
    assert all(s["name"] != "docs" for s in client.get("/api/connections").json()["servers"])


def test_failed_server_is_saved_with_its_error(monkeypatch, client):
    _enable_mcp(monkeypatch)

    async def boom(name, cfg, timeout):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(mcp_manager, "_load_server", boom)
    res = client.post("/api/connections", json={"name": "down", "transport": "sse", "url": "http://down.test/sse"})
    assert res.status_code == 201
    assert res.json()["status"] == "failed" and "connection refused" in res.json()["detail"]
    test = client.post("/api/connections/test", json={"name": "down2", "transport": "http", "url": "http://x.test/mcp"})
    assert test.json()["status"] == "failed"


def test_stdio_servers_need_permission(monkeypatch, client):
    from agentic_chatbot.core.settings import reset_caches

    monkeypatch.setenv("ALLOW_UI_STDIO", "false")
    reset_caches()
    body = {"name": "local", "transport": "stdio", "command": "npx", "args": ["-y", "some-server"]}
    res = client.post("/api/connections", json=body)
    assert res.status_code == 403 and "mcp_servers.yaml" in res.json()["detail"]
    bad = client.post("/api/connections/test", json={**body, "command": "npx; rm -rf /"})
    assert bad.status_code == 422


def test_file_servers_can_be_switched_but_not_deleted(tmp_path, monkeypatch, client):
    path = tmp_path / "mcp.yaml"
    path.write_text("servers:\n  files:\n    transport: stdio\n    command: definitely-not-installed-xyz\n    args: []\n")
    monkeypatch.setenv("MCP_CONFIG_PATH", str(path))
    _enable_mcp(monkeypatch)
    asyncio.run(mcp_manager.initialize())
    server = next(s for s in client.get("/api/connections").json()["servers"] if s["name"] == "files")
    assert server["origin"] == "file" and server["status"] == "skipped"
    assert client.delete("/api/connections/files").status_code == 409
    assert client.patch("/api/connections/files", json={"enabled": False}).json()["status"] == "disabled"
    assert connections.load()["file_servers"]["files"]["enabled"] is False
