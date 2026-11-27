"""
Which tools run on their own and which wait for the user's approval.

Every tool is a **read** tool (looks something up) or an **act** tool (changes
something: sends, creates, deletes, writes, or hands a task to another agent).

1. Built-in tools are read tools; ``ask_<agent>`` delegation tools are act tools.
2. MCP tools use the server's own hints when it sends them: ``readOnlyHint: true``
   means read, ``readOnlyHint: false`` or ``destructiveHint: true`` means act.
3. Otherwise the tool's name decides (get/list/search/read → read; create/send/
   delete/update/write/push… → act). A name that says neither is treated as act.

The Connections panel can override any tool: ``auto`` (run without asking),
``ask`` (wait for approval) or ``off`` (the agent never sees it). The global
switch ``approvals.mode`` in config.yaml (``TOOL_APPROVALS``) turns approvals off.
"""

from __future__ import annotations

import os
import re
from typing import Any, Literal

from langchain_core.tools import BaseTool

from agentic_chatbot.core.settings import config_section
from agentic_chatbot.services import connections

Kind = Literal["read", "act"]
Decision = Literal["run", "ask", "off"]

BUILTIN_READ = {
    "web_search", "calculator", "current_datetime", "search_knowledge_base", "read_pdf",
    "describe_spreadsheets", "query_spreadsheet",
}

_READ_WORDS = {
    "get", "list", "search", "read", "query", "fetch", "find", "describe", "show", "lookup", "view", "count",
    "check", "browse", "tree", "stat", "info", "inspect", "preview", "download", "explain", "summarize", "compare",
}
_ACT_WORDS = {
    "create", "send", "delete", "remove", "update", "write", "edit", "move", "push", "merge", "post", "put", "patch",
    "set", "add", "upload", "insert", "drop", "close", "reopen", "fork", "publish", "comment", "reply", "invite",
    "assign", "rename", "copy", "execute", "run", "deploy", "approve", "transfer", "pay", "submit", "archive",
    "unarchive", "star", "unstar", "follow", "unfollow", "book", "cancel", "schedule", "trigger", "restart", "kill",
    "install", "uninstall", "commit", "revert", "reset", "clear", "purge", "share", "mark", "label", "tag", "apply",
}


def server_of(tool: BaseTool) -> str:
    """'builtin', 'agents', or the MCP server the tool came from."""
    meta = tool.metadata or {}
    if meta.get("mcp_server"):
        return str(meta["mcp_server"])
    return "agents" if tool.name.startswith("ask_") else "builtin"


def tool_key(tool: BaseTool) -> str:
    return f"{server_of(tool)}/{tool.name}"


def _words(name: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w]


# Act verbs that override a leading read verb ("get_or_create_issue" acts; "get_label" only reads).
_STRONG_ACT = {
    "create", "delete", "remove", "update", "write", "send", "set", "post", "put", "patch", "merge", "push",
    "execute", "run", "edit", "move", "upload", "insert", "drop", "submit", "pay", "transfer", "deploy", "publish",
}


def kind_from_name(name: str) -> Kind:
    words = _words(name)
    if not words:
        return "act"
    if words[0] in _READ_WORDS and not set(words[1:]) & _STRONG_ACT:
        return "read"
    if set(words) & _ACT_WORDS:
        return "act"
    if set(words) & _READ_WORDS:
        return "read"
    return "act"


def tool_kind(tool: BaseTool) -> Kind:
    if tool.name in BUILTIN_READ and server_of(tool) == "builtin":
        return "read"
    if server_of(tool) == "agents":
        return "act"
    meta = tool.metadata or {}
    if meta.get("readOnlyHint") is True:
        return "read"
    if meta.get("readOnlyHint") is False or meta.get("destructiveHint") is True:
        return "act"
    return kind_from_name(tool.name)


def approvals_on() -> bool:
    mode = (os.environ.get("TOOL_APPROVALS") or str(config_section("approvals").get("mode") or "ask")).strip().lower()
    return mode not in ("off", "false", "0", "never")


def decide(tool: BaseTool | None, settings: dict[str, str] | None = None) -> Decision:
    """run | ask | off for one tool. An unknown tool runs (it fails with a clear error instead)."""
    if tool is None:
        return "run"
    settings = connections.tool_settings() if settings is None else settings
    setting = settings.get(tool_key(tool))
    if setting == "off":
        return "off"
    if not approvals_on() or setting == "auto":
        return "run"
    if setting == "ask":
        return "ask"
    return "ask" if tool_kind(tool) == "act" else "run"


def visible(tools: list[BaseTool]) -> list[BaseTool]:
    """Tools the agent may see: everything not switched off."""
    settings = connections.tool_settings()
    return [t for t in tools if decide(t, settings) != "off"]


def describe_tool(tool: BaseTool, settings: dict[str, str] | None = None) -> dict[str, Any]:
    settings = connections.tool_settings() if settings is None else settings
    meta = tool.metadata or {}
    return {
        "name": tool.name,
        "key": tool_key(tool),
        "description": (tool.description or "").strip()[:400],
        "kind": tool_kind(tool),
        "setting": settings.get(tool_key(tool)),  # None = default for its kind
        "decision": decide(tool, settings),
        "title": meta.get("title"),
    }
