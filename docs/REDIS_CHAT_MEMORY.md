# Redis Chat Memory

The backend supports optional Redis-backed short-term memory for chat. This keeps
the API stateless while still letting the LLM see recent conversation turns.

## What It Stores

Redis stores recent user and assistant messages for a conversation:

```text
conversationId -> last N user/assistant turns
```

It does not store durable profile facts, advisor notes, or compliance history.
Those should move to a durable database later. Redis is intentionally used for
short-lived session memory.

## Environment

```text
REDIS_URL=redis://...
CHAT_MEMORY_ENABLED=true
CHAT_MEMORY_TTL_SECONDS=86400
CHAT_MEMORY_MAX_MESSAGES=20
```

Defaults:

- If `REDIS_URL` is set, chat memory is enabled by default.
- If Redis is not configured, chat still works without Redis memory.
- Failed Redis reads/writes are logged and do not block chat.

## Fly.io

Set Redis as a secret:

```bash
fly secrets set REDIS_URL="redis://..."
fly secrets set CHAT_MEMORY_ENABLED="true"
```

The app will read recent messages from Redis before calling the LLM and append
the latest user/assistant turn after the response completes.

## Local Fake Redis

For local demos without Redis installed:

```bash
USE_FAKE_REDIS=true ./run.sh
```

or:

```bash
./demo.sh --web --fake-redis
```

This starts `backend/scripts/fake_redis_server.py` on `redis://127.0.0.1:6380/0`
and points the backend at it. The fake server only implements the Redis commands
used by chat memory, so it is for demos/tests only.

## Azure Later

Use Azure Cache for Redis and set the same `REDIS_URL`. For TLS-enabled Azure
Redis endpoints, use `rediss://...`.

No application code should need to change when moving from Fly Redis to Azure
Cache for Redis.

## Frontend Contract

`POST /api/chat` accepts an optional `conversationId`:

```json
{
  "clientId": "maya",
  "session": "wednesday",
  "conversationId": "maya:wednesday",
  "message": "What if the car costs $70,000?"
}
```

If omitted, the backend defaults to one conversation per client/session.
