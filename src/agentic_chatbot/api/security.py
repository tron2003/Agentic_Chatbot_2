"""Optional API-key auth and a per-client rate limiter.

Auth: set ``API_KEYS=key1,key2`` to require ``Authorization: Bearer <key>``
(or ``X-API-Key``) on every /api route. Leave empty to disable.

Rate limit: a sliding one-minute window per API key (or client IP), applied
to endpoints that call the model or index files. It is in-process, so with
several workers each worker enforces its own window; put a shared limiter
(e.g. at the reverse proxy) in front for strict global limits.
"""

from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from agentic_chatbot.core.settings import get_settings


def _presented_key(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


def client_identity(request: Request) -> str:
    key = _presented_key(request)
    if key:
        return f"key:{key[-8:]}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


async def require_api_key(request: Request) -> None:
    keys = get_settings().api_key_set
    if not keys:
        return
    presented = _presented_key(request) or ""
    if not any(hmac.compare_digest(presented, k) for k in keys):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key.",
            headers={"WWW-Authenticate": "Bearer"},
        )


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, identity: str, limit: int, window: float = 60.0) -> float | None:
        """Return seconds to wait if over the limit, else None (and record the hit)."""
        if limit <= 0:
            return None
        now = time.monotonic()
        hits = self._hits[identity]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return window - (now - hits[0])
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory under abuse
            for k in [k for k, v in self._hits.items() if not v][:5000]:
                del self._hits[k]
        return None

    def reset(self) -> None:
        self._hits.clear()


limiter = RateLimiter()


async def rate_limit(request: Request) -> None:
    wait = limiter.check(client_identity(request), get_settings().rate_limit_per_minute)
    if wait is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many requests. Try again in {int(wait) + 1} seconds.",
            headers={"Retry-After": str(int(wait) + 1)},
        )
