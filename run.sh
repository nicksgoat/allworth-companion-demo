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

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "WARNING: ANTHROPIC_API_KEY not set (backend/.env). Chat will use cached fallback responses."
fi

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
echo "Backend starting on http://localhost:3000  (LAN: http://${LAN_IP}:3000)"
exec uv run python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-3000}"
