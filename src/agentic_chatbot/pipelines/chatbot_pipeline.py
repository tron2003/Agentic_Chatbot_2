"""
The LangGraph pipeline and its streaming interface.

    START -> router -> chat | rag | agent -> (summarize) -> END

``stream()`` yields protocol events that the API forwards over SSE:

    {"type": "route", "route": "agent", "label": "Research", "reason": "..."}
    {"type": "step", "step": {...}}             # reasoning timeline stop (upserted by id)
    {"type": "token", "text": "..."}            # answer text, as it is generated
    {"type": "draft_reset"}                     # streamed text was agent thinking, not the answer
    {"type": "sources", "items": [...]}         # web pages or document passages used
    {"type": "answer", "content": "...", "route": "..."}  # final answer text (authoritative)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from agentic_chatbot.entity.chat_state import Chatbot
from agentic_chatbot.nodes.agent_node import agent_node
from agentic_chatbot.nodes.chat_node import chat_node
from agentic_chatbot.nodes.rag_node import rag_node
from agentic_chatbot.nodes.router_node import router_node
from agentic_chatbot.nodes.summarizer_node import should_summarize, summarize_conversation
from agentic_chatbot.utils.message_builder import ThinkFilter, message_text

logger = logging.getLogger(__name__)

ANSWER_NODES = ("chat", "rag", "agent")


def _after_answer(state: Chatbot) -> str:
    return "summarize" if should_summarize(state) else END


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    graph = StateGraph(Chatbot)
    graph.add_node("router", router_node)
    graph.add_node("chat", chat_node)
    graph.add_node("rag", rag_node)
    graph.add_node("agent", agent_node)
    graph.add_node("summarize", summarize_conversation)

    graph.add_edge(START, "router")
    graph.add_conditional_edges("router", lambda s: s.route or "chat", {n: n for n in ANSWER_NODES})
    for node in ANSWER_NODES:
        graph.add_conditional_edges(node, _after_answer, {"summarize": "summarize", END: END})
    graph.add_edge("summarize", END)
    return graph.compile(checkpointer=checkpointer)


class ChatbotPipeline:
    def __init__(self, checkpointer: BaseCheckpointSaver | None = None):
        self.checkpointer = checkpointer
        self.workflow = build_graph(checkpointer)

    @staticmethod
    def _config(thread_id: str, checkpoint_id: str | None = None) -> dict[str, Any]:
        configurable: dict[str, Any] = {"thread_id": thread_id}
        if checkpoint_id:
            configurable["checkpoint_id"] = checkpoint_id
        return {"configurable": configurable, "recursion_limit": 40}

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

    async def stream(self, thread_id: str, message: str | Sequence[BaseMessage] | None = None,
                     checkpoint_id: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """Run one turn. ``message`` is the new user text, a full message history
        (used for stateless OpenAI-compatible calls), or None to resume a checkpoint."""
        config = self._config(thread_id, checkpoint_id)
        if message is None:
            graph_input = None
        elif isinstance(message, str):
            graph_input = {"messages": [HumanMessage(content=message)]}
        else:
            graph_input = {"messages": list(message)}
        think = ThinkFilter()
        answer: str | None = None
        route: str | None = None

        async for mode, chunk in self.workflow.astream(
            graph_input, config=config, stream_mode=["messages", "custom", "updates"]
        ):
            if mode == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") not in ANSWER_NODES or not isinstance(msg, AIMessageChunk):
                    continue
                if "nostream" in (meta.get("tags") or []):
                    continue
                text = think.feed(message_text(msg.content))
                if text:
                    yield {"type": "token", "text": text}

            elif mode == "custom":
                if isinstance(chunk, dict) and chunk.get("type"):
                    if chunk["type"] == "draft_reset":
                        think = ThinkFilter()
                    elif chunk["type"] == "route":
                        route = chunk.get("route")
                    yield chunk

            elif mode == "updates":
                for node, update in (chunk or {}).items():
                    if node in ANSWER_NODES and update:
                        msgs = update.get("messages") or []
                        if msgs and isinstance(msgs[-1], AIMessage):
                            answer = message_text(msgs[-1].content)
                            tail = think.flush()
                            if tail:
                                yield {"type": "token", "text": tail}
                            yield {"type": "answer", "content": answer, "route": route or node}
