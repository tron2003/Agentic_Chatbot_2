"""Pure-ASGI middleware (safe with streaming responses).

* Assigns each request an ID (or reuses a valid incoming ``X-Request-ID``),
  exposes it in the response header and in every log line.
* Logs one access line per request with status and duration.
* Adds conservative security headers.
"""

from __future__ import annotations

import logging
import re
import time

from agentic_chatbot.core.context import new_request_id, request_id_var

logger = logging.getLogger("agentic_chatbot.access")

_VALID_ID = re.compile(r"^[A-Za-z0-9\-_.]{6,64}$")

SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _VALID_ID.match(incoming) else new_request_id()
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status_holder = {"code": 500}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                headers = list(message.get("headers") or [])
                headers.append((b"x-request-id", rid.encode()))
                existing = {k.lower() for k, _ in headers}
                headers.extend(h for h in SECURITY_HEADERS if h[0] not in existing)
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            path = scope.get("path", "")
            if not path.startswith("/assets") and path not in ("/health",):
                logger.info(
                    "%s %s %s",
                    scope.get("method"),
                    path,
                    status_holder["code"],
                    extra={"status": status_holder["code"], "elapsed_ms": round((time.perf_counter() - start) * 1000, 1)},
                )
            request_id_var.reset(token)
