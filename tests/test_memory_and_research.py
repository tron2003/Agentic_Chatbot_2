"""Short-term memory (token window + summarise block), long-term memory (store + blocks + API)
and Deep research (plan, parallel workers, report). No network: web search is stubbed."""

import asyncio

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agentic_chatbot.entity.chat_state import Chatbot, merge_notes
from agentic_chatbot.nodes import research_nodes, summarizer_node
from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline
from agentic_chatbot.services import long_term_memory as ltm
from agentic_chatbot.utils.message_builder import context_window, count_tokens


def _drain(pipeline, thread, message, **kw):
    async def go():
        return [e async for e in pipeline.stream(thread, message, **kw)]

    return asyncio.run(go())


# ── short-term memory ──────────────────────────────────────────────────────

def test_context_window_keeps_newest_turns_within_token_budget():
    long = "word " * 2000  # ~2,000+ tokens
    msgs = [
        HumanMessage(content="first question", id="1"), AIMessage(content=long, id="2"),
        HumanMessage(content="second question", id="3"), AIMessage(content="short answer", id="4"),
        HumanMessage(content="latest question", id="5"),
    ]
    window = context_window(msgs, max_tokens=500, max_messages=20)
    assert [m.id for m in window] == ["3", "4", "5"], "the long old answer is dropped, newest turns kept"
    assert isinstance(window[0], HumanMessage)
    assert count_tokens(window) <= 500


def test_context_window_always_keeps_the_latest_message():
    huge = HumanMessage(content="x " * 5000, id="1")
    assert context_window([huge], max_tokens=10) == [huge]


def test_summary_triggers_on_tokens_not_just_message_count(monkeypatch):
    monkeypatch.setattr(summarizer_node, "_limits", lambda: (100, 2, 300))
    few_but_long = [HumanMessage(content="q " * 400, id="1"), AIMessage(content="a " * 400, id="2"),
                    HumanMessage(content="next", id="3")]
    assert summarizer_node.should_summarize(Chatbot(messages=few_but_long))
    assert not summarizer_node.should_summarize(Chatbot(messages=few_but_long[:2]))


def test_merge_notes_reducer_appends_and_resets():
    assert merge_notes([{"a": 1}], [{"b": 2}]) == [{"a": 1}, {"b": 2}]
    assert merge_notes([{"a": 1}], None) == []


# ── long-term memory ───────────────────────────────────────────────────────

def test_memory_store_add_dedupe_update_delete_and_secrets():
    store = InMemoryStore()

    async def go():
        a = await ltm.add_memory(store, "u", "Name is Kanish")
        again = await ltm.add_memory(store, "u", "name is kanish")
        assert again["id"] == a["id"], "same fact is refreshed, not duplicated"
        assert await ltm.add_memory(store, "u", "My API key is sk-abcdef123456") is None
        assert await ltm.add_memory(store, "u", "Card 4111 1111 1111 1111") is None
        await ltm.update_memory(store, "u", a["id"], "Name is Kanish S")
        items = await ltm.list_memories(store, "u")
        assert [m["content"] for m in items] == ["Name is Kanish S"]
        assert await ltm.delete_memory(store, "u", a["id"])
        assert await ltm.list_memories(store, "u") == []
        assert await ltm.list_memories(store, "someone-else") == []

    asyncio.run(go())


def test_remember_block_saves_facts_and_recall_uses_them_in_a_new_chat():
    store = InMemoryStore()
    pipeline = ChatbotPipeline(InMemorySaver(), store=store)

    events = _drain(pipeline, "chat-1", "Hi, my name is Kanish and I build LangGraph agents")
    saved = [e for e in events if e["type"] == "step" and e["step"]["title"] == "Updated long-term memory"]
    assert saved, "the remember block reports what it saved"

    memories = asyncio.run(ltm.list_memories(store, ltm.default_user_id()))
    assert any("Kanish" in m["content"] for m in memories)

    # A different conversation (new thread) still knows the user, without a "Recalled" stop in the timeline.
    events = _drain(pipeline, "chat-2", "what should we build today?")
    assert not [e for e in events if e["type"] == "step" and e["step"]["title"].startswith("Recalled")]
    state = asyncio.run(pipeline.workflow.aget_state({"configurable": {"thread_id": "chat-2"}}))
    assert "Kanish" in (state.values.get("user_memories") or "")


def test_small_talk_costs_no_memory_call(monkeypatch):
    calls = []

    async def spy(*args, **kwargs):
        calls.append(1)
        raise AssertionError("should not be called")

    from agentic_chatbot.nodes import memory_nodes

    monkeypatch.setattr(memory_nodes, "_extract", spy)
    pipeline = ChatbotPipeline(InMemorySaver(), store=InMemoryStore())
    _drain(pipeline, "t", "explain the difference between RAG and fine-tuning")
    assert calls == []


def test_memory_api_lists_adds_and_deletes(client):
    body = client.get("/api/memory").json()
    assert body["enabled"] is True and body["backend"] == "memory" and body["items"] == []

    created = client.post("/api/memory", json={"content": "Prefers answers in Python"})
    assert created.status_code == 201
    mid = created.json()["id"]
    assert [m["content"] for m in client.get("/api/memory").json()["items"]] == ["Prefers answers in Python"]

    assert client.post("/api/memory", json={"content": "my password is hunter22"}).status_code == 422
    assert client.delete(f"/api/memory/{mid}").status_code == 204
    assert client.delete(f"/api/memory/{mid}").status_code == 404
    assert client.delete("/api/memory").status_code == 400
    assert client.delete("/api/memory?confirm=true").json() == {"deleted": 0}

    meta = client.get("/api/meta").json()
    assert meta["memory"] == {"short_term": "memory", "long_term": "memory"}


