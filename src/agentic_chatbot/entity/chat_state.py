from typing import Annotated, Literal

from langgraph.graph.message import add_messages
from pydantic import BaseModel

Route = Literal["chat", "rag", "agent"]


class Chatbot(BaseModel):
    """Graph state persisted by the checkpointer for each conversation thread."""

    messages: Annotated[list, add_messages]
    summary: str | None = None
    route: Route | None = None
