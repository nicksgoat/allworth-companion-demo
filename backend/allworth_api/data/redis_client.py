"""Minimal async Redis client for optional infrastructure features.

The backend only needs a few Redis commands for short-lived conversation memory.
Keeping this tiny client avoids coupling local tests to an optional dependency.
"""

from __future__ import annotations

import asyncio
import socket
import ssl
from typing import Any
from urllib.parse import unquote, urlparse

from allworth_api.config import redis_url


class RedisUnavailableError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(redis_url())


def reachability_status(timeout_seconds: float = 0.25) -> dict[str, Any]:
    """Return a fast, non-mutating Redis reachability check for readiness."""
    url = redis_url()
    if not url:
        return {"configured": False, "reachable": False, "error": "REDIS_URL is not configured"}
    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"}:
        return {"configured": True, "reachable": False, "error": "REDIS_URL must start with redis:// or rediss://"}
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {"configured": True, "reachable": True, "host": host, "port": port}
    except OSError as err:
        return {
            "configured": True,
            "reachable": False,
            "host": host,
            "port": port,
            "error": err.__class__.__name__,
        }


async def execute(*parts: str | int | float) -> Any:
    url = redis_url()
    if not url:
        raise RedisUnavailableError("REDIS_URL is not configured")

    parsed = urlparse(url)
    if parsed.scheme not in {"redis", "rediss"}:
        raise RedisUnavailableError("REDIS_URL must start with redis:// or rediss://")

    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    use_ssl = parsed.scheme == "rediss"
    ssl_ctx = ssl.create_default_context() if use_ssl else None
    reader, writer = await asyncio.open_connection(host, port, ssl=ssl_ctx)
    try:
        if parsed.password:
            if parsed.username:
                await _send(reader, writer, "AUTH", unquote(parsed.username), unquote(parsed.password))
            else:
                await _send(reader, writer, "AUTH", unquote(parsed.password))
        db = (parsed.path or "").strip("/")
        if db:
            await _send(reader, writer, "SELECT", db)
        return await _send(reader, writer, *parts)
    finally:
        writer.close()
        await writer.wait_closed()


async def _send(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *parts: str | int | float) -> Any:
    writer.write(_encode(parts))
    await writer.drain()
    return await _read_response(reader)


def _encode(parts: tuple[str | int | float, ...]) -> bytes:
    chunks = [f"*{len(parts)}\r\n".encode()]
    for part in parts:
        data = str(part).encode()
        chunks.append(f"${len(data)}\r\n".encode())
        chunks.append(data + b"\r\n")
    return b"".join(chunks)


async def _read_response(reader: asyncio.StreamReader) -> Any:
    prefix = await reader.readexactly(1)
    if prefix == b"+":
        return (await reader.readline()).rstrip(b"\r\n").decode("utf-8")
    if prefix == b"-":
        message = (await reader.readline()).rstrip(b"\r\n").decode("utf-8")
        raise RedisUnavailableError(message)
    if prefix == b":":
        return int((await reader.readline()).rstrip(b"\r\n"))
    if prefix == b"$":
        length = int((await reader.readline()).rstrip(b"\r\n"))
        if length == -1:
            return None
        data = await reader.readexactly(length)
        await reader.readexactly(2)
        return data.decode("utf-8")
    if prefix == b"*":
        length = int((await reader.readline()).rstrip(b"\r\n"))
        if length == -1:
            return None
        return [await _read_response(reader) for _ in range(length)]
    raise RedisUnavailableError(f"Unexpected Redis response prefix: {prefix!r}")
