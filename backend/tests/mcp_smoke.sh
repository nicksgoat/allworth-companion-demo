#!/usr/bin/env bash
# Smoke-test the MCP server over stdio, invoked exactly as .mcp.json does (from repo root).
# Asserts: 7 read-only tools (no update_client_profile), provenance envelope, accounts data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

OUT="$( {
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_accounts","arguments":{}}}'
  sleep 2
} | uv run --project services/api python services/api/mcp_server.py 2>/dev/null )"

fail() { echo "MCP SMOKE FAIL: $1"; exit 1; }

tools=$(printf '%s' "$OUT" | grep -o '"name":"get_[a-z_]*"\|"name":"simulate_[a-z_]*"' | sort -u | wc -l | tr -d ' ')
[ "$tools" = 7 ] || fail "expected 7 tools, saw $tools"
printf '%s' "$OUT" | grep -q 'update_client_profile' && fail "write tool exposed" || true
printf '%s' "$OUT" | grep -q 'read_only' || fail "no provenance envelope"
printf '%s' "$OUT" | grep -q 'netWorth' || fail "get_accounts returned no data"
echo "MCP smoke OK: 7 read-only tools, provenance envelope, accounts data present."
