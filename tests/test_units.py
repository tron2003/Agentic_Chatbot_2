import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agentic_chatbot.api.security import RateLimiter
from agentic_chatbot.core.settings import expand_env, pg_conninfo, sqlalchemy_uri
from agentic_chatbot.nodes.router_node import heuristic_route
from agentic_chatbot.services.chat_service import public_error
from agentic_chatbot.tools.math_tool import calculator, safe_eval
from agentic_chatbot.tools.pdf_tool import read_pdf
from agentic_chatbot.utils.document_loader import safe_filename
from agentic_chatbot.utils.message_builder import ThinkFilter, conversational, message_text, strip_think


def test_expand_env(monkeypatch):
    monkeypatch.setenv("X_MODEL", "claude-x")
    monkeypatch.delenv("X_MISSING", raising=False)
    out = expand_env({"a": "${X_MODEL}", "b": "${X_MISSING:-fallback}", "c": "${X_MISSING}", "d": "pre-${X_MODEL}", "n": "${X_NUM:-0.5}"})
    assert out == {"a": "claude-x", "b": "fallback", "c": None, "d": "pre-claude-x", "n": 0.5}


def test_db_uri_normalisation():
    assert pg_conninfo("postgresql+psycopg://u:p@h/db") == "postgresql://u:p@h/db"
    assert sqlalchemy_uri("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system.ini", "system.ini"),
        ("my report (v2).pdf", "my report (v2).pdf"),
        ("", "upload"),
        ("a<b>c|d.md", "a_b_c_d.md"),
    ],
)
def test_safe_filename(raw, expected):
    assert safe_filename(raw) == expected


def test_calculator_is_safe_and_exact():
    assert calculator.invoke({"expression": "1250 * 0.18 + 42"}).endswith("= 267")
    assert safe_eval("sqrt(16) + 2^3") == 12
    for evil in ["__import__('os').system('id')", "().__class__", "open('x')", "9**99999"]:
        assert calculator.invoke({"expression": evil}).startswith("Error")
    assert "division by zero" in calculator.invoke({"expression": "1/0"})


def test_read_pdf_is_confined_to_workspace():
    assert read_pdf.invoke({"file_path": "/etc/passwd"}).startswith("Access denied")
    assert read_pdf.invoke({"file_path": "../../.env"}).startswith("Access denied")


def test_message_text_handles_content_blocks():
    blocks = [{"type": "text", "text": "Hel"}, {"type": "tool_use", "id": "x"}, {"type": "text", "text": "lo"}]
    assert message_text(blocks) == "Hello"
    assert message_text(None) == ""


def test_think_filter_across_chunks():
    f = ThinkFilter()
    out = "".join(f.feed(c) for c in ["Hi <thi", "nk>secret plan</th", "ink> there", " <", "b>"]) + f.flush()
    assert out == "Hi there <b>"
    assert strip_think("<think>x</think>Answer") == "Answer"


def test_conversational_window_starts_with_user_and_drops_tool_calls():
    msgs = [
        HumanMessage("q1"), AIMessage("a1"),
        HumanMessage("q2"), AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": "1"}]),
        ToolMessage("r", tool_call_id="1"), AIMessage("a2"),
        HumanMessage("q3"),
    ]
    window = conversational(msgs, 4)
    assert isinstance(window[0], HumanMessage)
    assert [m.content for m in window] == ["q2", "a2", "q3"]


def test_heuristic_route():
    assert heuristic_route("who won the match today?", False).route == "agent"
    assert heuristic_route("summarise my pdf", True).route == "rag"
    assert heuristic_route("summarise my pdf", False).route == "chat"
    assert heuristic_route("write a haiku about rain", False).route == "chat"


def test_public_error_hides_internals():
    class AuthenticationError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    assert public_error(AuthenticationError("bad key sk-123"))["code"] == "LLM_AUTH"
    assert public_error(RateLimitError("429"))["code"] == "LLM_RATE_LIMIT"
    generic = public_error(RuntimeError("psycopg password=hunter2 failed"))
    assert "hunter2" not in generic["message"]


def test_rate_limiter_window():
    rl = RateLimiter()
    assert rl.check("a", 2) is None
    assert rl.check("a", 2) is None
    assert rl.check("a", 2) is not None
    assert rl.check("b", 2) is None
