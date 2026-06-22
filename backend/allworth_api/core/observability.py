"""Request logging helpers for production operations."""

from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from allworth_api.core.auth import get_session

logger = logging.getLogger("allworth_api.request")


def hash_household_id(household_id: str | None) -> str | None:
    if not household_id:
        return None
    return hashlib.sha256(household_id.encode("utf-8")).hexdigest()[:16]


def household_id_from_request(request: Request) -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        session = get_session(auth_header[7:])
        if session:
            return session.household_id
    return request.headers.get("X-Household-Id") or None


async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
    request.state.request_id = request_id
    t0 = time.perf_counter()
    status_code = 500
    error_class = None
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-Id"] = request_id
        return response
    except Exception as err:
        error_class = err.__class__.__name__
        raise
    finally:
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        household = household_id_from_request(request)
        logger.info(
            json.dumps(
                {
                    "event": "request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status_code,
                    "latency_ms": elapsed_ms,
                    "household_hash": hash_household_id(household),
                    "error_class": error_class,
                },
                separators=(",", ":"),
            )
        )
