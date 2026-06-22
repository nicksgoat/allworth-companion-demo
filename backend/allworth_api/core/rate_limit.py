"""Small in-process rate limiter.

This protects early Fly deployments. Multi-instance production should move this
boundary to shared infrastructure such as Redis or an API gateway.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from allworth_api.config import (
    chat_rate_limit_per_window,
    rate_limit_enabled,
    rate_limit_per_window,
    rate_limit_window_seconds,
)
from allworth_api.core.observability import hash_household_id, household_id_from_request

_requests: dict[str, deque[float]] = defaultdict(deque)
logger = logging.getLogger("allworth_api.rate_limit")

LIMITED_PATHS = (
    "/api/chat",
    "/api/chat/feedback",
    "/api/auth/login",
    "/api/auth/login/email",
    "/tools/simulate",
    "/tools/rebalance",
)


def _client_key(request: Request) -> str:
    household = request.headers.get("X-Household-Id", "")
    auth = request.headers.get("Authorization", "")
    ip = request.client.host if request.client else "unknown"
    identity = household or auth[:32] or ip
    return f"{request.url.path}:{identity}"


def _limit_for(path: str) -> int:
    return chat_rate_limit_per_window() if path == "/api/chat" else rate_limit_per_window()


async def rate_limit_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if not rate_limit_enabled() or request.url.path not in LIMITED_PATHS:
        return await call_next(request)

    now = time.monotonic()
    window = rate_limit_window_seconds()
    limit = _limit_for(request.url.path)
    key = _client_key(request)
    bucket = _requests[key]
    while bucket and bucket[0] <= now - window:
        bucket.popleft()

    remaining = max(limit - len(bucket), 0)
    if remaining <= 0:
        retry_after = max(1, int(window - (now - bucket[0]))) if bucket else window
        logger.info(
            json.dumps(
                {
                    "event": "rate_limit",
                    "path": request.url.path,
                    "method": request.method,
                    "limit": limit,
                    "window_seconds": window,
                    "retry_after": retry_after,
                    "household_hash": hash_household_id(household_id_from_request(request)),
                },
                separators=(",", ":"),
            )
        )
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded. Please try again shortly."},
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time() + retry_after)),
            },
        )

    bucket.append(now)
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(max(limit - len(bucket), 0))
    response.headers["X-RateLimit-Reset"] = str(int(time.time() + window))
    return response


def reset_rate_limits() -> None:
    _requests.clear()
