from typing import Literal

from pydantic import BaseModel, Field


class Router(BaseModel):
    """Routing decision for the user's latest message."""

    route: Literal["chat", "rag", "agent"] = Field(
        description="chat = conversation/explanations; rag = the user's uploaded documents; agent = tools, web research, anything current"
    )
    reason: str = Field(description="One short sentence explaining the choice")
