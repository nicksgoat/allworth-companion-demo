#!/usr/bin/env bash
# Allworth demo backend — one-command startup (FastAPI).
set -euo pipefail
cd "$(dirname "$0")/backend"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required (https://docs.astral.sh/uv/). Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

if [ -f .env ]; then
  set -a; source .env; set +a
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
exec uv run python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-3000}" --workers "${WEB_CONCURRENCY:-1}"