# ── Deep research ──────────────────────────────────────────────────────────

def _fake_search(monkeypatch):
    queries = []

    async def fake(query):
        queries.append(query)
        slug = abs(hash(query)) % 1000
        return "duckduckgo", None, [
            {"title": f"Result for {query}", "url": f"https://example.com/{slug}", "content": f"Facts about {query}."},
            {"title": "Shared page", "url": "https://example.com/shared", "content": "Shared context."},
        ], ""

    monkeypatch.setattr(research_nodes, "search_results", fake)
    monkeypatch.setattr(research_nodes, "web_search_available", lambda: True)
    return queries


def test_deep_research_plans_searches_in_parallel_and_writes_cited_report(monkeypatch):
    queries = _fake_search(monkeypatch)
    pipeline = ChatbotPipeline(InMemorySaver(), store=InMemoryStore())
    events = _drain(pipeline, "r1", "Vanguard's biggest holdings", mode="deep_research")

    route = next(e for e in events if e["type"] == "route")
    assert route["route"] == "agent" and route["label"] == "Deep research"

    workers = {e["step"]["id"] for e in events if e["type"] == "step" and e["step"]["id"].startswith("research-1-")}
    assert len(workers) == 3 and len(queries) == 3, "one parallel search per planned sub-question"

    sources = next(e for e in events if e["type"] == "sources")["items"]
    urls = [s["url"] for s in sources]
    assert len(urls) == len(set(urls)) == 4, "the shared page is numbered once"
    assert [s["index"] for s in sources] == [1, 2, 3, 4]

    answer = next(e for e in events if e["type"] == "answer")
    assert answer["route"] == "agent" and "Research report" in answer["content"]
    assert "](https://example.com/" in answer["content"], "citations link to the sources"

    state = asyncio.run(pipeline.workflow.aget_state({"configurable": {"thread_id": "r1"}}))
    assert state.values["research_notes"] == [], "notes are cleared after the report"


def test_sources_are_capped_balanced_and_trimmed_for_the_writer():
    notes = [
        {"round": 1, "index": i, "question": f"q{i}", "query": f"q{i}", "docs": [],
         "results": [{"title": f"r{i}-{k}", "url": f"https://x.com/{i}/{k}", "content": "y" * 3000} for k in range(5)]}
        for i in range(4)
    ]
    sources, block = research_nodes.number_sources(notes, max_sources=6, budget_chars=1200)
    assert len(sources) == 6
    # round-robin: every sub-question's best result comes before anyone's second
    assert [s["title"] for s in sources[:4]] == ["r0-0", "r1-0", "r2-0", "r3-0"]
    assert len(block) < 6 * 200 + 6 * 120, "each excerpt is trimmed to its share of the budget"


def test_empty_report_is_retried_then_falls_back_to_the_sources(monkeypatch):
    _fake_search(monkeypatch)
    calls = []

    class Silent:
        async def ainvoke(self, messages, config=None):
            calls.append(len(messages[0].content))
            return AIMessage(content="")

    real = research_nodes.get_llm
    monkeypatch.setattr(research_nodes, "get_llm", lambda role="main": Silent() if role == "main" else real(role))
    pipeline = ChatbotPipeline(InMemorySaver(), store=InMemoryStore())
    events = _drain(pipeline, "r2", "research solar panel prices", mode="deep_research")
    assert len(calls) == 2 and calls[1] < calls[0], "the retry sends a smaller prompt"
    answer = next(e for e in events if e["type"] == "answer")["content"]
    assert answer.startswith("## Research notes") and "https://example.com/" in answer


def test_quick_lookups_skip_planning(monkeypatch):
    _fake_search(monkeypatch)
    state = Chatbot(messages=[HumanMessage(content="what's the weather in Pune today")])
    assert asyncio.run(research_nodes.choose_depth(state)) == "quick"
    state = Chatbot(messages=[HumanMessage(content="research the EV battery market")])
    assert asyncio.run(research_nodes.choose_depth(state)) == "deep"


def test_no_search_available_means_quick(monkeypatch):
    monkeypatch.setattr(research_nodes, "web_search_available", lambda: False)
    state = Chatbot(messages=[HumanMessage(content="research everything about Vanguard")], mode="deep_research")
    assert asyncio.run(research_nodes.choose_depth(state)) == "quick"


def test_chat_request_accepts_deep_research_mode(client, stream, monkeypatch):
    _fake_search(monkeypatch)
    events = stream({"message": "compare Postgres and MongoDB", "mode": "deep_research"})
    assert next(e for e in events if e["type"] == "route")["label"] == "Deep research"
    done = next(e for e in events if e["type"] == "done")
    assert done["message"]["metadata"]["mode"] == "deep_research"
    assert client.post("/api/chat", json={"message": "x", "mode": "turbo"}).status_code == 422


def test_plain_json_replies_are_parsed_first():
    from agentic_chatbot.nodes.memory_nodes import MemoryOps
    from agentic_chatbot.utils.structured import parse_json_model

    reply = '<think>hmm</think>```json\n{"add": ["Prefers Python"], "update": [], "delete": []}\n```'
    assert parse_json_model(MemoryOps, reply).add == ["Prefers Python"]
    import pytest

    with pytest.raises(ValueError):
        parse_json_model(MemoryOps, "no json here")


def test_ollama_is_not_started_when_autostart_is_off():
    from agentic_chatbot.components.ollama_service import ensure_ollama

    assert ensure_ollama("http://127.0.0.1:1") is False  # nothing listens on port 1; tests disable autostart
