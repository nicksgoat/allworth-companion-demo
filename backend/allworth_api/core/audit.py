"""Append-only JSONL audit log for every tool invocation.

Inspired by the analytics plugin's PreToolUse hook. Every tool call gets a
single-line JSON record: timestamp, client, tool name, params (scrubbed),
elapsed_ms, and token estimate. The file lives alongside the runtime data.

The log is observe-only — it never blocks a tool call.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from allworth_api.config import API_DIR

AUDIT_PATH = API_DIR / "audit.log"

# Fields we never write to disk in plaintext.
SENSITIVE_KEYS = frozenset({"access_token", "password", "token", "api_key", "secret"})

CHARS_PER_TOKEN = 4  # conservative estimate


def _scrub(obj):
    """Recursively redact sensitive keys from params."""
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in SENSITIVE_KEYS else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    return obj


def estimate_tokens(obj) -> int:
    """Rough token count from JSON serialization length."""
    try:
        text = json.dumps(obj, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        text = str(obj)
    return max(1, len(text) // CHARS_PER_TOKEN)


def log_tool_call(
    *,
    tool: str,
    client_id: str,
    params: dict | None = None,
    result: dict | None = None,
    elapsed_ms: float | None = None,
) -> None:
    """Append one audit record. Never raises — failures print to stderr."""
    try:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "client": client_id,
            "tool": tool,
            "params": _scrub(params or {}),
            "elapsed_ms": round(elapsed_ms, 1) if elapsed_ms is not None else None,
            "tokens_in": estimate_tokens(params),
            "tokens_out": estimate_tokens(result) if result else 0,
        }
        with AUDIT_PATH.open("a") as f:
            f.write(json.dumps(record, separators=(",", ":"), default=str) + "\n")
    except Exception as err:
        print(f"[audit] write failed: {err}", file=sys.stderr)
