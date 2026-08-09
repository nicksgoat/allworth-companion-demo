"""JSON-backed persistence for the Admin console.

Stores users, groups and their tool-access grants in a single JSON state file,
mirroring the atomic-write + lock pattern used by ``nfbc/queue_store.py``.

Access model
------------
Every tool is identified by its slug in the root ``tool-manifest.json``.
A user's *effective* access is the union of:
    * the tools granted to the user directly, and
    * the tools granted to every group the user is currently a member of.

Because effective access is computed from live group membership, removing a
user from a group immediately revokes the access that group cascaded to them.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from admin.assignment_repository import AssignmentRepository, sqlite_database_url
from tool_manifest import manifest_tools

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / ".admin-state"
_STATE = _DIR / "admin_state.json"
# Committed baseline roster used as a last-resort fallback when there is no
# local state AND no ADLS backup could be restored. Keep it current by copying
# a known-good export here (see seed_local_if_empty).
_SEED = Path(__file__).parent / "admin_state.seed.json"
def _assignment_database_url() -> str:
    configured_url = os.getenv("ADMIN_ASSIGNMENTS_DATABASE_URL")
    if configured_url:
        return configured_url
    configured_path = os.getenv("ADMIN_ASSIGNMENTS_DB")
    return sqlite_database_url(Path(configured_path) if configured_path else _DIR / "assignments.sqlite3")


_ASSIGNMENTS = AssignmentRepository(_assignment_database_url)
_lock = Lock()

# Bootstrap admins are always members of the all-access "Admin" group so the
# system owner can never be locked out by enforcement. Extend via the
# ADMIN_BOOTSTRAP_EMAILS env var (comma-separated).
_BOOTSTRAP_ADMIN_GROUP_ID = "admin"
# The "All Users" group implicitly contains every user. Admins share tools with
# the whole organisation by granting them to this group. Its membership is
# derived from the live user roster, so it can't be edited or deleted.
_ALL_USERS_GROUP_ID = "all-users"
_BOOTSTRAP_EMAILS = {
    e.strip().lower()
    for e in os.getenv("ADMIN_BOOTSTRAP_EMAILS", "").split(",")
    if e.strip()
}
_BOOTSTRAP_EMAILS.add("mark.fanning@allworthfinancial.com")

ASSIGNMENT_TYPES = {"advisor", "executive", "operations", "platform_admin", "general"}
DEFAULT_ASSIGNMENT = {
    "id": "general",
    "name": "General workspace",
    "type": "general",
    "home_tool_ids": [],
    "built_in": True,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def user_from_headers(headers) -> str:
    """Resolve the acting user from Azure/SSO headers (for audit fields)."""
    def _get(name: str) -> str:
        try:
            return headers.get(name) or ""
        except AttributeError:
            return ""

    return (
        _get("x-ms-client-principal-name")
        or _get("X-Ms-Client-Principal-Name")
        or _get("X-User-Email")
        or _get("x-user-email")
        or os.environ.get("USER")
        or os.environ.get("USERNAME")
        or "anonymous"
    )


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


# ── available tools (from the hub registry) ──────────────────────────────────


def _manifest_tools() -> tuple[dict[str, str], ...]:
    """Load and validate the canonical tool manifest.

    Tool registration is security-sensitive: an incomplete fallback list can
    silently change grants. Fail loudly when the manifest is absent or invalid
    instead of maintaining a second source of truth in Python.
    """
    tools: list[dict[str, str]] = []
    for entry in manifest_tools():
        tool_id = str(entry.get("id", "")).strip()
        status = str(entry.get("status", "")).strip()
        tools.append({
            "id": tool_id,
            "name": str(entry.get("name") or tool_id),
            "category": str(entry.get("category") or "utilities"),
            "status": status,
        })
    return tuple(tools)


def available_tools() -> list[dict[str, str]]:
    """Return tool metadata from the canonical root manifest."""
    return [dict(tool) for tool in _manifest_tools()]


def _valid_tool_ids() -> set[str]:
    return {tool["id"] for tool in available_tools() if tool["status"] in {"live", "new"}}


# ── state I/O ────────────────────────────────────────────────────────────────


def _empty_state() -> dict[str, Any]:
    return {"users": {}, "groups": {}, "assignments": {}, "shares": []}


def _read_state() -> dict[str, Any]:
    if not _STATE.exists():
        data = _empty_state()
        data["assignments"] = _ASSIGNMENTS.as_dict()
        return data
    try:
        data = json.loads(_STATE.read_text(encoding="utf-8"))
        data.setdefault("users", {})
        data.setdefault("groups", {})
        legacy_assignments = data.setdefault("assignments", {})
        _ASSIGNMENTS.migrate_legacy(legacy_assignments)
        data["assignments"] = _ASSIGNMENTS.as_dict()
        data.setdefault("shares", [])
        return data
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Admin state is unreadable: %s", exc)
        data = _empty_state()
        data["assignments"] = _ASSIGNMENTS.as_dict()
        return data


def _write_state(state: dict[str, Any]) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    snapshot = dict(state)
    snapshot["assignments"] = _ASSIGNMENTS.as_dict()
    fd, tmp = tempfile.mkstemp(dir=str(_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(snapshot, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _STATE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    # Flag that the local store diverged from the last data-lake backup, then
    # kick off an immediate best-effort upload so a deploy (the container volume
    # is ephemeral) can never lose a recent change. The upload runs off the
    # request thread and is a no-op until startup confirms this is a trusted
    # writer (see _immediate_backup_enabled), so bootstrap/seed states are never
    # pushed over the shared roster.
    global _dirty
    _dirty = True
    _schedule_backup()


# ── projections ──────────────────────────────────────────────────────────────


def _groups_for(email: str, state: dict[str, Any]) -> list[dict[str, Any]]:
    email = norm_email(email)
    return [
        g for g in state["groups"].values()
        # An ``all_members`` group (e.g. "All Users") implicitly contains every
        # user, so its tool grants cascade to everyone.
        if g.get("all_members")
        or email in {norm_email(m) for m in g.get("members", [])}
    ]


def _user_view(user: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    email = norm_email(user["email"])
    direct = sorted(set(user.get("tools", [])))
    # Share access is a stronger grant than view; a shareable tool is always
    # also viewable, so the direct-view list is the union of the two.
    direct_share = sorted(set(user.get("share_tools", [])) & set(direct))
    groups = _groups_for(email, state)
    all_tool_ids = [t["id"] for t in available_tools()]
    inherited: dict[str, list[str]] = {}
    for g in groups:
        # A group flagged all_tools grants every current *and* future tool.
        granted = all_tool_ids if g.get("all_tools") else g.get("tools", [])
        for tid in granted:
            inherited.setdefault(tid, []).append(g["name"])
    effective = sorted(set(direct) | set(inherited.keys()))
    return {
        "email": email,
        "direct_tools": direct,
        "direct_share_tools": direct_share,  # subset of direct the user may re-share
        "inherited_tools": inherited,   # tool_id -> [group names granting it]
        "effective_tools": effective,
        "groups": [{"id": g["id"], "name": g["name"]} for g in groups],
        "assignment_id": user.get("assignment_id"),
        "advisor_id_override": user.get("advisor_id_override"),
        "created_at": user.get("created_at"),
        "created_by": user.get("created_by"),
    }


def _assignment_view(assignment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": assignment["id"],
        "name": assignment["name"],
        "type": assignment.get("type", "general"),
        "home_tool_ids": sorted(set(assignment.get("home_tool_ids", []))),
        "built_in": bool(assignment.get("built_in", False)),
        "created_at": assignment.get("created_at"),
        "created_by": assignment.get("created_by"),
    }


def _group_view(group: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    # An ``all_members`` group reflects the full user roster; its membership is
    # derived live rather than stored, so new users appear automatically.
    if group.get("all_members"):
        members = sorted(norm_email(e) for e in state["users"].keys())
    else:
        members = sorted({norm_email(m) for m in group.get("members", [])})
    tools = sorted(set(group.get("tools", [])))
    return {
        "id": group["id"],
        "name": group["name"],
        "description": group.get("description", ""),
        "tools": tools,
        "share_tools": sorted(set(group.get("share_tools", [])) & set(tools)),
        "all_tools": bool(group.get("all_tools", False)),
        "all_members": bool(group.get("all_members", False)),
        "members": members,
        "created_at": group.get("created_at"),
        "created_by": group.get("created_by"),
    }


# ── public API ───────────────────────────────────────────────────────────────


def list_users() -> list[dict[str, Any]]:
    with _lock:
        state = _read_state()
        return sorted(
            (_user_view(u, state) for u in state["users"].values()),
            key=lambda v: v["email"],
        )


def list_groups() -> list[dict[str, Any]]:
    with _lock:
        state = _read_state()
        return sorted(
            (_group_view(g, state) for g in state["groups"].values()),
            key=lambda v: v["name"].lower(),
        )


def list_assignments() -> list[dict[str, Any]]:
    with _lock:
        state = _read_state()
        rows = [_assignment_view(DEFAULT_ASSIGNMENT)]
        rows.extend(_assignment_view(a) for a in state["assignments"].values())
        return sorted(rows, key=lambda row: (row["built_in"] is False, row["name"].lower()))


def add_user(email: str, actor: str) -> dict[str, Any]:
    email = norm_email(email)
    if not email or "@" not in email:
        raise ValueError("A valid email address is required")
    with _lock:
        state = _read_state()
        if email in state["users"]:
            raise ValueError(f"User {email} already exists")
        state["users"][email] = {
            "email": email,
            "tools": [],
            "share_tools": [],
            "assignment_id": None,
            "advisor_id_override": None,
            "created_at": now_iso(),
            "created_by": actor,
        }
        _write_state(state)
        return _user_view(state["users"][email], state)


def ensure_user(email: str, actor: str = "self-provision") -> bool:
    """Register ``email`` in the roster if it isn't already known.

    Called on first authenticated access so a new user is auto-added and, via
    the derived "All Users" membership, immediately shows up in the console.
    Returns True when a new user was created. No-op for blank/invalid emails.
    """
    email = norm_email(email)
    if not email or "@" not in email:
        return False
    with _lock:
        state = _read_state()
        if email in state["users"]:
            return False
        state["users"][email] = {
            "email": email,
            "tools": [],
            "share_tools": [],
            "assignment_id": None,
            "advisor_id_override": None,
            "created_at": now_iso(),
            "created_by": actor,
        }
        _write_state(state)
        return True


def remove_user(email: str) -> None:
    email = norm_email(email)
    with _lock:
        state = _read_state()
        state["users"].pop(email, None)
        for g in state["groups"].values():
            g["members"] = [m for m in g.get("members", []) if norm_email(m) != email]
        _write_state(state)


def set_user_tools(email: str, tools: list[str], share_tools: list[str] | None = None) -> dict[str, Any]:
    email = norm_email(email)
    valid = _valid_tool_ids()
    cleaned = sorted({t for t in tools if t in valid})
    # Share access implies view access, so a shareable tool is forced into the
    # view set and any share grant for a non-viewable tool is dropped.
    share_in = set(share_tools or []) & set(cleaned)
    cleaned_share = sorted(share_in)
    with _lock:
        state = _read_state()
        if email not in state["users"]:
            raise ValueError(f"Unknown user {email}")
        state["users"][email]["tools"] = cleaned
        state["users"][email]["share_tools"] = cleaned_share
        _write_state(state)
        return _user_view(state["users"][email], state)


def set_user_assignment(email: str, assignment_id: str | None,
                        advisor_id_override: str | None = None) -> dict[str, Any]:
    email = norm_email(email)
    assignment_id = (assignment_id or "").strip() or None
    advisor_id_override = (advisor_id_override or "").strip() or None
    with _lock:
        state = _read_state()
        if email not in state["users"]:
            raise ValueError(f"Unknown user {email}")
        if assignment_id not in {None, "general"} and assignment_id not in state["assignments"]:
            raise ValueError(f"Unknown assignment {assignment_id}")
        state["users"][email]["assignment_id"] = assignment_id
        state["users"][email]["advisor_id_override"] = advisor_id_override
        _write_state(state)
        return _user_view(state["users"][email], state)


def add_assignment(name: str, assignment_type: str, home_tool_ids: list[str], actor: str) -> dict[str, Any]:
    name = (name or "").strip()
    assignment_type = (assignment_type or "").strip().lower()
    if not name:
        raise ValueError("An assignment name is required")
    if assignment_type not in ASSIGNMENT_TYPES:
        raise ValueError("Unknown assignment type")
    aid = _slugify(name)
    if aid == "general":
        raise ValueError("General workspace is built in")
    valid = _valid_tool_ids()
    tools = sorted({tool for tool in home_tool_ids if tool in valid})
    with _lock:
        state = _read_state()
        if aid in state["assignments"]:
            raise ValueError(f"An assignment named '{name}' already exists")
        assignment = {
            "id": aid, "name": name, "type": assignment_type,
            "home_tool_ids": tools, "created_at": now_iso(), "created_by": actor,
        }
        _ASSIGNMENTS.create(assignment)
        state["assignments"][aid] = assignment
        _write_state(state)
        return _assignment_view(assignment)


def update_assignment(aid: str, name: str, assignment_type: str,
                      home_tool_ids: list[str]) -> dict[str, Any]:
    if aid == "general":
        raise ValueError("General workspace is built in")
    name = (name or "").strip()
    assignment_type = (assignment_type or "").strip().lower()
    if not name:
        raise ValueError("An assignment name is required")
    if assignment_type not in ASSIGNMENT_TYPES:
        raise ValueError("Unknown assignment type")
    valid = _valid_tool_ids()
    tools = sorted({tool for tool in home_tool_ids if tool in valid})
    with _lock:
        state = _read_state()
        if aid not in state["assignments"]:
            raise ValueError(f"Unknown assignment {aid}")
        assignment = _ASSIGNMENTS.update(aid, name=name, assignment_type=assignment_type,
                                         home_tool_ids=tools)
        state["assignments"][aid] = assignment
        _write_state(state)
        return _assignment_view(assignment)


def remove_assignment(aid: str) -> None:
    if aid == "general":
        raise ValueError("General workspace is built in")
    with _lock:
        state = _read_state()
        if aid not in state["assignments"]:
            raise ValueError(f"Unknown assignment {aid}")
        assigned = [email for email, user in state["users"].items()
                    if user.get("assignment_id") == aid]
        if assigned:
            raise ValueError("Reassign its users before deleting this assignment")
        _ASSIGNMENTS.delete(aid)
        state["assignments"].pop(aid, None)
        _write_state(state)


def assignment_for(email: str) -> dict[str, Any]:
    email = norm_email(email)
    with _lock:
        state = _read_state()
        user = state["users"].get(email, {})
        aid = user.get("assignment_id")
        assignment = state["assignments"].get(aid) if aid else None
        if aid == "general" or assignment is None:
            assignment = DEFAULT_ASSIGNMENT
        result = _assignment_view(assignment)
        result["advisor_id_override"] = user.get("advisor_id_override")
        return result


def add_group(name: str, description: str, actor: str) -> dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("A group name is required")
    gid = _slugify(name)
    with _lock:
        state = _read_state()
        if gid in state["groups"]:
            raise ValueError(f"A group named '{name}' already exists")
        state["groups"][gid] = {
            "id": gid,
            "name": name,
            "description": (description or "").strip(),
            "tools": [],
            "all_tools": False,
            "members": [],
            "created_at": now_iso(),
            "created_by": actor,
        }
        _write_state(state)
        return _group_view(state["groups"][gid], state)


def remove_group(gid: str) -> None:
    if gid in (_BOOTSTRAP_ADMIN_GROUP_ID, _ALL_USERS_GROUP_ID):
        raise ValueError("This group is built-in and can't be deleted")
    with _lock:
        state = _read_state()
        state["groups"].pop(gid, None)
        _write_state(state)


def set_group_tools(gid: str, tools: list[str], share_tools: list[str] | None = None) -> dict[str, Any]:
    valid = _valid_tool_ids()
    cleaned = sorted({t for t in tools if t in valid})
    share_in = set(share_tools or []) & set(cleaned)
    cleaned_share = sorted(share_in)
    with _lock:
        state = _read_state()
        if gid not in state["groups"]:
            raise ValueError(f"Unknown group {gid}")
        state["groups"][gid]["tools"] = cleaned
        state["groups"][gid]["share_tools"] = cleaned_share
        _write_state(state)
        return _group_view(state["groups"][gid], state)


def set_group_all_tools(gid: str, value: bool) -> dict[str, Any]:
    with _lock:
        state = _read_state()
        if gid not in state["groups"]:
            raise ValueError(f"Unknown group {gid}")
        state["groups"][gid]["all_tools"] = bool(value)
        _write_state(state)
        return _group_view(state["groups"][gid], state)


def set_group_members(gid: str, members: list[str]) -> dict[str, Any]:
    cleaned = sorted({norm_email(m) for m in members if norm_email(m)})
    with _lock:
        state = _read_state()
        if gid not in state["groups"]:
            raise ValueError(f"Unknown group {gid}")
        if state["groups"][gid].get("all_members"):
            raise ValueError("This group includes every user automatically")
        # Auto-register any member emails that are not yet known users so their
        # inherited access is reflected on the Users tab.
        for email in cleaned:
            state["users"].setdefault(
                email,
                {"email": email, "tools": [], "created_at": now_iso(), "created_by": "group-membership"},
            )
        state["groups"][gid]["members"] = cleaned
        _write_state(state)
        return _group_view(state["groups"][gid], state)


def _slugify(value: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in value.lower())
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-") or "group"


# ── enforcement helpers ──────────────────────────────────────────────────────


def enforcement_enabled() -> bool:
    """Whether per-user access enforcement is active.

    Defaults to OFF so a deploy never locks the team out before the user list
    is populated. Flip on with ``ADMIN_ENFORCEMENT=1`` (or true/yes/on) once
    users and groups are configured.
    """
    return (os.getenv("ADMIN_ENFORCEMENT", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def ensure_bootstrap() -> None:
    """Guarantee an all-access "Admin" group exists and that every bootstrap
    email is a member of it. Safe to call repeatedly (idempotent)."""
    with _lock:
        state = _read_state()
        grp = state["groups"].get(_BOOTSTRAP_ADMIN_GROUP_ID)
        if grp is None:
            grp = {
                "id": _BOOTSTRAP_ADMIN_GROUP_ID,
                "name": "Admin",
                "description": "Full access to every tool, including new ones",
                "tools": [],
                "all_tools": True,
                "members": [],
                "created_at": now_iso(),
                "created_by": "bootstrap",
            }
            state["groups"][_BOOTSTRAP_ADMIN_GROUP_ID] = grp
        grp["all_tools"] = True  # the Admin group is always all-access
        members = {norm_email(m) for m in grp.get("members", [])}
        for email in _BOOTSTRAP_EMAILS:
            members.add(email)
            state["users"].setdefault(
                email,
                {"email": email, "tools": [], "created_at": now_iso(), "created_by": "bootstrap"},
            )
        grp["members"] = sorted(members)

        # "All Users" — an all-members group so tools can be shared with the
        # whole organisation at once. Membership is derived from the live user
        # roster (see ``_group_view``/``_groups_for``), so new users join
        # automatically. It starts with no tool grants; admins add them.
        all_users = state["groups"].get(_ALL_USERS_GROUP_ID)
        if all_users is None:
            all_users = {
                "id": _ALL_USERS_GROUP_ID,
                "name": "All Users",
                "description": "Every user. Grant tools here to share them with everyone.",
                "tools": [],
                "all_tools": False,
                "all_members": True,
                "members": [],
                "created_at": now_iso(),
                "created_by": "bootstrap",
            }
            state["groups"][_ALL_USERS_GROUP_ID] = all_users
        all_users["all_members"] = True  # membership is always the full roster
        _write_state(state)


def effective_for(email: str) -> dict[str, Any]:
    """Resolve a single user's effective tool access (for live enforcement).

    ``all_access`` is True when the user belongs to any all-tools group; such
    users implicitly get every current and future tool. ``share_tools`` is the
    set of tools the user is allowed to re-share with others (an all-access
    user can share everything, i.e. ``can_share_all``).
    """
    email = norm_email(email)
    with _lock:
        state = _read_state()
        user = state["users"].get(email, {"email": email, "tools": []})
        groups = _groups_for(email, state)
        all_tool_ids = [t["id"] for t in available_tools()]
        all_access = any(g.get("all_tools") for g in groups)
        effective: set[str] = set(user.get("tools", []))
        shareable: set[str] = set(user.get("share_tools", [])) & set(user.get("tools", []))
        for g in groups:
            granted = set(all_tool_ids if g.get("all_tools") else g.get("tools", []))
            effective |= granted
            g_share = set(all_tool_ids) if g.get("all_tools") else set(g.get("share_tools", []))
            shareable |= g_share & granted
        if all_access:
            effective |= set(all_tool_ids)
            shareable |= set(all_tool_ids)
        aid = user.get("assignment_id")
        assignment = state["assignments"].get(aid) if aid else None
        if aid == "general" or assignment is None:
            assignment = DEFAULT_ASSIGNMENT
        assignment_view = _assignment_view(assignment)
        permitted_home_tools = [tool for tool in assignment_view["home_tool_ids"]
                                if all_access or tool in effective]
        return {
            "email": email,
            "effective_tools": sorted(effective),
            "share_tools": sorted(shareable),
            "can_share_all": bool(all_access),
            "all_access": bool(all_access),
            "known": email in state["users"],
            "assignment": assignment_view,
            "home_tool_ids": permitted_home_tools,
            "advisor_id_override": user.get("advisor_id_override"),
        }


def can_share(email: str, tool_id: str) -> bool:
    """Whether ``email`` is permitted to share ``tool_id`` with other users."""
    info = effective_for(email)
    return bool(info["can_share_all"]) or tool_id in set(info["share_tools"])


def share_tool(tool_id: str, recipient: str, actor: str) -> dict[str, Any]:
    """Grant view access to ``tool_id`` for ``recipient`` on behalf of ``actor``.

    Auto-registers an unknown recipient and records the share so the granting
    user can later revoke exactly what they shared.
    """
    recipient = norm_email(recipient)
    if not recipient or "@" not in recipient:
        raise ValueError("A valid recipient email address is required")
    if tool_id not in _valid_tool_ids():
        raise ValueError(f"Unknown tool {tool_id}")
    with _lock:
        state = _read_state()
        user = state["users"].setdefault(
            recipient,
            {"email": recipient, "tools": [], "share_tools": [], "created_at": now_iso(), "created_by": actor},
        )
        tools = set(user.get("tools", []))
        if tool_id not in tools:
            tools.add(tool_id)
            user["tools"] = sorted(tools)
        ledger = state.setdefault("shares", [])
        if not any(
            norm_email(s.get("email")) == recipient and s.get("tool") == tool_id for s in ledger
        ):
            ledger.append(
                {"tool": tool_id, "email": recipient, "by": norm_email(actor), "at": now_iso()}
            )
        _write_state(state)
        return _user_view(state["users"][recipient], state)


def revoke_share(tool_id: str, recipient: str) -> None:
    """Remove a direct view grant for ``tool_id`` from ``recipient``.

    Only the direct grant is removed; access inherited from a group is left
    intact. The matching share-ledger entries are cleared.
    """
    recipient = norm_email(recipient)
    with _lock:
        state = _read_state()
        user = state["users"].get(recipient)
        if user:
            user["tools"] = [t for t in user.get("tools", []) if t != tool_id]
            user["share_tools"] = [t for t in user.get("share_tools", []) if t != tool_id]
        state["shares"] = [
            s
            for s in state.get("shares", [])
            if not (norm_email(s.get("email")) == recipient and s.get("tool") == tool_id)
        ]
        _write_state(state)


def share_recipients(tool_id: str) -> dict[str, Any]:
    """List who currently has ``tool_id`` plus the roster for a share picker."""
    with _lock:
        state = _read_state()
        ledger = {
            (s.get("tool"), norm_email(s.get("email"))): s for s in state.get("shares", [])
        }
        recipients = []
        for email, user in state["users"].items():
            email = norm_email(email)
            has_direct = tool_id in set(user.get("tools", []))
            groups = _groups_for(email, state)
            all_tool_ids = [t["id"] for t in available_tools()]
            inherited = [
                g["name"]
                for g in groups
                if g.get("all_tools") or tool_id in set(g.get("tools", []))
            ] if not has_direct else []
            if not has_direct and not inherited:
                continue
            share = ledger.get((tool_id, email))
            recipients.append(
                {
                    "email": email,
                    "direct": has_direct,
                    "inherited_from": inherited,
                    "shared_by": share.get("by") if share else None,
                    "shared_at": share.get("at") if share else None,
                }
            )
        recipients.sort(key=lambda r: r["email"])
        roster = sorted(norm_email(e) for e in state["users"].keys())
        return {"tool": tool_id, "recipients": recipients, "roster": roster}


# ── data-lake durability (backup + restore) ──────────────────────────────────
#
# Design goal: keep the admin store as fast as a local file. All reads/writes
# stay on the container filesystem (sub-millisecond). Durability across
# container restarts/redeploys is provided by:
#   * restore-on-startup: if the local file is missing, download the latest
#     backup from ADLS Gen2 before bootstrapping.
#   * a low-frequency background backup (default once/day) that only uploads
#     when the state changed, plus a best-effort upload on process exit.
# No ADLS I/O ever happens on a request path.

_dirty = False
_backup_started = False
_last_backup_iso: str | None = None
_last_backup_error: str | None = None
# Guard against clobbering a good remote roster. Flipped OFF when startup could
# not confirm the remote backup (e.g. a transient ADLS/auth error), so a failed
# restore can never overwrite the saved users with a bootstrap-only state.
_backup_safe = True
# Only True once startup has confirmed this is a trusted writer that RESTORED
# the roster from ADLS. Until then, per-write immediate backups are suppressed
# so bootstrap/seed writes during startup can never overwrite the shared roster.
_immediate_backup_enabled = False


def _adls_target() -> tuple[str, str, str]:
    account = os.getenv("ADMIN_STATE_ADLS_ACCOUNT") or os.getenv("ADLS_ACCOUNT_NAME", "dlallworthai")
    container = os.getenv("ADMIN_STATE_ADLS_CONTAINER") or os.getenv("ADLS_SILVER_CONTAINER", "silver")
    path = os.getenv("ADMIN_STATE_ADLS_PATH", "admin/admin_state.json")
    return account, container, path


def _adls_credential():
    """Match delta_reader's auth precedence: account key → SP → MSI → CLI."""
    key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or os.getenv("ADLS_ACCOUNT_KEY")
    if key:
        return key
    try:
        from azure.identity import (
            AzureCliCredential,
            ClientSecretCredential,
            ManagedIdentityCredential,
        )
    except Exception:
        return None
    cid, cs, tid = (
        os.getenv("AZURE_CLIENT_ID"),
        os.getenv("AZURE_CLIENT_SECRET"),
        os.getenv("AZURE_TENANT_ID"),
    )
    if cid and cs and tid:
        return ClientSecretCredential(tid, cid, cs)
    if os.getenv("AZURE_USE_MANAGED_IDENTITY", "").lower() in ("1", "true", "yes"):
        msi = os.getenv("AZURE_MSI_CLIENT_ID")
        return ManagedIdentityCredential(client_id=msi) if msi else ManagedIdentityCredential()
    try:
        return AzureCliCredential()
    except Exception:
        return None


