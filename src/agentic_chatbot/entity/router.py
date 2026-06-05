from typing import Literal

from pydantic import BaseModel


class Router(BaseModel):

    route: Literal["chat", "rag", "tool"]

    reason: str
