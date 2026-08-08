"""Proposal persistence + append-only audit log for NFBC.

Proposals are persisted by ``row_id`` so edits + confirms survive a queue
rebuild and are decoupled from the in-memory cache. Every mutating action
(edit, insert, rollforward, comment, transition) is appended to an
``events.jsonl`` audit log, mirroring jarvis/storage.py.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / "knowledge" / ".nfbc-history"
_PROPOSALS = _DIR / "proposals.json"
_EVENTS = _DIR / "events.jsonl"
_lock = Lock()


def _ensure_dir() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def user_from_headers(headers) -> str:
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
    return os.environ.get("USER") or os.environ.get("USERNAME") or "anonymous"


# ── proposals ────────────────────────────────────────────────────────────────


def _read_proposals() -> dict[str, dict]:
    if not _PROPOSALS.exists():
        return {}
    try:
        return json.loads(_PROPOSALS.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read proposals.json")
        return {}


def _write_proposals(data: dict[str, dict]) -> None:
    _ensure_dir()
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=_DIR, encoding="utf-8", suffix=".tmp"
    ) as tmp:
        tmp.write(json.dumps(data, ensure_ascii=False, indent=2))
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, _PROPOSALS)


def save_proposals(rows: list[dict]) -> None:
    """Upsert rows by row_id, preserving any already-confirmed status."""
    with _lock:
        store = _read_proposals()
        for row in rows:
            rid = row.get("row_id")
            if not rid:
                continue
            existing = store.get(rid)
            # Never downgrade a confirmed row back to proposed on rebuild.
            if existing and existing.get("status") == "confirmed":
                continue
            store[rid] = row
        _write_proposals(store)


def get_proposal(row_id: str) -> dict | None:
    with _lock:
        return _read_proposals().get(row_id)


def update_proposal(row_id: str, patch: dict) -> dict | None:
    with _lock:
        store = _read_proposals()
        row = store.get(row_id)
        if row is None:
            return None
        row.update(patch)
        store[row_id] = row
        _write_proposals(store)
        return row


def set_status(row_id: str, status: str, extra: dict | None = None) -> dict | None:
    patch = {"status": status}
    if extra:
        patch.update(extra)
    return update_proposal(row_id, patch)


def all_proposals() -> list[dict]:
    with _lock:
        return list(_read_proposals().values())


# ── audit log ─────────────────────────────────────────────────────────────────


def append_event(event: dict[str, Any]) -> None:
    event.setdefault("ts", now_iso())
    try:
        _ensure_dir()
        with _EVENTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("failed to append nfbc audit event")


def global_history(limit: int = 200) -> list[dict]:
    if not _EVENTS.exists():
        return []
    events: list[dict] = []
    for line in _EVENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(events[-limit:]))
