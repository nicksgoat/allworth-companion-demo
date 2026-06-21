"""Server-side conversation memory for the chat assistant.

The chat endpoint is stateless per request, so on its own the model never sees
earlier turns. This store holds the recent user/assistant turns for a
``(client_id, session)`` thread so Prompt 2 can see Prompt 1 and its answer, and
so the thread survives the app being closed and Fly running multiple machines.

Backend is Redis (Fly Upstash) when ``REDIS_URL`` is set; otherwise an in-process
dict — fine for local dev and tests, but not shared across machines. Only clean
user/assistant *text* turns are stored (never tool_use/tool_result blocks), so
they replay cleanly through any provider; the current turn runs its own fresh
tool loop.
"""

import json
import sys

from allworth_api.config import (
    chat_memory_max_messages,
    chat_memory_ttl_seconds,
    redis_url,
)

# Lazily-created async Redis client (redis.asyncio). None until first use / when
# REDIS_URL is unset.
_redis = None
_redis_init = False

# In-process fallback: { "chat:{client_id}:{session}": [ {role, content}, ... ] }
_mem: dict[str, list[dict]] = {}


def _key(client_id: str, session: str) -> str:
    return f"chat:{client_id}:{session}"


def _get_redis():
    """Return a shared async Redis client, or None if not configured/available."""
    global _redis, _redis_init
    if _redis_init:
        return _redis
    _redis_init = True
    url = redis_url()
    if not url:
        return None
    try:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(url, decode_responses=True)
    except Exception as err:  # pragma: no cover - import/connection guard
        print(f"[memory] redis unavailable, using in-process store: {err}", file=sys.stderr)
        _redis = None
    return _redis


async def load_turns(client_id: str, session: str) -> list[dict]:
    """Prior turns for this thread, oldest first, as [{role, content}, ...]."""
    key = _key(client_id, session)
    client = _get_redis()
    if client is not None:
        try:
            raw = await client.lrange(key, 0, -1)
            return [json.loads(r) for r in raw]
        except Exception as err:
            print(f"[memory] redis load failed ({key}): {err}", file=sys.stderr)
            return []
    return list(_mem.get(key, []))


async def append_turns(client_id: str, session: str, turns: list[dict]) -> None:
    """Append turns and trim the thread to the configured message cap."""
    turns = [t for t in turns if t.get("content")]
    if not turns:
        return
    key = _key(client_id, session)
    cap = chat_memory_max_messages()
    client = _get_redis()
    if client is not None:
        try:
            await client.rpush(key, *[json.dumps(t) for t in turns])
            await client.ltrim(key, -cap, -1)
            await client.expire(key, chat_memory_ttl_seconds())
            return
        except Exception as err:
            print(f"[memory] redis append failed ({key}): {err}", file=sys.stderr)
            return
    existing = _mem.setdefault(key, [])
    existing.extend(turns)
    if len(existing) > cap:
        _mem[key] = existing[-cap:]


async def clear(client_id: str, session: str | None = None) -> None:
    """Clear one thread (session given) or all of a client's threads (reset/demo)."""
    client = _get_redis()
    if session is not None:
        key = _key(client_id, session)
        if client is not None:
            try:
                await client.delete(key)
            except Exception as err:
                print(f"[memory] redis clear failed ({key}): {err}", file=sys.stderr)
        _mem.pop(key, None)
        return
    prefix = f"chat:{client_id}:"
    if client is not None:
        try:
            async for k in client.scan_iter(match=f"{prefix}*"):
                await client.delete(k)
        except Exception as err:
            print(f"[memory] redis clear-all failed ({prefix}*): {err}", file=sys.stderr)
    for k in [k for k in _mem if k.startswith(prefix)]:
        _mem.pop(k, None)
