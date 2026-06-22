"""Short-term Redis-backed conversation memory for stateless chat."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from allworth_api.config import (
    chat_memory_enabled,
    chat_memory_max_messages,
    chat_memory_ttl_seconds,
)
from allworth_api.core.formatting import iso_now
from allworth_api.data import redis_client

logger = logging.getLogger("allworth_api.memory")


def default_conversation_id(client_id: str, session: str) -> str:
    return f"{client_id}:{session}"


def _key(client_id: str, conversation_id: str) -> str:
    digest = hashlib.sha256(f"{client_id}:{conversation_id}".encode()).hexdigest()
    return f"allworth:chat:{digest}"


async def recent_messages(client_id: str, conversation_id: str) -> list[dict[str, str]]:
    if not chat_memory_enabled() or not redis_client.is_configured():
        return []
    try:
        raw_items = await redis_client.execute(
            "LRANGE",
            _key(client_id, conversation_id),
            -chat_memory_max_messages(),
            -1,
        )
    except Exception as err:
        logger.warning(f"Redis conversation memory read failed: {err}")
        return []

    messages: list[dict[str, str]] = []
    for raw in raw_items or []:
        try:
            item = json.loads(raw)
        except (TypeError, ValueError):
            continue
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})
    return messages


async def append_turn(
    client_id: str,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    if not chat_memory_enabled() or not redis_client.is_configured():
        return
    entries: list[dict[str, Any]] = [
        {"role": "user", "content": user_text, "timestamp": iso_now()},
        {"role": "assistant", "content": assistant_text, "timestamp": iso_now()},
    ]
    key = _key(client_id, conversation_id)
    try:
        for entry in entries:
            await redis_client.execute("RPUSH", key, json.dumps(entry, separators=(",", ":")))
        await redis_client.execute("LTRIM", key, -chat_memory_max_messages(), -1)
        await redis_client.execute("EXPIRE", key, chat_memory_ttl_seconds())
    except Exception as err:
        logger.warning(f"Redis conversation memory write failed: {err}")


async def clear_conversation(client_id: str, conversation_id: str) -> None:
    if not redis_client.is_configured():
        return
    try:
        await redis_client.execute("DEL", _key(client_id, conversation_id))
    except Exception as err:
        logger.warning(f"Redis conversation memory clear failed: {err}")
