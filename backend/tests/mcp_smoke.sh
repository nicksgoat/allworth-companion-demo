#!/usr/bin/env bash
# Smoke-test the MCP server over stdio, invoked exactly as .mcp.json does (from repo root).
# Asserts: financial tools are exposed read-only, provenance envelope, accounts data.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

OUT="$( {
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
  printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_accounts","arguments":{}}}'
  sleep 2
} | uv run --project backend python backend/mcp_server.py 2>/dev/null )"

fail() { echo "MCP SMOKE FAIL: $1"; exit 1; }

printf '%s' "$OUT" | grep -q 'update_client_profile' && fail "write tool exposed" || true
printf '%s' "$OUT" | grep -q '"name":"simulate"' || fail "simulate financial tool not exposed"
printf '%s' "$OUT" | grep -q '"name":"rebalance"' || fail "rebalance financial tool not exposed"
printf '%s' "$OUT" | grep -q '"name":"compare_scenarios"' && fail "extra financial decision tool exposed" || true
printf '%s' "$OUT" | grep -q 'read_only' || fail "no provenance envelope"
printf '%s' "$OUT" | grep -q 'netWorth' || fail "get_accounts returned no data"
echo "MCP smoke OK: read-only financial tools, provenance envelope, accounts data present."
