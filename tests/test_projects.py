"""Projects: their own chats, documents and instructions, kept apart from everything else."""

import asyncio

from agentic_chatbot.core.scope import Scope, build_scope, use_scope
from agentic_chatbot.prompts.prompt import build_chat_prompt
from agentic_chatbot.services.spreadsheets import sheets_available


def _upload(client, name: str, text: str, project_id: str | None = None) -> str:
    data = {"project_id": project_id} if project_id else {}
    res = client.post("/api/documents", files=[("files", (name, text.encode(), "text/markdown"))], data=data).json()
    assert res["results"][0]["status"] == "ok", res
    return res["results"][0]["document"]["id"]


def _project(client, name="Thesis", instructions="") -> dict:
    res = client.post("/api/projects", json={"name": name, "instructions": instructions})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_list_rename_and_counts(client, stream):
    p = _project(client, "  Thesis   work ", "Answer in British English.")
    assert p["name"] == "Thesis work" and p["instructions"] == "Answer in British English."
    _upload(client, "ch1.md", "# Chapter one\n\nGraph neural networks.", p["id"])
    stream({"message": "hello", "project_id": p["id"]})
    listed = client.get("/api/projects").json()
    assert listed[0]["id"] == p["id"] and listed[0]["chat_count"] == 1 and listed[0]["document_count"] == 1
    renamed = client.patch(f"/api/projects/{p['id']}", json={"name": "Thesis 2026"}).json()
    assert renamed["name"] == "Thesis 2026" and renamed["instructions"] == "Answer in British English."
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422
    assert client.get("/api/projects/p_missing").status_code == 404


def test_chats_and_documents_stay_in_their_project(client, stream):
    p = _project(client)
    in_project = _upload(client, "thesis-notes.md", "# Thesis notes\n\nThe thesis studies graph neural networks.", p["id"])
    general = _upload(client, "shopping.md", "# Shopping notes\n\nBuy oat milk and coffee beans.")

    events = stream({"message": "What does my notes document say?", "project_id": p["id"]})
    cid = events[0]["conversation_id"]
    assert next(e for e in events if e["type"] == "route")["route"] == "rag"
    titles = {s["title"] for s in next(e for e in events if e["type"] == "sources")["items"]}
    assert titles == {"thesis-notes.md"}, "a project chat only reads the project's documents"

    events = stream({"message": "What does my notes document say?"})
    titles = {s["title"] for s in next(e for e in events if e["type"] == "sources")["items"]}
    assert titles == {"shopping.md"}, "a general chat never reads a project's documents"

    # A follow-up stays in the project even if the client sends another project id.
    stream({"message": "and the document again?", "conversation_id": cid, "project_id": "p_other"})
    assert client.get(f"/api/conversations/{cid}").json()["conversation"]["project_id"] == p["id"]

    assert [c["id"] for c in client.get(f"/api/conversations?project={p['id']}").json()] == [cid]
    assert cid not in [c["id"] for c in client.get("/api/conversations?project=none").json()]
    assert [d["id"] for d in client.get(f"/api/documents?project={p['id']}").json()] == [in_project]
    assert [d["id"] for d in client.get("/api/documents?project=none").json()] == [general]


def test_empty_project_doesnt_route_to_documents(client, stream):
    _upload(client, "notes.md", "# Notes\n\nGeneral library notes.")
    p = _project(client)
    events = stream({"message": "What does my notes document say?", "project_id": p["id"]})
    assert next(e for e in events if e["type"] == "route")["route"] == "chat"


def test_instructions_reach_every_prompt(client):
    scope = Scope(project_id="p_1", name="Thesis", instructions="Always cite chapter numbers.")
    with use_scope(scope):
        prompt = build_chat_prompt(None)
    assert 'project "Thesis"' in prompt and "Always cite chapter numbers." in prompt
    assert "Project" not in build_chat_prompt(None).split("What you know")[0], "nothing outside projects"


def test_build_scope_and_spreadsheets_follow_the_project(client):
    p = _project(client)
    sheet = client.post("/api/documents", files=[("files", ("costs.csv", b"item,amount\npaper,10\nink,5\n", "text/csv"))],
                        data={"project_id": p["id"]}).json()["results"][0]["document"]["id"]
    inside = asyncio.run(build_scope(p["id"]))
    outside = asyncio.run(build_scope(None))
    assert inside.doc_ids == {sheet} and outside.doc_ids == frozenset()
    with use_scope(inside):
        assert sheets_available()
    with use_scope(outside):
        assert not sheets_available(), "a project's spreadsheet isn't visible outside it"


def test_unknown_project_and_delete_cascade(client, stream):
    res = client.post("/api/chat/stream", json={"message": "hi", "project_id": "p_nope"})
    assert res.status_code == 404
    p = _project(client)
    doc = _upload(client, "a.md", "# A\n\ntext", p["id"])
    cid = stream({"message": "hello", "project_id": p["id"]})[0]["conversation_id"]
    assert client.delete(f"/api/projects/{p['id']}").status_code == 400, "needs confirm=true"
    out = client.delete(f"/api/projects/{p['id']}?confirm=true").json()
    assert out == {"deleted": p["id"], "chats": 1, "documents": 1}
    assert client.get(f"/api/conversations/{cid}").status_code == 404
    assert doc not in [d["id"] for d in client.get("/api/documents").json()]
    assert client.get("/api/projects").json() == []
