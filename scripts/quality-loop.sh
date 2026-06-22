#!/usr/bin/env bash
# Run product-quality gates and generate a Markdown report.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_PATH="$ROOT/backend/quality-loop-report.md"
JSON_REPORT_PATH=""
USE_FAKE_REDIS=false
NO_REDIS=false
QUICK=false
OFFLINE=false
LIVE_ARGS=()
SCRIPT_ARGS=()

while [ "$#" -gt 0 ]; do
  case "$1" in
    --fake-redis)
      USE_FAKE_REDIS=true
      shift
      ;;
    --no-redis)
      NO_REDIS=true
      shift
      ;;
    --quick)
      QUICK=true
      shift
      ;;
    --offline)
      OFFLINE=true
      shift
      ;;
    --live|--live-max-cases|--live-token-budget|--live-timeout-seconds|--live-chat-max-tokens|--live-case-id)
      LIVE_ARGS+=("$1")
      if [ "$1" != "--live" ]; then
        shift
        [ "$#" -gt 0 ] || { echo "ERROR: missing value for ${LIVE_ARGS[-1]}"; exit 1; }
        LIVE_ARGS+=("$1")
      fi
      shift
      ;;
    --json)
      SCRIPT_ARGS+=("$1")
      shift
      ;;
    --json-out)
      shift
      [ "$#" -gt 0 ] || { echo "ERROR: missing value for --json-out"; exit 1; }
      JSON_REPORT_PATH="$1"
      shift
      ;;
    --out)
      shift
      [ "$#" -gt 0 ] || { echo "ERROR: missing value for --out"; exit 1; }
      REPORT_PATH="$1"
      shift
      ;;
    *)
      REPORT_PATH="$1"
      shift
      ;;
  esac
done

if [ -z "$JSON_REPORT_PATH" ]; then
  if [[ "$REPORT_PATH" == *.md ]]; then
    JSON_REPORT_PATH="${REPORT_PATH%.md}.json"
  else
    JSON_REPORT_PATH="$REPORT_PATH.json"
  fi
fi

FAKE_REDIS_PID=""
cleanup() {
  if [ -n "$FAKE_REDIS_PID" ] && kill -0 "$FAKE_REDIS_PID" 2>/dev/null; then
    kill "$FAKE_REDIS_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

cd "$ROOT/backend"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache}"
ORIGINAL_FEEDBACK_LOG_PATH="${FEEDBACK_LOG_PATH:-}"
TEST_FEEDBACK_LOG_PATH="${QUALITY_LOOP_TEST_FEEDBACK_LOG_PATH:-/tmp/allworth-quality-loop-test-feedback.log}"
REPORT_FEEDBACK_LOG_PATH="${ORIGINAL_FEEDBACK_LOG_PATH:-${QUALITY_LOOP_FEEDBACK_LOG_PATH:-/tmp/allworth-quality-loop-feedback.log}}"

mkdir -p "$(dirname "$TEST_FEEDBACK_LOG_PATH")" "$(dirname "$REPORT_FEEDBACK_LOG_PATH")"
: > "$TEST_FEEDBACK_LOG_PATH"
if [ -z "$ORIGINAL_FEEDBACK_LOG_PATH" ]; then
  : > "$REPORT_FEEDBACK_LOG_PATH"
fi
export FEEDBACK_LOG_PATH="$TEST_FEEDBACK_LOG_PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required (https://docs.astral.sh/uv/)."
  exit 1
fi

if [ "$USE_FAKE_REDIS" = "true" ]; then
  if [ "$NO_REDIS" = "true" ]; then
    echo "ERROR: use either --fake-redis or --no-redis, not both"
    exit 1
  fi
  export FAKE_REDIS_HOST="${FAKE_REDIS_HOST:-127.0.0.1}"
  export FAKE_REDIS_PORT="${FAKE_REDIS_PORT:-6380}"
  export REDIS_URL="redis://${FAKE_REDIS_HOST}:${FAKE_REDIS_PORT}/0"
  export CHAT_MEMORY_ENABLED=true
  python3 scripts/fake_redis_server.py >/tmp/allworth-quality-loop-redis.log 2>&1 &
  FAKE_REDIS_PID=$!
  for _ in $(seq 1 20); do
    if UV_CACHE_DIR=/tmp/uv-cache uv run python -c "from allworth_api.data.redis_client import reachability_status; assert reachability_status()['reachable']" >/dev/null 2>&1; then
      break
    fi
    sleep 0.1
  done
  if ! UV_CACHE_DIR=/tmp/uv-cache uv run python -c "from allworth_api.data.redis_client import reachability_status; assert reachability_status()['reachable']" >/dev/null 2>&1; then
    echo "ERROR: fake Redis did not become reachable. See /tmp/allworth-quality-loop-redis.log"
    exit 1
  fi
elif [ "$NO_REDIS" = "true" ]; then
  unset REDIS_URL
  export CHAT_MEMORY_ENABLED=false
fi

UV_RUN=(uv run)
if [ "$OFFLINE" = "true" ]; then
  UV_RUN=(uv run --offline)
fi

if [ "$QUICK" = "true" ]; then
  "${UV_RUN[@]}" --with pytest --with httpx python -m pytest tests/test_quality_loop.py
else
  "${UV_RUN[@]}" --with pytest --with httpx python -m pytest tests
fi
"${UV_RUN[@]}" --with ruff ruff check allworth_api tests
if [ "${SKIP_FRONTEND_TYPECHECK:-false}" != "true" ]; then
  npm --prefix "$ROOT/frontend" run typecheck
fi
export FEEDBACK_LOG_PATH="$REPORT_FEEDBACK_LOG_PATH"
"${UV_RUN[@]}" python scripts/quality_loop.py "${LIVE_ARGS[@]}" "${SCRIPT_ARGS[@]}" --out "$REPORT_PATH" --json-out "$JSON_REPORT_PATH"

echo "Quality loop report written to $REPORT_PATH"
echo "Quality loop JSON written to $JSON_REPORT_PATH"
