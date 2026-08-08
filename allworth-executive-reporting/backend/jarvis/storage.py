"""Write/delete/restore framework YAMLs with an append-only history log.

History lives at ``<frameworks_dir>/.jarvis-history/events.jsonl``. Each line
is a JSON record with full before/after content so any change is reviewable
and restorable.

Identity comes from (in order):
  1. Azure Easy Auth header ``x-ms-client-principal-name`` (prod).
  2. ``X-User-Email`` header (some proxies use this).
  3. ``JARVIS_USER`` env var (dev fallback).
  4. OS username.
  5. "anonymous".
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from jarvis.knowledge_loader import frameworks_dir

logger = logging.getLogger(__name__)

_MAX_BYTES = 250_000
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_HISTORY_DIR = ".jarvis-history"
_EVENTS_FILE = "events.jsonl"


def user_from_headers(headers) -> str:
    """Extract user identity from a Flask request.headers-like object."""
    # headers is either a Flask EnvironHeaders or a dict
    def _get(name):
        try:
            return headers.get(name)
        except AttributeError:
            return headers.get(name, "")

    azure = _get("x-ms-client-principal-name") or _get("X-Ms-Client-Principal-Name")
    if azure:
        return azure
    explicit = _get("X-User-Email") or _get("x-user-email")
    if explicit:
        return explicit
    return (
        os.environ.get("JARVIS_USER")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or "anonymous"
    )


def _doc_path(key: str) -> Path:
    if not _KEY_RE.match(key or ""):
        raise ValueError(
            f"invalid key {key!r}: must be lowercase, alphanumeric + dashes, 2–64 chars"
        )
    return frameworks_dir() / f"{key}.yaml"


def _history_path() -> Path:
    p = frameworks_dir() / _HISTORY_DIR / _EVENTS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now_iso() -> str:
    """ISO timestamp with millisecond precision (avoids same-second collisions)."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def read_raw(key: str) -> str | None:
    p = _doc_path(key)
    return p.read_text(encoding="utf-8") if p.exists() else None


def write_doc(
    key: str,
    *,
    name: str,
    description: str,
    keywords: list[str],
    content: str,
    user: str,
    category: str | None = None,
    summary: str | None = None,
    related_tables: list[str] | None = None,
    related_columns: list | None = None,
) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("name is required")

    p = _doc_path(key)
    data: dict[str, Any] = {
        "name": name,
        "uri": f"frameworks://{key}",
        "description": (description or "").strip(),
        "keywords": [k.strip() for k in (keywords or []) if k and k.strip()],
    }
    if category:
        data["category"] = category
    if related_tables:
        data["related_tables"] = related_tables
    if related_columns:
        data["related_columns"] = related_columns
    data["content"] = content or ""

    rendered = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    if len(rendered.encode("utf-8")) > _MAX_BYTES:
        raise ValueError(f"document too large (>{_MAX_BYTES} bytes)")

    action = "edit" if p.exists() else "create"
    before = p.read_text(encoding="utf-8") if p.exists() else None

    p.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=p.parent, encoding="utf-8", suffix=".tmp"
    ) as tmp:
        tmp.write(rendered)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, p)

    _append_history(
        {
            "ts": _now_iso(),
            "user": user,
            "key": key,
            "name": name,
            "action": action,
            "summary": (summary or "").strip(),
            "before": before,
            "after": rendered,
        }
    )
    logger.info("Jarvis doc %s %s by %s", action, key, user)
    return data


def delete_doc(key: str, *, user: str, summary: str | None = None) -> bool:
    p = _doc_path(key)
    if not p.exists():
        return False
    before = p.read_text(encoding="utf-8")
    parsed: dict = {}
    try:
        parsed = yaml.safe_load(before) or {}
    except Exception:
        pass
    p.unlink()
    _append_history(
        {
            "ts": _now_iso(),
            "user": user,
            "key": key,
            "name": parsed.get("name", key),
            "action": "delete",
            "summary": (summary or "").strip(),
            "before": before,
            "after": None,
        }
    )
    logger.info("Jarvis doc delete %s by %s", key, user)
    return True


def restore_doc(key: str, ts: str, *, user: str) -> dict[str, Any]:
    events = [e for e in _read_events() if e.get("key") == key and e.get("ts") == ts]
    if not events:
        raise ValueError(f"no history entry for key={key} ts={ts}")
    event = events[-1]
    raw = event.get("after") if event.get("after") else event.get("before")
    if not raw:
        raise ValueError("no content available to restore for that entry")

    parsed = yaml.safe_load(raw) or {}
    return write_doc(
        key,
        name=parsed.get("name", ""),
        description=parsed.get("description", ""),
        keywords=parsed.get("keywords", []) or [],
        content=parsed.get("content", ""),
        category=parsed.get("category"),
        related_tables=parsed.get("related_tables"),
        related_columns=parsed.get("related_columns"),
        user=user,
        summary=f"restored to {ts}",
    )


def history_for_key(key: str, limit: int = 50) -> list[dict[str, Any]]:
    events = [e for e in _read_events() if e.get("key") == key]
    return list(reversed(events[-limit:]))


def global_history(limit: int = 100) -> list[dict[str, Any]]:
    events = _read_events()
    return list(reversed(events[-limit:]))


def diff_for_event(key: str, ts: str) -> dict[str, Any]:
    events = [e for e in _read_events() if e.get("key") == key and e.get("ts") == ts]
    if not events:
        raise ValueError(f"no history entry for key={key} ts={ts}")
    event = events[-1]
    before = event.get("before") or ""
    after = event.get("after") or ""

    raw = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
            n=3,
        )
    )

    lines: list[dict[str, str]] = []
    for raw_line in raw:
        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue
        if raw_line.startswith("@@"):
            lines.append({"type": "hunk", "text": raw_line})
        elif raw_line.startswith("+"):
            lines.append({"type": "add", "text": raw_line[1:]})
        elif raw_line.startswith("-"):
            lines.append({"type": "remove", "text": raw_line[1:]})
        else:
            lines.append({"type": "context", "text": raw_line[1:] if raw_line else ""})

    added = sum(1 for l in lines if l["type"] == "add")
    removed = sum(1 for l in lines if l["type"] == "remove")

    return {
        "key": key,
        "ts": ts,
        "action": event.get("action"),
        "user": event.get("user"),
        "summary": event.get("summary", ""),
        "added": added,
        "removed": removed,
        "lines": lines,
        "before": before,
        "after": after,
    }


def last_edit_for_key(key: str) -> dict[str, Any] | None:
    events = [e for e in _read_events() if e.get("key") == key]
    if not events:
        return None
    last = events[-1]
    return {
        "ts": last.get("ts"),
        "user": last.get("user"),
        "action": last.get("action"),
        "summary": last.get("summary", ""),
    }


def _append_history(event: dict[str, Any]) -> None:
    try:
        with _history_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("failed to append history event")


def _read_events() -> list[dict[str, Any]]:
    p = _history_path()
    if not p.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events
