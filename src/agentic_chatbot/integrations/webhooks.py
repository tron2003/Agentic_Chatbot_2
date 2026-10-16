"""
Outgoing webhooks.

``emit_event("document.ingested", {...})`` fans the event out to every enabled
webhook subscribed to it, in the background (a slow receiver never delays a
chat answer). Each delivery is retried up to 3 times with backoff.

Formats
-------
json            ``{"id", "event", "created_at", "data"}`` with headers
                ``X-Junction-Event``, ``X-Junction-Delivery`` and, when a secret
                is set, ``X-Junction-Signature: sha256=<hmac of the raw body>``.
openclaw_agent  OpenClaw's ``POST /hooks/agent`` body (``message``, ``name``,
                ``deliver``, optional ``channel``/``to``/``agentId``) with a
                bearer token, so your OpenClaw assistant can tell you about it.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from agentic_chatbot.integrations import agent_bridge
from agentic_chatbot.integrations.config import WebhookConfig, get_integrations

logger = logging.getLogger(__name__)

ROUTE_LABEL = {"chat": "Chat", "rag": "Documents", "agent": "Research"}


def render_message(event: str, data: dict[str, Any]) -> str:
    if event == "answer.completed":
        title = data.get("title") or "a question"
        route = ROUTE_LABEL.get(data.get("route") or "", "")
        content = (data.get("content") or "").strip()
        if len(content) > 1500:
            content = content[:1500] + "…"
        return f'Junction finished answering "{title}"{f" ({route})" if route else ""}.\n\n{content}'
    if event == "document.ingested":
        return f"Junction added {data.get('name')} to the document library ({data.get('chunks')} passages)."
    if event == "document.deleted":
        return f"Junction removed {data.get('name')} from the document library."
    if event == "conversation.created":
        return f'New Junction conversation: "{data.get("title")}".'
    return f"Junction event {event}."


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def build_request(hook: WebhookConfig, event: str, data: dict[str, Any], delivery_id: str) -> tuple[bytes, dict[str, str]]:
    headers = {"Content-Type": "application/json", "User-Agent": "Junction-Webhooks/1", **hook.headers}
    if hook.format == "openclaw_agent":
        payload: dict[str, Any] = {"message": render_message(event, data), "name": "Junction", "deliver": hook.deliver}
        if hook.channel and hook.to:
            payload.update(channel=hook.channel, to=hook.to)
        if hook.agent_id:
            payload["agentId"] = hook.agent_id
        if hook.token:
            headers["Authorization"] = f"Bearer {hook.token}"
        headers["Idempotency-Key"] = delivery_id
    else:
        payload = {"id": delivery_id, "event": event, "created_at": datetime.now(UTC).isoformat(), "data": data}
        headers["X-Junction-Event"] = event
        headers["X-Junction-Delivery"] = delivery_id
        if hook.token:
            headers["Authorization"] = f"Bearer {hook.token}"
    body = json.dumps(payload, ensure_ascii=False, default=str).encode()
    if hook.secret and hook.format == "json":
        headers["X-Junction-Signature"] = sign(hook.secret, body)
    return body, headers


class WebhookDispatcher:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self.last_status: dict[str, str] = {}

    def emit(self, event: str, data: dict[str, Any]) -> None:
        hooks = [h for h in get_integrations().enabled_webhooks if h.wants(event)]
        if not hooks:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        for hook in hooks:
            task = loop.create_task(self._deliver(hook, event, data))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _deliver(self, hook: WebhookConfig, event: str, data: dict[str, Any], attempts: int = 3) -> None:
        delivery_id = f"evt_{uuid.uuid4().hex[:20]}"
        body, headers = build_request(hook, event, data, delivery_id)
        for attempt in range(1, attempts + 1):
            try:
                async with agent_bridge.client_factory(hook.timeout_seconds) as client:
                    res = await client.post(hook.url, content=body, headers=headers)  # type: ignore[arg-type]
                if res.status_code < 400:
                    self.last_status[hook.name] = "ok"
                    return
                status = f"HTTP {res.status_code}"
                if 400 <= res.status_code < 500 and res.status_code not in (408, 429):
                    attempt = attempts  # client errors won't fix themselves
            except Exception as exc:  # network errors, timeouts
                status = type(exc).__name__
            if attempt >= attempts:
                self.last_status[hook.name] = f"failed: {status}"
                logger.warning("Webhook %s failed for %s: %s", hook.name, event, status)
                return
            await asyncio.sleep(0.5 * 2 ** (attempt - 1))

    async def drain(self) -> None:
        """Wait for in-flight deliveries (used on shutdown and in tests)."""
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)


dispatcher = WebhookDispatcher()


def emit_event(event: str, data: dict[str, Any]) -> None:
    dispatcher.emit(event, data)
