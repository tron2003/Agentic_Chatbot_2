"""Custom stream events emitted by graph nodes.

Nodes call ``emit(...)``; the pipeline forwards these to the client over SSE
alongside model tokens. Outside a streaming run the writer is a no-op.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


def emit(event: dict[str, Any]) -> None:
    try:
        from langgraph.config import get_stream_writer

        get_stream_writer()(event)
    except Exception:  # not inside a streaming graph run
        pass


def step(kind: str, title: str, detail: str = "", *, step_id: str | None = None,
         status: str = "done", tool: str | None = None, **extra: Any) -> dict[str, Any]:
    event = {
        "type": "step",
        "step": {
            "id": step_id or uuid.uuid4().hex[:10],
            "kind": kind,  # route | retrieval | thinking | tool
            "title": title,
            "detail": detail,
            "status": status,  # running | done | error
            "tool": tool,
            "ts": datetime.now(UTC).isoformat(),
            **extra,
        },
    }
    emit(event)
    return event["step"]
