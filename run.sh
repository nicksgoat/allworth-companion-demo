#!/usr/bin/env bash
# Allworth demo backend — one-command startup (FastAPI).
set -euo pipefail
cd "$(dirname "$0")/backend"
FAKE_REDIS_PID=""

cleanup() {
  if [ -n "$FAKE_REDIS_PID" ] && kill -0 "$FAKE_REDIS_PID" 2>/dev/null; then
    kill "$FAKE_REDIS_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required (https://docs.astral.sh/uv/). Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if [ -f .env ]; then
  set -a; source .env; set +a
fi

if [ "${USE_FAKE_REDIS:-false}" = "true" ]; then
  export FAKE_REDIS_HOST="${FAKE_REDIS_HOST:-127.0.0.1}"
  export FAKE_REDIS_PORT="${FAKE_REDIS_PORT:-6380}"
  export REDIS_URL="${REDIS_URL:-redis://${FAKE_REDIS_HOST}:${FAKE_REDIS_PORT}/0}"
  export CHAT_MEMORY_ENABLED="${CHAT_MEMORY_ENABLED:-true}"
  python3 scripts/fake_redis_server.py &
  FAKE_REDIS_PID=$!
  for _ in $(seq 1 20); do
    if python3 - <<'PY' >/dev/null 2>&1
import asyncio
from allworth_api.data.redis_client import execute

async def main():
    assert await execute("PING") == "PONG"

asyncio.run(main())
PY
    then
      break
    fi
    sleep 0.1
  done
fi

case "${LLM_PROVIDER:-anthropic}" in
  azure_openai)
    if [ -z "${AZURE_OPENAI_API_KEY:-}" ] || [ -z "${AZURE_OPENAI_ENDPOINT:-}" ]; then
      echo "WARNING: Azure OpenAI is selected, but AZURE_OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT is missing."
      echo "Chat will return an unavailable error until the provider is configured."
    fi
    ;;
  openai)
    if [ -z "${OPENAI_API_KEY:-}" ]; then
      echo "WARNING: OPENAI_API_KEY not set (backend/.env). Chat will return an unavailable error."
    fi
    ;;
  *)
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
      echo "WARNING: ANTHROPIC_API_KEY not set (backend/.env). Chat will return an unavailable error."
    fi
    ;;
esac

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
echo "Backend starting on http://localhost:3000  (LAN: http://${LAN_IP}:3000)"
if [ -n "${REDIS_URL:-}" ]; then
  echo "Redis chat memory: enabled (${CHAT_MEMORY_MAX_MESSAGES:-20} messages, TTL ${CHAT_MEMORY_TTL_SECONDS:-86400}s)"
else
  echo "Redis chat memory: disabled (set REDIS_URL to enable)"
fi
exec uv run python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-3000}" --workers "${WEB_CONCURRENCY:-1}"
