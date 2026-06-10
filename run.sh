#!/usr/bin/env bash
# Allworth demo backend — one-command startup.
set -euo pipefail
cd "$(dirname "$0")/app/backend"

if [ ! -d node_modules ]; then
  echo "Installing backend dependencies..."
  npm install --no-audit --no-fund
fi

if [ -f .env ]; then
  set -a; source .env; set +a
fi

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "WARNING: ANTHROPIC_API_KEY not set (app/backend/.env). Chat will use cached fallback responses."
fi

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || echo "unknown")
echo "Backend starting on http://localhost:3000  (LAN: http://${LAN_IP}:3000)"
exec node server.js
