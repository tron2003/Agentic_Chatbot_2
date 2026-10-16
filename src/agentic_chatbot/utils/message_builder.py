"""Helpers for turning graph state into model input."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def message_text(content: Any) -> str:
    """Plain text from message content (str, or a list of provider content blocks).

    Anthropic streams content as blocks like ``{"type": "text", "text": "..."}``
    alongside ``tool_use`` / ``input_json_delta`` blocks; only text is kept.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") in ("text", "text_delta") and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.S)


def strip_think(text: str) -> str:
    """Remove <think>…</think> reasoning blocks some local models emit."""
    text = _THINK_RE.sub("", text)
    if "<think>" in text:  # unterminated block
        text = text.split("<think>")[0]
    return text.strip()


class ThinkFilter:
    """Streaming filter that hides <think>…</think> spans split across chunks."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self.inside = False
        self.buffer = ""

    def feed(self, text: str) -> str:
        self.buffer += text
        out: list[str] = []
        while self.buffer:
            if self.inside:
                idx = self.buffer.find(self.CLOSE)
                if idx == -1:
                    # keep a tail that may hold a partial closing tag
                    self.buffer = self.buffer[-(len(self.CLOSE) - 1):]
                    break
                self.buffer = self.buffer[idx + len(self.CLOSE):].lstrip()
                self.inside = False
            else:
                idx = self.buffer.find(self.OPEN)
                if idx == -1:
                    # hold back a possible partial "<think" at the end
                    safe = len(self.buffer)
                    for k in range(1, len(self.OPEN)):
                        if self.buffer.endswith(self.OPEN[:k]):
                            safe = len(self.buffer) - k
                            break
                    out.append(self.buffer[:safe])
                    self.buffer = self.buffer[safe:]
                    break
                out.append(self.buffer[:idx])
                self.buffer = self.buffer[idx + len(self.OPEN):]
                self.inside = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self.inside else self.buffer
        self.buffer = ""
        return rest


def conversational(messages: Sequence[BaseMessage], limit: int) -> list[BaseMessage]:
    """The last ``limit`` user/assistant turns, starting with a user message.

    Several providers (Anthropic in particular) reject a conversation that
    starts with an assistant message, which naive ``messages[-n:]`` slicing
    produces half the time. Tool-call messages are dropped: the graph only
    stores final answers, but older checkpoints may contain them.
    """
    clean = [
        m for m in messages
        if isinstance(m, HumanMessage) or (isinstance(m, AIMessage) and not m.tool_calls)
    ]
    window = clean[-limit:] if limit > 0 else clean
    while window and not isinstance(window[0], HumanMessage):
        window = window[1:]
    return window


def latest_user_text(messages: Sequence[BaseMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return message_text(m.content)
    return ""


def transcript(messages: Sequence[BaseMessage], max_chars_per_message: int = 1500) -> str:
    lines = []
    for m in messages:
        if isinstance(m, ToolMessage):
            continue
        role = "User" if isinstance(m, HumanMessage) else "Assistant"
        text = message_text(m.content).strip()
        if len(text) > max_chars_per_message:
            text = text[:max_chars_per_message] + " …"
        if text:
            lines.append(f"{role}: {text}")
    return "\n".join(lines)


def build_messages(state: Any, limit: int = 10) -> list[BaseMessage]:
    """Backwards-compatible helper: recent conversational messages."""
    return conversational(state.messages, limit)
