#!/usr/bin/env bash
# Allworth demo — one command runs everything: FastAPI backend + iOS app.
#
#   ./demo.sh            backend + app (Debug build, Metro attached)
#   ./demo.sh --release  backend + app (Release build, no Metro — demo-day mode)
#
# Ctrl-C stops everything this script started.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT/app/AllworthCompanionRN"
LOG=/tmp/allworth-backend.log

CONFIG="Debug"
[ "${1:-}" = "--release" ] && CONFIG="Release"

command -v uv >/dev/null 2>&1 || { echo "ERROR: uv is required — install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
command -v npm >/dev/null 2>&1 || { echo "ERROR: node/npm is required — https://nodejs.org"; exit 1; }
command -v xcrun >/dev/null 2>&1 || { echo "ERROR: Xcode is required (Mac App Store); open it once so it installs its components"; exit 1; }

BACKEND_PID=""
cleanup() {
  if [ -n "$BACKEND_PID" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo
    echo "Stopping backend (pid $BACKEND_PID)"
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# 1. Backend on :3000 (reuse a healthy one if it's already up).
if curl -sf -m 1 http://localhost:3000/api/health >/dev/null 2>&1; then
  echo "Backend already running on :3000 — reusing it."
else
  echo "Starting backend (log: $LOG)…"
  "$ROOT/run.sh" >"$LOG" 2>&1 &
  BACKEND_PID=$!
  for _ in $(seq 1 30); do
    curl -sf -m 1 http://localhost:3000/api/health >/dev/null 2>&1 && break
    sleep 1
  done
  curl -sf -m 1 http://localhost:3000/api/health >/dev/null 2>&1 || { echo "ERROR: backend failed to start — see $LOG"; exit 1; }
  echo "Backend up: http://localhost:3000"
fi

# 2. iOS app.
cd "$APP_DIR"
if [ ! -d node_modules ]; then
  echo "Installing app dependencies…"
  npm install --no-audit --no-fund
fi

echo "Building and launching the iOS app ($CONFIG)…"
if [ "$CONFIG" = "Release" ]; then
  npx expo run:ios --configuration Release --no-bundler
  echo
  if [ -n "$BACKEND_PID" ]; then
    echo "App launched (Release — no Metro). Backend is running; Ctrl-C here stops it."
    wait "$BACKEND_PID"
  else
    echo "App launched (Release — no Metro). Backend was already running — leaving it up."
  fi
else
  # Debug stays attached to Metro; Ctrl-C stops Metro, then the backend.
  npx expo run:ios
fi
