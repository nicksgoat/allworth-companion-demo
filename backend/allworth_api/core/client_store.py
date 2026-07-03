"""Client-owned demo state: saved goal plans and advisor requests.

Two tiny Redis-backed collections (same Fly/Upstash instance as the chat
conversation store, same hand-parsed URL — redis.from_url chokes on Upstash
passwords), with an in-process fallback for local dev and tests:

- ``goal_plans:{client_id}``  hash  {goal_id: {"monthly": .., "years": .., "ts": ..}}
- ``requests:{client_id}``    list  [{"id", "kind", "slotDisplay", "topic", ...}]

Sync on purpose: these are called from sync tool handlers (planning.py) and
plain FastAPI routes; the payloads are a few hundred bytes.
"""

import json
import sys

from allworth_api.config import redis_url

_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days, like chat memory
_MAX_REQUESTS = 50

_redis = None
_redis_init = False

# In-process fallback stores.
_mem_plans: dict[str, dict[str, dict]] = {}
_mem_requests: dict[str, list[dict]] = {}


def _build_redis(url: str):
    import redis as redislib

    scheme, _, rest = url.partition("://")
    use_tls = scheme == "rediss"
    creds, sep, hostpart = rest.rpartition("@")
    if not sep:
        hostpart = rest
    username = password = None
    if creds:
        username, _, password = creds.partition(":")
        password = password or None
        username = username or None
    db = 0
    if "/" in hostpart:
        hostpart, _, db_str = hostpart.partition("/")
        db = int(db_str) if db_str.isdigit() else 0
    if ":" in hostpart:
        host, _, port_str = hostpart.rpartition(":")
        port = int(port_str) if port_str.isdigit() else 6379
    else:
        host, port = hostpart, 6379
    return redislib.Redis(
        host=host,
        port=port,
        username=username,
        password=password,
        db=db,
        ssl=use_tls,
        decode_responses=True,
        socket_timeout=3,
    )


def _get_redis():
    global _redis, _redis_init
    if _redis_init:
        return _redis
    _redis_init = True
    url = redis_url()
    if not url:
        return None
    try:
        _redis = _build_redis(url)
    except Exception as err:  # pragma: no cover - import/connection guard
        print(f"[client_store] redis unavailable, using in-process store: {err}", file=sys.stderr)
        _redis = None
    return _redis


# ── Goal plans ───────────────────────────────────────────────────────────


def save_goal_plan(client_id: str, goal_id: str, plan: dict) -> None:
    key = f"goal_plans:{client_id}"
    client = _get_redis()
    if client is not None:
        try:
            client.hset(key, goal_id, json.dumps(plan))
            client.expire(key, _TTL_SECONDS)
            return
        except Exception as err:
            print(f"[client_store] redis save failed ({key}): {err}", file=sys.stderr)
            return
    _mem_plans.setdefault(client_id, {})[goal_id] = plan


def load_goal_plans(client_id: str) -> dict[str, dict]:
    key = f"goal_plans:{client_id}"
    client = _get_redis()
    if client is not None:
        try:
            raw = client.hgetall(key)
            return {k: json.loads(v) for k, v in raw.items()}
        except Exception as err:
            print(f"[client_store] redis load failed ({key}): {err}", file=sys.stderr)
            return {}
    return dict(_mem_plans.get(client_id, {}))


# ── Advisor requests (bookings + topic requests) ─────────────────────────


def append_request(client_id: str, record: dict) -> None:
    key = f"requests:{client_id}"
    client = _get_redis()
    if client is not None:
        try:
            client.rpush(key, json.dumps(record))
            client.ltrim(key, -_MAX_REQUESTS, -1)
            client.expire(key, _TTL_SECONDS)
            return
        except Exception as err:
            print(f"[client_store] redis append failed ({key}): {err}", file=sys.stderr)
            return
    lst = _mem_requests.setdefault(client_id, [])
    lst.append(record)
    if len(lst) > _MAX_REQUESTS:
        _mem_requests[client_id] = lst[-_MAX_REQUESTS:]


def load_requests(client_id: str) -> list[dict]:
    key = f"requests:{client_id}"
    client = _get_redis()
    if client is not None:
        try:
            raw = client.lrange(key, 0, -1)
            return [json.loads(r) for r in raw]
        except Exception as err:
            print(f"[client_store] redis load failed ({key}): {err}", file=sys.stderr)
            return []
    return list(_mem_requests.get(client_id, []))
