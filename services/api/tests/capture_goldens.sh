#!/usr/bin/env bash
# Capture the backend's full API contract (bytes) into a goldens directory.
# Requires the backend running on :3000 in fallback mode (no ANTHROPIC_API_KEY)
# so every response is deterministic.
#
#   ./capture_goldens.sh [out_dir]    default: tests/goldens
set -euo pipefail
BASE="http://localhost:3000"
OUT="${1:-"$(cd "$(dirname "$0")" && pwd)/goldens"}"
mkdir -p "$OUT"

health="$(curl -sf "$BASE/api/health")"
case "$health" in
  *'"llm":false'*) ;;
  *) echo "ERROR: backend must run WITHOUT an API key (deterministic fallback mode). Health: $health"; exit 1 ;;
esac

curl -sf -X POST "$BASE/api/demo/reset" -H 'Content-Type: application/json' -d '{"clientId":"maya"}' >/dev/null

get() { curl -sf --output "$OUT/$1" "$BASE$2"; }

# Fixed order: chat-history must be captured before the SSE chats append episodes.
get health.json                    /api/health
get dashboard.json                 /api/clients/maya/dashboard
get nudges.json                    /api/clients/maya/nudges
get spending.json                  /api/clients/maya/spending
get spending_6mo.json              "/api/clients/maya/spending?months=6"
get portfolio.json                 /api/clients/maya/portfolio
get profile.json                   /api/clients/maya/profile
get proactive_wednesday.json       "/api/clients/maya/proactive?session=wednesday"
get proactive_monday.json          "/api/clients/maya/proactive?session=monday"
get chat_history_monday.json       "/api/clients/maya/chat-history?session=monday"
get chat_history_wednesday.json    "/api/clients/maya/chat-history?session=wednesday"
get book.json                      /api/advisors/dana/book
get brief.json                     /api/advisors/dana/clients/maya/brief

sse() {
  curl -sfN --output "$OUT/$1" "$BASE/api/chat" \
    -H 'Content-Type: application/json' -d "$2"
}
sse sse_beat3.txt         '{"clientId":"maya","session":"monday","message":"What would $200K into the SpaceX IPO mean for me?"}'
sse sse_beat4.txt         '{"clientId":"maya","session":"wednesday","message":"Where did we land on the SpaceX IPO?"}'
sse sse_whats_changed.txt '{"clientId":"maya","session":"wednesday","message":"What changed since I was last here?"}'

curl -sf -X POST "$BASE/api/demo/reset" -H 'Content-Type: application/json' -d '{"clientId":"maya"}' >/dev/null
echo "Captured $(ls "$OUT" | wc -l | tr -d ' ') goldens into $OUT"
