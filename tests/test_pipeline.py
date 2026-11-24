import asyncio

from langgraph.checkpoint.memory import InMemorySaver

from agentic_chatbot.nodes import summarizer_node
from agentic_chatbot.pipelines.chatbot_pipeline import ChatbotPipeline


async def _drain(pipeline, thread, message):
    return [e async for e in pipeline.stream(thread, message)]


def test_summarizer_folds_old_messages_into_summary(monkeypatch):
    monkeypatch.setattr(summarizer_node, "_limits", lambda: (4, 2))
    pipeline = ChatbotPipeline(InMemorySaver())

    async def run():
        for q in ["hi, I'm Kanish", "I build LangGraph agents", "what's a checkpointer?"]:
            await _drain(pipeline, "t", q)
        return await pipeline.workflow.aget_state({"configurable": {"thread_id": "t"}})

    state = asyncio.run(run())
    msgs = state.values["messages"]
    assert state.values["summary"], "summary should be written once the threshold is passed"
    assert len(msgs) <= 4
    assert msgs[0].type == "human", "kept window must start with a user message"


def test_answer_event_matches_final_state():
    pipeline = ChatbotPipeline(InMemorySaver())
    events = asyncio.run(_drain(pipeline, "t2", "hello"))
    answer = next(e for e in events if e["type"] == "answer")
    tokens = "".join(e["text"] for e in events if e["type"] == "token")
    assert answer["content"].strip() == tokens.strip()
    assert answer["route"] == "chat"
