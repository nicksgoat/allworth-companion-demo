"""JSON-backed persistence for File Explorer resource shares.

A *share* grants download access to a *resource* (a directory root or a single
table) to a *principal* (a user email or an Admin-console group). Directory
shares cascade to every table beneath them — that cascade is applied by the
route layer, not here; this module only stores and resolves the raw grants.

Group membership is resolved live from ``admin.store`` so removing a user from a
group immediately revokes any access that group cascaded to them. Persistence
mirrors the atomic-write + lock pattern used by ``admin/store.py``.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

_DIR = Path(__file__).parent / ".file-explorer-state"
_STATE = _DIR / "shares.json"
_lock = Lock()

PRINCIPAL_TYPES = ("user", "group")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _empty_state() -> dict[str, Any]:
    return {"shares": []}


def _read_state() -> dict[str, Any]:
    if not _STATE.exists():
        return _empty_state()
    try:
        data = json.loads(_STATE.read_text(encoding="utf-8"))
        data.setdefault("shares", [])
        return data
    except Exception:
        return _empty_state()


def _write_state(state: dict[str, Any]) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _STATE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _norm_principal(principal_type: str, principal_id: str) -> tuple[str, str]:
    ptype = (principal_type or "").strip().lower()
    if ptype not in PRINCIPAL_TYPES:
        raise ValueError("principal_type must be 'user' or 'group'")
    pid = (principal_id or "").strip()
    if not pid:
        raise ValueError("principal_id is required")
    if ptype == "user":
        pid = norm_email(pid)
        if "@" not in pid:
            raise ValueError("A valid user email address is required")
    return ptype, pid


# ── public API ───────────────────────────────────────────────────────────────


def all_shares() -> list[dict[str, Any]]:
    with _lock:
        return list(_read_state()["shares"])


def list_shares(resource_id: str) -> list[dict[str, Any]]:
    """All share grants for a single resource."""
    with _lock:
        return [
            s for s in _read_state()["shares"] if s.get("resource_id") == resource_id
        ]


def add_share(
    resource_id: str, principal_type: str, principal_id: str, actor: str
) -> dict[str, Any]:
    if not (resource_id or "").strip():
        raise ValueError("resource_id is required")
    ptype, pid = _norm_principal(principal_type, principal_id)
    with _lock:
        state = _read_state()
        for s in state["shares"]:
            if (
                s.get("resource_id") == resource_id
                and s.get("principal_type") == ptype
                and s.get("principal_id") == pid
            ):
                return s  # already shared — idempotent
        entry = {
            "resource_id": resource_id,
            "principal_type": ptype,
            "principal_id": pid,
            "created_at": _now_iso(),
            "created_by": norm_email(actor) or actor,
        }
        state["shares"].append(entry)
        _write_state(state)
        return entry


def remove_share(resource_id: str, principal_type: str, principal_id: str) -> bool:
    ptype, pid = _norm_principal(principal_type, principal_id)
    with _lock:
        state = _read_state()
        before = len(state["shares"])
        state["shares"] = [
            s
            for s in state["shares"]
            if not (
                s.get("resource_id") == resource_id
                and s.get("principal_type") == ptype
                and s.get("principal_id") == pid
            )
        ]
        removed = len(state["shares"]) < before
        if removed:
            _write_state(state)
        return removed


def _user_group_ids(email: str) -> set[str]:
    """Ids of the Admin-console groups the user belongs to (live membership)."""
    email = norm_email(email)
    if not email:
        return set()
    try:
        from admin import store as admin_store
    except Exception:
        return set()
    gids: set[str] = set()
    try:
        for g in admin_store.list_groups():
            members = {norm_email(m) for m in g.get("members", [])}
            if g.get("all_members") or email in members:
                gids.add(g["id"])
    except Exception:
        return set()
    return gids


def shared_resource_ids_for(email: str) -> set[str]:
    """Resource ids shared to the user directly or via any of their groups.

    Directory-cascade is NOT applied here — the caller expands directory roots
    to their child tables.
    """
    email = norm_email(email)
    gids = _user_group_ids(email)
    out: set[str] = set()
    for s in all_shares():
        rid = s.get("resource_id")
        if not rid:
            continue
        ptype = s.get("principal_type")
        pid = s.get("principal_id")
        if ptype == "user" and norm_email(pid) == email:
            out.add(rid)
        elif ptype == "group" and pid in gids:
            out.add(rid)
    return out
