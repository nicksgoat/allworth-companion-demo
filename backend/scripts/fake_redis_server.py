"""Tiny fake Redis server for local chat-memory demos.

It implements only the commands used by `conversation_memory.py`: PING, SELECT,
RPUSH, LRANGE, LTRIM, EXPIRE, and DEL. This is intentionally not a production
Redis replacement; it exists so `./demo.sh --fake-redis` can exercise the real
REDIS_URL code path without installing Redis locally.
"""

from __future__ import annotations

import asyncio
import time


class Store:
    def __init__(self) -> None:
        self.values: dict[str, list[str]] = {}
        self.expires_at: dict[str, float] = {}

    def cleanup(self, key: str) -> None:
        expires = self.expires_at.get(key)
        if expires is not None and expires <= time.time():
            self.values.pop(key, None)
            self.expires_at.pop(key, None)


STORE = Store()


async def read_command(reader: asyncio.StreamReader) -> list[str] | None:
    prefix = await reader.read(1)
    if not prefix:
        return None
    if prefix != b"*":
        raise ValueError("expected RESP array")
    count = int((await reader.readline()).rstrip(b"\r\n"))
    parts = []
    for _ in range(count):
        marker = await reader.readexactly(1)
        if marker != b"$":
            raise ValueError("expected RESP bulk string")
        length = int((await reader.readline()).rstrip(b"\r\n"))
        data = await reader.readexactly(length)
        await reader.readexactly(2)
        parts.append(data.decode())
    return parts


def simple(value: str) -> bytes:
    return f"+{value}\r\n".encode()


def integer(value: int) -> bytes:
    return f":{value}\r\n".encode()


def bulk(value: str | None) -> bytes:
    if value is None:
        return b"$-1\r\n"
    data = value.encode()
    return f"${len(data)}\r\n".encode() + data + b"\r\n"


def array(values: list[str]) -> bytes:
    return f"*{len(values)}\r\n".encode() + b"".join(bulk(value) for value in values)


def error(message: str) -> bytes:
    return f"-ERR {message}\r\n".encode()


def redis_slice(values: list[str], start: int, end: int) -> list[str]:
    length = len(values)
    if start < 0:
        start = max(length + start, 0)
    if end < 0:
        end = length + end
    if start >= length or end < 0 or start > end:
        return []
    return values[start : min(end, length - 1) + 1]


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            command = await read_command(reader)
            if command is None:
                break
            if not command:
                writer.write(error("empty command"))
                await writer.drain()
                continue

            name = command[0].upper()
            if name == "PING":
                response = simple("PONG")
            elif name == "SELECT":
                response = simple("OK")
            elif name == "RPUSH" and len(command) >= 3:
                key = command[1]
                STORE.cleanup(key)
                bucket = STORE.values.setdefault(key, [])
                bucket.extend(command[2:])
                response = integer(len(bucket))
            elif name == "LRANGE" and len(command) == 4:
                key = command[1]
                STORE.cleanup(key)
                response = array(redis_slice(STORE.values.get(key, []), int(command[2]), int(command[3])))
            elif name == "LTRIM" and len(command) == 4:
                key = command[1]
                STORE.cleanup(key)
                STORE.values[key] = redis_slice(STORE.values.get(key, []), int(command[2]), int(command[3]))
                response = simple("OK")
            elif name == "EXPIRE" and len(command) == 3:
                key = command[1]
                if key in STORE.values:
                    STORE.expires_at[key] = time.time() + int(command[2])
                    response = integer(1)
                else:
                    response = integer(0)
            elif name == "DEL" and len(command) >= 2:
                deleted = 0
                for key in command[1:]:
                    deleted += 1 if key in STORE.values else 0
                    STORE.values.pop(key, None)
                    STORE.expires_at.pop(key, None)
                response = integer(deleted)
            else:
                response = error(f"unsupported command {name}")

            writer.write(response)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def main() -> None:
    import os

    host = os.environ.get("FAKE_REDIS_HOST", "127.0.0.1")
    port = int(os.environ.get("FAKE_REDIS_PORT", "6380"))
    server = await asyncio.start_server(handle, host, port)
    print(f"Fake Redis listening on redis://{host}:{port}/0", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
