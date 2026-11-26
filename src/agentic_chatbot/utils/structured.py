"""
Structured answers that work with small models too.

``llm.with_structured_output(Schema)`` is the usual way to get JSON back, but
some small/free models handle a strict schema badly: liquid/lfm-3-1.7b loops
until it hits 8,192 tokens (33 s) and fails, while the same model answers a
plain "reply with JSON like this" prompt correctly in about 6 s. So:

1. ask for JSON in plain text, with an example of the shape, and parse it;
2. only if that fails, fall back to the provider's native structured output.

Both attempts have a time limit, so a struggling model can't hold up a turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TypeVar

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from agentic_chatbot.components.llm_loader import get_llm
from agentic_chatbot.exception.exception import LLMConfigError
from agentic_chatbot.utils.message_builder import message_text, strip_think

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json_model(schema: type[T], text: str) -> T:
    """Parse the first JSON object in ``text`` (fences and <think> blocks allowed) into ``schema``."""
    text = _FENCE.sub("", strip_think(text).strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"no JSON object in reply: {text[:120]!r}")
    return schema.model_validate(json.loads(text[start : end + 1]))


async def structured_invoke(schema: type[T], prompt: str, example: str, *, role: str = "router",
                            config: RunnableConfig | None = None, timeout: float = 40.0) -> T:
    """Ask the model for ``schema``. Raises when both attempts fail (callers have their own fallbacks)."""
    llm = get_llm(role)
    quiet: RunnableConfig = {**(config or {}), "tags": [*((config or {}).get("tags") or []), "nostream"]}
    plain = f"{prompt}\n\nReply with only a JSON object in exactly this shape, and nothing else:\n{example}"
    try:
        reply = await asyncio.wait_for(llm.ainvoke([HumanMessage(content=plain)], config=quiet), timeout)
        return parse_json_model(schema, message_text(reply.content))
    except LLMConfigError:
        raise
    except Exception as exc:
        logger.info("Plain JSON answer for %s failed (%s: %s); trying native structured output",
                    schema.__name__, type(exc).__name__, str(exc)[:160])

    result = await asyncio.wait_for(
        llm.with_structured_output(schema).ainvoke([HumanMessage(content=prompt)], config=quiet), timeout
    )
    return result if isinstance(result, schema) else schema.model_validate(result)
