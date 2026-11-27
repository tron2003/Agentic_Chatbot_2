"""Routing: explicit research requests reach Research even when the router model fails."""

import asyncio

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.entity.router import Router
from agentic_chatbot.nodes import router_node as rn
from agentic_chatbot.prompts.agent_prompt import FILE_TOOLS_NOTE, NO_WEB_NOTE, build_agent_prompt

VANGUARD = "research about company call vanguard and which company they have their investments"


def test_keyword_fallback_sends_research_requests_to_research():
    # This message used to fall through to chat ("General conversation.").
    assert rn.heuristic_route(VANGUARD, False).route == "agent"
    assert rn.heuristic_route("who is the ceo of vanguard", False).route == "agent"
    assert rn.heuristic_route("hi dude", False).route == "chat"
    assert rn.heuristic_route("explain the difference between RAG and fine-tuning", False).route == "chat"


@pytest.mark.parametrize(
    "text",
    [VANGUARD, "research about how microplastics are very bad ?", "can you look up the population of Tokyo", "find out who won", "please look it up"],
)
def test_explicit_research_overrides_a_chat_decision(text):
    out = rn.apply_research_intent(Router(route="chat", reason="General conversation."), text)
    assert out.route == "agent"


def test_research_override_leaves_other_decisions_alone():
    assert rn.apply_research_intent(Router(route="chat", reason="x"), "write a haiku about rain").route == "chat"
    assert rn.apply_research_intent(Router(route="rag", reason="x"), "research what my pdf says").route == "rag"


class _FakeRouterLLM:
    """Structured output always fails; the plain call returns `plain` (or raises if None)."""

    def __init__(self, plain):
        self.plain = plain

    def with_structured_output(self, schema):
        class _Broken:
            async def ainvoke(self, *a, **k):
                raise ValueError("model returned invalid JSON")

        return _Broken()

    async def ainvoke(self, *a, **k):
        if self.plain is None:
            raise RuntimeError("429 rate limited")
        return AIMessage(content=self.plain)


def _route(monkeypatch, text, plain):
    monkeypatch.setattr(rn, "get_llm", lambda role="main": _FakeRouterLLM(plain))
    state = Chatbot(messages=[HumanMessage(content=text)])
    return asyncio.run(rn.router_node(state, {"configurable": {}}))["route"]


def test_plain_answer_is_used_when_structured_output_fails(monkeypatch):
    assert _route(monkeypatch, "who is the current CEO of Vanguard", "agent") == "agent"
    assert _route(monkeypatch, "hi dude", "Route: chat") == "chat"


def test_keyword_fallback_when_the_router_model_is_down(monkeypatch):
    assert _route(monkeypatch, VANGUARD, None) == "agent"
    assert _route(monkeypatch, "hi dude", None) == "chat"


def test_agent_prompt_says_when_web_search_is_off():
    no_web = build_agent_prompt(["calculator", "read_file", "list_directory"], None)
    assert NO_WEB_NOTE in no_web and FILE_TOOLS_NOTE in no_web
    with_web = build_agent_prompt(["web_search", "calculator"], None)
    assert NO_WEB_NOTE not in with_web and FILE_TOOLS_NOTE not in with_web


def test_naming_a_tool_routes_to_the_agent():
    from agentic_chatbot.entity.router import Router
    from agentic_chatbot.nodes.router_node import apply_tool_intent

    chat = Router(route="chat", reason="General conversation.")
    tools = ["web_search", "write_file", "calculator"]
    assert apply_tool_intent(chat, "Use the write_file tool to create hello.txt", tools).route == "agent"
    assert apply_tool_intent(chat, "I need to rewrite_files soon", tools).route == "chat"
    assert apply_tool_intent(chat, "what's a calculator?", tools).route == "chat", "plain words never count"
