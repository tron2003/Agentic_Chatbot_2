from typing import Literal

from pydantic import (
    BaseModel
)


class Router(
    BaseModel
):

    route: Literal[
        "chat",
        "rag",
        "memory",
        "tool"
    ]

    reason: str