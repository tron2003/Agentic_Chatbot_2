"""
The LangGraph pipeline and its streaming interface.

    START -> recall -> router -> chat
                              -> rag
                              -> research_plan -> agent <-> approval         (quick look-up; pauses before act tools)
                                               -> research_worker x N        (deep, in parallel)
                                                  -> research_review -> (more workers) -> research_write
          answer -> remember (long-term memory) + summarize (short-term memory, when the thread is long) -> END

``stream()`` yields protocol events that the API forwards over SSE:

    {"type": "route", "route": "agent", "label": "Deep research", "reason": "..."}
    {"type": "step", "step": {...}}             # reasoning timeline stop (upserted by id)
    {"type": "token", "text": "..."}            # answer text, as it is generated
    {"type": "draft_reset"}                     # streamed text was agent thinking, not the answer
    {"type": "sources", "items": [...]}         # web pages or document passages used
    {"type": "answer", "content": "...", "route": "..."}  # final answer text (authoritative)
    {"type": "approval_required", "actions": [...]}      # paused: the agent wants to run act tools

A paused run is continued with ``stream(thread_id, resume={call_id: "approve" | "decline"})``.
Only runs started with ``interactive=True`` (the web UI) pause; elsewhere act tools are declined.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Command

from agentic_chatbot.core.scope import Scope, set_scope
from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.nodes.agent_node import CLEARED, after_agent, agent_node, approval_node
from agentic_chatbot.nodes.chat_node import chat_node
from agentic_chatbot.nodes.memory_nodes import WORTH_REMEMBERING, recall, remember
from agentic_chatbot.nodes.rag_node import rag_node
from agentic_chatbot.nodes.research_nodes import (
    ResearchTask,
    research_plan,
    research_review,
    research_worker,
    research_write,
    route_after_plan,
    route_after_review,
)
from agentic_chatbot.nodes.router_node import router_node
from agentic_chatbot.nodes.summarizer_node import should_summarize, summarize_conversation
from agentic_chatbot.services.long_term_memory import default_user_id, long_term_enabled
from agentic_chatbot.utils.message_builder import ThinkFilter, latest_user_text, message_text

logger = logging.getLogger(__name__)

# Nodes whose model output is the answer (their tokens stream to the client).
ANSWER_NODES = ("chat", "rag", "agent", "research_write")
ROUTE_TARGETS = {"chat": "chat", "rag": "rag", "agent": "research_plan"}


def _after_answer(state: Chatbot) -> list[str] | str:
    """Memory upkeep after every answer: both blocks run in parallel, after the reply was sent."""
    nxt: list[str] = []
    if long_term_enabled() and WORTH_REMEMBERING.search(latest_user_text(state.messages)):
        nxt.append("remember")
    if should_summarize(state):
        nxt.append("summarize")
    return nxt or END


def _after_agent_node(state: Chatbot) -> list[str] | str:
    return "approval" if after_agent(state) else _after_answer(state)


def build_graph(checkpointer: BaseCheckpointSaver | None = None, store: BaseStore | None = None):
    graph = StateGraph(Chatbot)
    graph.add_node("recall", recall)
    graph.add_node("router", router_node)
    graph.add_node("chat", chat_node)
    graph.add_node("rag", rag_node)
    graph.add_node("research_plan", research_plan)
    graph.add_node("agent", agent_node)
    graph.add_node("approval", approval_node)
    graph.add_node("research_worker", research_worker, input_schema=ResearchTask)
    graph.add_node("research_review", research_review)
    graph.add_node("research_write", research_write)
    graph.add_node("remember", remember)
    graph.add_node("summarize", summarize_conversation)

    graph.add_edge(START, "recall")
    graph.add_edge("recall", "router")
    graph.add_conditional_edges("router", lambda s: ROUTE_TARGETS[s.route or "chat"],
                                ["chat", "rag", "research_plan"])
    graph.add_conditional_edges("research_plan", route_after_plan, ["agent", "research_worker", "research_write"])
    graph.add_edge("research_worker", "research_review")
    graph.add_conditional_edges("research_review", route_after_review, ["research_worker", "research_write"])
    graph.add_conditional_edges("agent", _after_agent_node, ["approval", "remember", "summarize", END])
    graph.add_edge("approval", "agent")
    for node in ANSWER_NODES:
        if node != "agent":
            graph.add_conditional_edges(node, _after_answer, ["remember", "summarize", END])
    graph.add_edge("remember", END)
    graph.add_edge("summarize", END)
    return graph.compile(checkpointer=checkpointer, store=store)


class ChatbotPipeline:
    def __init__(self, checkpointer: BaseCheckpointSaver | None = None, store: BaseStore | None = None):
        self.checkpointer = checkpointer
        self.store = store
        self.workflow = build_graph(checkpointer, store)

    @staticmethod
    def _config(thread_id: str, checkpoint_id: str | None = None, user_id: str | None = None,
                interactive: bool = False) -> dict[str, Any]:
        configurable: dict[str, Any] = {"thread_id": thread_id, "user_id": user_id or default_user_id(),
                                        "interactive": interactive}
        if checkpoint_id:
            configurable["checkpoint_id"] = checkpoint_id
        return {"configurable": configurable, "recursion_limit": 60}

    async def run(self, message: HumanMessage | str, thread_id: str = "default") -> dict:
        """Non-streaming helper (kept for scripts and backwards compatibility)."""
        if isinstance(message, str):
            message = HumanMessage(content=message)
        return await self.workflow.ainvoke({"messages": [message]}, config=self._config(thread_id))

    async def regenerate_checkpoint(self, thread_id: str) -> str | None:
        """ID of the checkpoint where the latest user message entered the thread.

        Resuming from it re-runs the graph for that same message on a new
        branch, which is how "regenerate response" works without duplicating
        the question in memory.
        """
        async for snapshot in self.workflow.aget_state_history(self._config(thread_id)):
            if (snapshot.metadata or {}).get("source") == "input":
                return snapshot.config["configurable"]["checkpoint_id"]
        return None

    async def pending_approval(self, thread_id: str) -> list[dict] | None:
        """The actions a paused run is waiting on, or None when nothing is waiting."""
        snapshot = await self.workflow.aget_state(self._config(thread_id))
        for intr in snapshot.interrupts or ():
            value = intr.value if isinstance(intr.value, dict) else {}
            if value.get("type") == "approval":
                return list(value.get("actions") or [])
        return None

    async def stream(self, thread_id: str, message: str | Sequence[BaseMessage] | None = None,
                     checkpoint_id: str | None = None, *, mode: str = "auto",
                     user_id: str | None = None, interactive: bool = False,
                     resume: Any = None, scope: Scope | None = None) -> AsyncIterator[dict[str, Any]]:
        """Run one turn. ``message`` is the new user text, a full message history
        (used for stateless OpenAI-compatible calls), or None to resume a checkpoint.
        ``mode="deep_research"`` forces the Deep research route and a full report.
        ``interactive=True`` lets the agent pause for approval; ``resume`` continues a paused run.
        ``scope`` limits documents, spreadsheets and instructions to the conversation's project."""
        if scope is not None:
            set_scope(scope)  # the project this turn belongs to; every node and tool reads it (core/scope.py)
        config = self._config(thread_id, checkpoint_id, user_id, interactive)
        mode = mode if mode in ("auto", "deep_research") else "auto"
        if resume is not None:
            graph_input: Any = Command(resume=resume)
        elif message is None:
            graph_input = None
        elif isinstance(message, str):
            # A new message also drops any approval still waiting from the previous turn.
            graph_input = {"messages": [HumanMessage(content=message)], "mode": mode, **CLEARED}
        else:
            graph_input = {"messages": list(message), "mode": mode, **CLEARED}
        think = ThinkFilter()
        answer: str | None = None
        route: str | None = None

        async for kind, chunk in self.workflow.astream(
            graph_input, config=config, stream_mode=["messages", "custom", "updates"]
        ):
            if kind == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") not in ANSWER_NODES or not isinstance(msg, AIMessageChunk):
                    continue
                if "nostream" in (meta.get("tags") or []):
                    continue
                text = think.feed(message_text(msg.content))
                if text:
                    yield {"type": "token", "text": text}

            elif kind == "custom":
                if isinstance(chunk, dict) and chunk.get("type"):
                    if chunk["type"] == "draft_reset":
                        think = ThinkFilter()
                    elif chunk["type"] == "route":
                        route = chunk.get("route")
                    yield chunk

            elif kind == "updates":
                for node, update in (chunk or {}).items():
                    if node == "__interrupt__":
                        for intr in update or ():
                            value = getattr(intr, "value", None)
                            if isinstance(value, dict) and value.get("type") == "approval":
                                yield {"type": "approval_required", "actions": value.get("actions") or []}
                        continue
                    if node in ANSWER_NODES and isinstance(update, dict):
                        msgs = update.get("messages") or []
                        if msgs and isinstance(msgs[-1], AIMessage):
                            answer = message_text(msgs[-1].content)
                            tail = think.flush()
                            if tail:
                                yield {"type": "token", "text": tail}
                            yield {"type": "answer", "content": answer, "route": route or node}
