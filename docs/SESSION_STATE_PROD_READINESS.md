# Session State And Production Readiness

Generated: 2026-06-20

## Current Verification Snapshot

- Full app quality loop passes locally.
- Deterministic eval suite: 10 passed / 0 failed.
- Memory-covered eval cases: 2.
- Frontend TypeScript check runs inside the quality loop and passes.
- MCP read-only smoke passes.
- Performance smoke passes for dashboard, simulate, and rebalance.
- Advisor brief workflow now returns structured decisions, talking points, open
  questions, and next-best action.
- Production live-data readiness now requires `AUTH_PROVIDER=entra`.
- Production profile memory cannot be enabled unless a durable store and
  governance acknowledgement are configured.
- Targeted live GPT evals passed for:
  - `advisor-handoff-cta`
  - `what-changed-continuity`

Primary command:

```bash
./scripts/quality-loop.sh --offline --no-redis
```

Live targeted example:

```bash
./scripts/quality-loop.sh --fake-redis --live --live-case-id what-changed-continuity \
  --live-max-cases 1 --live-token-budget 1800 --live-timeout-seconds 20 \
  --live-chat-max-tokens 700
```

## Session Memory State

- Redis-backed short-term chat memory is implemented for stateless backend instances.
- Local `.env` currently points Redis at `127.0.0.1:6389`.
- Local readiness fails if that Redis server is not running.
- Quality-loop runs can use `--fake-redis` for local live evals.
- Redis is session memory only; it is not governed durable client intelligence.

## Production Readiness Answer

The app is close to a production demo or internal pilot, but it is not ready for
real client production traffic yet.

It is suitable for:

- synthetic-data demos,
- internal review,
- controlled pilot testing,
- Fly.io development with Azure OpenAI and Redis configured,
- continued product and LLM quality iteration.

It is not yet suitable for real client traffic until the blockers below are
closed.

## Production Blockers

1. Rotate the Azure OpenAI key.
   A plaintext Azure OpenAI key exists in `backend/.env`. The file is gitignored
   and not tracked, but the key should still be treated as exposed and rotated
   before any production deployment.

2. Move secrets to deployment secrets.
   Do not deploy with local `.env` values. Use Fly secrets or Azure runtime
   secrets for `AZURE_OPENAI_API_KEY`, `SESSION_SECRET`, `REDIS_URL`, and any
   warehouse credentials.

3. Configure real Redis.
   Set a reachable `REDIS_URL` for Fly Redis or Azure Cache for Redis, or set
   `CHAT_MEMORY_ENABLED=false` until Redis is available.

4. Configure production identity for real clients.
   The readiness gate now requires `AUTH_PROVIDER=entra` for
   `APP_ENV=production` and `DATA_MODE=live`. Real client traffic still needs
   the actual Entra token validation path and environment values:
   `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, and `ENTRA_AUDIENCE`.

5. Decide data mode.
   `DATA_MODE=mock` is acceptable for demos and CI. Real client traffic needs
   `DATA_MODE=live`, warehouse configuration, and no silent seed fallback.

6. Add production observability sink.
   Current stdout logging works for Fly basics. Real production should connect
   logs and metrics to a central drain, Application Insights, OpenTelemetry, or
   equivalent.

7. Provide governed durable memory before enabling long-term memory.
   The readiness gate blocks `PROFILE_MEMORY_ENABLED=true` in production unless
   `PROFILE_MEMORY_STORE` is durable and `PROFILE_MEMORY_GOVERNANCE_ACK=true`.
   Redis chat memory remains short-term session continuity only.

## Required Production Environment

```text
APP_ENV=production
SESSION_SECRET=<strong shared secret>
CORS_ORIGINS=<frontend origin>
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=<secret>
AZURE_OPENAI_ENDPOINT=<azure-openai-endpoint>
AZURE_OPENAI_API_VERSION=2024-12-01-preview
LLM_CHAT_MODEL=<azure deployment name>
LLM_EXTRACT_MODEL=<azure deployment name>
DATA_MODE=mock|live
REDIS_URL=<redis url if chat memory is enabled>
CHAT_MEMORY_ENABLED=true|false
ALLOW_SEED_AUTH=false
ALLOW_DEMO_AUTH_FALLBACK=false
RATE_LIMIT_ENABLED=true
AUTH_PROVIDER=entra
ENTRA_TENANT_ID=<tenant id>
ENTRA_CLIENT_ID=<application/client id>
ENTRA_AUDIENCE=<api audience>
PROFILE_MEMORY_ENABLED=false
```

## Current Best Next Step

For a production-like demo:

1. Rotate the Azure OpenAI key.
2. Move secrets into Fly.
3. Attach Fly Redis and verify `/api/health/ready`.
4. Deploy with `APP_ENV=production`, `DATA_MODE=mock`, and clear synthetic-data
   labeling.
5. Run:

```bash
./scripts/quality-loop.sh --fake-redis --live --live-case-id advisor-handoff-cta \
  --live-max-cases 1 --live-token-budget 1600 --live-timeout-seconds 20 \
  --live-chat-max-tokens 700
```

For real client production, complete the blockers first.