def _adls_file_client(rel_path: str):
    """A DataLakeFileClient for ``rel_path`` in the configured container, or None."""
    try:
        from azure.storage.filedatalake import DataLakeServiceClient
    except Exception:
        return None
    cred = _adls_credential()
    if cred is None:
        return None
    account, container, _ = _adls_target()
    try:
        svc = DataLakeServiceClient(
            account_url=f"https://{account}.dfs.core.windows.net", credential=cred
        )
        return svc.get_file_system_client(container).get_file_client(rel_path)
    except Exception as e:
        logger.warning("admin backup: could not build ADLS client: %s", e)
        return None


def backup_enabled() -> bool:
    flag = os.getenv("ADMIN_BACKUP_ENABLED")
    if flag is not None:
        return flag.strip().lower() in ("1", "true", "yes", "on")
    # Auto-enable only when explicit deploy credentials are present (account
    # key, service principal, or managed identity). Azure-CLI-only local dev is
    # left OFF to avoid noisy failed uploads; set ADMIN_BACKUP_ENABLED=1 to opt in.
    if os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or os.getenv("ADLS_ACCOUNT_KEY"):
        return True
    if all(os.getenv(k) for k in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID")):
        return True
    if os.getenv("AZURE_USE_MANAGED_IDENTITY", "").lower() in ("1", "true", "yes"):
        return True
    return False


def readonly_mode() -> bool:
    """Whether this instance is a READ-ONLY replica of the shared roster.

    A read-only instance (e.g. the dev site) reads the same ADLS roster file as
    production but never uploads, so it mirrors prod's users/groups without ever
    clobbering them. Local edits are kept only in memory/on the container disk
    and are discarded on the next refresh/restart. Enable with
    ``ADMIN_STATE_READONLY=1``.
    """
    return (os.getenv("ADMIN_STATE_READONLY", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _allow_seed_backup() -> bool:
    """Whether a seed/bootstrap-only roster may be uploaded to the shared store.

    OFF by default: uploads are only trusted when the roster was RESTORED from
    ADLS, so a deploy that couldn't see the real roster can never overwrite it
    with the committed baseline. Set ``ADMIN_STATE_ALLOW_SEED_BACKUP=1`` once for
    genuine first-time setup (no shared roster exists yet).
    """
    return (os.getenv("ADMIN_STATE_ALLOW_SEED_BACKUP", "") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )



def _is_not_found(e: Exception) -> bool:
    """True when an ADLS error means the blob simply doesn't exist yet.

    A genuine 404 is the expected first-run case (safe to bootstrap fresh). Any
    other error means a backup may exist that we failed to read — in which case
    the caller must NOT overwrite the remote.
    """
    try:
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(e, ResourceNotFoundError):
            return True
    except Exception:
        pass
    if getattr(e, "status_code", None) == 404:
        return True
    name = type(e).__name__
    return "ResourceNotFound" in name or "PathNotFound" in name or "BlobNotFound" in str(e)


def restore_from_lake_if_empty() -> str:
    """Seed the local store from the latest ADLS backup when it's missing.

    Returns one of:
      * ``"restored"`` — local state is present (downloaded now or already on disk),
      * ``"empty"``    — no remote backup exists yet / ADLS not configured (safe
        to bootstrap a fresh roster and back it up),
      * ``"failed"``   — a backup likely exists but could not be read or parsed;
        callers MUST NOT overwrite the remote, or a transient error would wipe
        the whole roster.
    """
    if _STATE.exists():
        return "restored"
    _, _, path = _adls_target()
    fc = _adls_file_client(path)
    if fc is None:
        # ADLS not configured at all — nothing to restore and nothing to clobber.
        return "empty"
    try:
        data = fc.download_file().readall()
    except Exception as e:
        if _is_not_found(e):
            logger.info("admin backup: no remote roster yet — starting fresh")
            return "empty"
        logger.warning(
            "admin backup: restore failed (%s) — will NOT overwrite remote roster",
            type(e).__name__,
        )
        return "failed"
    try:
        parsed = json.loads(data)  # validate before trusting it
    except Exception:
        logger.warning(
            "admin backup: remote roster is unreadable/corrupt — will NOT overwrite it"
        )
        return "failed"
    _DIR.mkdir(parents=True, exist_ok=True)
    _ASSIGNMENTS.replace_all(parsed.get("assignments", {}).values())
    _STATE.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    logger.info("admin backup: restored roster from adls://%s", path)
    return "restored"


def seed_local_if_empty() -> bool:
    """Seed the local store from the committed baseline roster when it's missing.

    A durable, in-repo fallback for when there is no ADLS backup to restore (or
    ADLS is unavailable): the committed ``admin_state.seed.json`` guarantees a
    fresh deploy is never empty. Never overwrites an existing local state.
    """
    if _STATE.exists() or not _SEED.exists():
        return False
    try:
        parsed = json.loads(_SEED.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("seed is not a JSON object")
        parsed.setdefault("users", {})
        parsed.setdefault("groups", {})
        parsed.setdefault("assignments", {})
        parsed.setdefault("shares", [])
        _DIR.mkdir(parents=True, exist_ok=True)
        _ASSIGNMENTS.replace_all(parsed["assignments"].values())
        _write_state(parsed)
        logger.info(
            "admin: seeded roster from committed baseline (%d users) %s",
            len(parsed.get("users", {})),
            _SEED.name,
        )
        return True
    except Exception as e:
        logger.warning("admin: seed load failed: %s", e)
        return False


def backup_to_lake(force: bool = False) -> bool:
    """Upload the local store to ADLS: a stable 'latest' file + a daily snapshot.

    No-op (fast) unless the state changed since the last backup or ``force``.
    """
    global _dirty, _last_backup_iso, _last_backup_error
    if readonly_mode():
        # A read-only replica never writes back to the shared roster.
        return False
    if not _backup_safe:
        # Startup could not confirm the remote roster; refuse all uploads so a
        # bootstrap-only state can never overwrite the saved users.
        return False
    if not force and not _dirty:
        return False
    with _lock:
        if not _STATE.exists():
            return False
        data = _STATE.read_bytes()
    _, _, path = _adls_target()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    snapshot = f"admin/backups/admin_state_{day}.json"
    try:
        for target in (path, snapshot):
            fc = _adls_file_client(target)
            if fc is None:
                return False
            fc.upload_data(data, overwrite=True)
        _dirty = False
        _last_backup_iso = now_iso()
        _last_backup_error = None
        logger.info("admin backup: uploaded roster to adls://%s (+ %s)", path, snapshot)
        return True
    except Exception as e:
        _last_backup_error = f"{type(e).__name__}: {e}"
        logger.warning("admin backup: upload failed: %s", _last_backup_error)
        return False


def backup_status() -> dict[str, Any]:
    return {
        "enabled": backup_enabled(),
        "readonly": readonly_mode(),
        "safe": _backup_safe,
        "immediate": _immediate_backup_enabled,
        "dirty": _dirty,
        "last_backup": _last_backup_iso,
        "last_error": _last_backup_error,
    }


def _schedule_backup() -> None:
    """Fire a best-effort ADLS upload of the current roster off the request path.

    Called on every write so a redeploy (the container volume is ephemeral)
    can't lose a recent change. Suppressed until startup confirms a trusted
    writer, in read-only mode, or when backups are marked unsafe — so a
    bootstrap/seed state can never be pushed over the shared roster.
    """
    if not _immediate_backup_enabled or readonly_mode() or not _backup_safe:
        return
    try:
        threading.Thread(
            target=backup_to_lake, kwargs={"force": True}, daemon=True,
            name="admin-lake-backup-now",
        ).start()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("admin backup: could not schedule immediate backup: %s", e)


def list_backups(limit: int = 60) -> list[dict[str, Any]]:
    """List available roster snapshots in ADLS (newest first).

    Includes the daily snapshots under ``admin/backups/`` written by
    ``backup_to_lake``. Returns [] when ADLS isn't configured.
    """
    try:
        from azure.storage.filedatalake import DataLakeServiceClient
    except Exception:
        return []
    cred = _adls_credential()
    if cred is None:
        return []
    account, container, _ = _adls_target()
    try:
        svc = DataLakeServiceClient(
            account_url=f"https://{account}.dfs.core.windows.net", credential=cred
        )
        fs = svc.get_file_system_client(container)
        items: list[dict[str, Any]] = []
        for p in fs.get_paths(path="admin/backups", recursive=False):
            name = str(p.name).split("/")[-1]
            if not name.endswith(".json"):
                continue
            lm = getattr(p, "last_modified", None)
            items.append(
                {
                    "name": name,
                    "size": getattr(p, "content_length", None),
                    "last_modified": str(lm) if lm else None,
                }
            )
        items.sort(key=lambda x: x["name"], reverse=True)
        return items[:limit]
    except Exception as e:
        if _is_not_found(e):
            return []
        logger.warning("admin backup: list snapshots failed: %s", type(e).__name__)
        return []


def restore_backup(name: str) -> dict[str, Any]:
    """Restore the roster from a named daily snapshot.

    Downloads ``admin/backups/<name>``, validates it, writes it locally, and
    (on a writer) uploads it as the current shared roster so the restore is
    durable. Returns a small summary of the restored roster.
    """
    name = (name or "").strip()
    if not name or "/" in name or "\\" in name or not name.endswith(".json"):
        raise ValueError("Invalid backup name")
    fc = _adls_file_client(f"admin/backups/{name}")
    if fc is None:
        raise ValueError("Backups are unavailable (ADLS not configured)")
    try:
        data = fc.download_file().readall()
    except Exception as e:
        if _is_not_found(e):
            raise ValueError(f"Backup {name} was not found")
        raise ValueError(f"Could not read backup {name}: {type(e).__name__}")
    try:
        parsed = json.loads(data)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except Exception:
        raise ValueError("Backup is unreadable or corrupt")
    with _lock:
        _DIR.mkdir(parents=True, exist_ok=True)
        _ASSIGNMENTS.replace_all(parsed.get("assignments", {}).values())
        _STATE.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    ensure_bootstrap()  # keep the all-access Admin group intact
    if not readonly_mode():
        backup_to_lake(force=True)  # make the restore the current shared roster
    with _lock:
        state = _read_state()
        return {
            "restored": name,
            "users": len(state.get("users", {})),
            "groups": len(state.get("groups", {})),
            "assignments": len(state.get("assignments", {})),
        }


def refresh_from_lake() -> str:
    """Download the latest shared roster from ADLS, overwriting local state.

    Used by read-only replicas to (re)sync with production. Unlike
    ``restore_from_lake_if_empty`` this replaces any existing local file so the
    replica always reflects the current shared roster. Returns ``"restored"``,
    ``"empty"`` (no remote file / ADLS not configured) or ``"failed"``.
    """
    _, _, path = _adls_target()
    fc = _adls_file_client(path)
    if fc is None:
        return "empty"
    try:
        data = fc.download_file().readall()
    except Exception as e:
        if _is_not_found(e):
            return "empty"
        logger.warning("admin readonly: refresh failed (%s)", type(e).__name__)
        return "failed"
    try:
        parsed = json.loads(data)  # validate before trusting it
    except Exception:
        logger.warning("admin readonly: remote roster is unreadable/corrupt")
        return "failed"
    with _lock:
        _DIR.mkdir(parents=True, exist_ok=True)
        _ASSIGNMENTS.replace_all(parsed.get("assignments", {}).values())
        _STATE.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return "restored"


def _refresh_loop(interval_seconds: float) -> None:
    while True:
        time.sleep(interval_seconds)
        try:
            refresh_from_lake()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("admin readonly: refresh loop error: %s", e)


def _backup_loop(interval_seconds: float) -> None:
    while True:
        time.sleep(interval_seconds)
        try:
            backup_to_lake()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("admin backup: loop error: %s", e)


def init_persistence() -> None:
    """Startup hook: restore-if-empty → bootstrap → start daily backup.

    Call this once at app startup instead of ``ensure_bootstrap`` directly.
    """
    global _backup_started, _backup_safe, _immediate_backup_enabled

    # Read-only replica (e.g. the dev site): mirror the shared prod roster and
    # never write back. Pull the latest at startup and on a short interval so
    # the user list tracks production without ever clobbering it.
    if readonly_mode():
        _backup_safe = False  # belt-and-suspenders: uploads are also disabled
        try:
            status = refresh_from_lake()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("admin readonly: initial refresh failed: %s", e)
            status = "failed"
        if status != "restored":
            # No shared roster reachable yet — fall back to the committed baseline
            # so the console still renders locally.
            seed_local_if_empty()
        ensure_bootstrap()  # local-only guarantee of the Admin group
        if not _backup_started:
            try:
                minutes = float(os.getenv("ADMIN_STATE_REFRESH_MINUTES", "10"))
            except ValueError:
                minutes = 10.0
            interval = max(60.0, minutes * 60.0)
            threading.Thread(
                target=_refresh_loop, args=(interval,), daemon=True, name="admin-lake-refresh"
            ).start()
            _backup_started = True
            logger.info(
                "admin: read-only replica mode — mirroring shared roster (refresh every %.0fm)",
                minutes,
            )
        return

    try:
        status = restore_from_lake_if_empty()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("admin backup: restore failed: %s", e)
        status = "failed"

    if status == "failed":
        # A remote backup likely exists but we couldn't read it. Serve locally
        # but DISABLE all uploads for this process, so a transient restore error
        # can't overwrite the saved roster with a bootstrap-only state. The good
        # remote copy is preserved for the next healthy start.
        _backup_safe = False
        ensure_bootstrap()
        logger.error(
            "admin backup: could not restore the existing roster — backups are "
            "DISABLED for this process to protect it. Check ADLS access, then "
            "restart to restore the saved users."
        )
        return

    if status != "restored":
        # Nothing was restored from ADLS — fall back to the committed baseline
        # roster so a fresh (or degraded) start is never empty.
        seed_local_if_empty()

    ensure_bootstrap()

    # CRITICAL: only a roster RESTORED from the shared store is trusted for
    # upload. A seed/bootstrap-only start must NEVER be written back — otherwise
    # a deploy that couldn't see the real roster (empty ADLS, ephemeral volume)
    # would upload the 1-user baseline and wipe the live user list, then that
    # empty roster propagates to every other instance. This has wiped the roster
    # before. First-time setup (no shared roster yet) can opt in explicitly.
    if status != "restored" and not _allow_seed_backup():
        _backup_safe = False
        logger.warning(
            "admin backup: no shared roster was restored — serving a seed/bootstrap "
            "roster with uploads DISABLED so it can't overwrite the shared store. "
            "Set ADMIN_STATE_ALLOW_SEED_BACKUP=1 only for genuine first-time setup."
        )
        return

    if not backup_enabled():
        logger.info("admin backup: disabled (no ADLS credentials or ADMIN_BACKUP_ENABLED=0)")
        return

    # Capture the freshly bootstrapped/restored state immediately.
    backup_to_lake(force=True)

    if not _backup_started:
        try:
            hours = float(os.getenv("ADMIN_BACKUP_INTERVAL_HOURS", "24"))
        except ValueError:
            hours = 24.0
        interval = max(60.0, hours * 3600.0)
        threading.Thread(
            target=_backup_loop, args=(interval,), daemon=True, name="admin-lake-backup"
        ).start()
        atexit.register(lambda: backup_to_lake(force=True))
        _backup_started = True
        logger.info("admin backup: daily backup thread started (every %.1fh)", hours)

    # Trusted writer with a restored roster: every future write now persists to
    # ADLS immediately (see _schedule_backup), so a redeploy can't lose changes.
    _immediate_backup_enabled = True
