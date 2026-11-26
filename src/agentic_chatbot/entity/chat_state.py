from typing import Annotated, Any, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel

Route = Literal["chat", "rag", "agent"]
Mode = Literal["auto", "deep_research"]


def merge_notes(old: list | None, new: Any) -> list:
    """Reducer for research notes. Parallel workers each append their notes;
    ``None`` (sent by the planner at the start of a turn) clears the list."""
    if new is None:
        return []
    return [*(old or []), *(new if isinstance(new, list) else [new])]


class Chatbot(BaseModel):
    """Graph state persisted by the checkpointer for each conversation thread.

    Short-term memory is this state: ``messages`` (the recent conversation, kept
    per thread by the checkpointer) plus ``summary`` (older messages folded into
    a running summary by the summarise block). Long-term memory lives in the
    LangGraph store, across threads; ``user_memories`` is what the recall block
    loaded from it for this turn.
    """

    messages: Annotated[list, add_messages]
    summary: str | None = None
    route: Route | None = None

    # Set per turn by the client: "deep_research" forces the Deep research route and a full report.
    mode: Mode = "auto"

    # Long-term memory recalled for this turn (formatted text for prompts).
    user_memories: str | None = None

    # Deep research working state (reset at the start of each research turn).
    research_depth: Literal["quick", "deep"] | None = None
    research_round: int = 0
    research_questions: list[dict] = []
    research_notes: Annotated[list, merge_notes] = []
