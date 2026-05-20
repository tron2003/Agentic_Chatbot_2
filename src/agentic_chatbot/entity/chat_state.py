from pydantic import BaseModel
from typing import Annotated
from langgraph.graph.message import add_messages
from pydantic import Field

class Chatbot(BaseModel):

    messages: Annotated[
        list,
        add_messages
    ]
    summary: str|None=Field(default="")