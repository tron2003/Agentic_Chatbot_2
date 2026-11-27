"""
Which project a chat turn belongs to, so every part of the answer stays inside it.

A turn sets the scope once (``use_scope``); the router, document search, the
agent's knowledge-base tool, spreadsheet SQL and the prompts read it with
``current_scope()``. It is a context variable, so LangGraph's node tasks and the
worker threads they start inherit it without passing it through every call.

* No scope set (scripts, the MCP ``search_documents`` tool): every document.
* A chat outside any project: documents that aren't in a project.
* A project chat: that project's documents, plus its instructions in every prompt.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scope:
    project_id: str | None = None
    name: str | None = None
    instructions: str = ""
    doc_ids: frozenset[str] = field(default_factory=frozenset)

    def allows(self, doc_id: str | None) -> bool:
        return doc_id in self.doc_ids


_scope: ContextVar[Scope | None] = ContextVar("project_scope", default=None)


def current_scope() -> Scope | None:
    return _scope.get()


@contextmanager
def use_scope(scope: Scope | None) -> Iterator[None]:
    token = _scope.set(scope)
    try:
        yield
    finally:
        _scope.reset(token)


def set_scope(scope: Scope | None) -> None:
    """Set for the rest of the current task (used inside async generators, where a with-block can't span yields)."""
    _scope.set(scope)


async def build_scope(project_id: str | None) -> Scope:
    """The scope for a conversation: its project (or none) and the documents it may read."""
    from agentic_chatbot.services.store import get_store

    store = get_store()
    docs = await store.list_documents()
    allowed = frozenset(d["id"] for d in docs if (d.get("project_id") or None) == (project_id or None))
    if not project_id:
        return Scope(doc_ids=allowed)
    project = await store.get_project(project_id)
    if not project:
        return Scope(doc_ids=frozenset(d["id"] for d in docs if not d.get("project_id")))
    return Scope(project_id=project_id, name=project["name"], instructions=project.get("instructions") or "",
                 doc_ids=allowed)
