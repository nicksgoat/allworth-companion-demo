from __future__ import annotations

import json

import pytest

from allworth_api.core import conversation_memory


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_redis_conversation_memory_round_trips_recent_messages(monkeypatch) -> None:
    store: dict[str, list[str]] = {}

    async def fake_execute(command, key, *args):
        command = command.upper()
        if command == "RPUSH":
            store.setdefault(key, []).append(args[0])
            return len(store[key])
        if command == "LTRIM":
            start, end = int(args[0]), int(args[1])
            values = store.get(key, [])
            store[key] = values[start : end + 1 if end != -1 else None]
            return "OK"
        if command == "EXPIRE":
            return 1
        if command == "LRANGE":
            start, end = int(args[0]), int(args[1])
            values = store.get(key, [])
            return values[start : end + 1 if end != -1 else None]
        raise AssertionError(f"unexpected command {command}")

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("CHAT_MEMORY_ENABLED", "true")
    monkeypatch.setenv("CHAT_MEMORY_MAX_MESSAGES", "3")
    monkeypatch.setattr(conversation_memory.redis_client, "is_configured", lambda: True)
    monkeypatch.setattr(conversation_memory.redis_client, "execute", fake_execute)

    await conversation_memory.append_turn("maya", "maya:wednesday", "first", "reply one")
    await conversation_memory.append_turn("maya", "maya:wednesday", "second", "reply two")

    messages = await conversation_memory.recent_messages("maya", "maya:wednesday")

    assert messages == [
        {"role": "assistant", "content": "reply one"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply two"},
    ]
    assert all(
        json.loads(raw)["role"] in {"user", "assistant"}
        for values in store.values()
        for raw in values
    )


@pytest.mark.anyio
async def test_conversation_memory_is_noop_without_redis(monkeypatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CHAT_MEMORY_ENABLED", raising=False)

    assert await conversation_memory.recent_messages("maya", "maya:wednesday") == []
    await conversation_memory.append_turn("maya", "maya:wednesday", "hello", "hi")
