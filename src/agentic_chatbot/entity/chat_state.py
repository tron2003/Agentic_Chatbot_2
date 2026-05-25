from typing import Annotated

from pydantic import (
    BaseModel,
    Field
)

from langgraph.graph.message import (
    add_messages
)


class Chatbot(
    BaseModel
):

    messages: Annotated[
        list,
        add_messages
    ]

    summary: str | None = None

    route: str | None = None