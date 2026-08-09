"""Flask blueprint for the Admin console — mounted at /api/admin by app.py.

The UI is the React SPA served at /admin (nginx); it calls these JSON
endpoints under the shared /api base. All writes reuse the global JWT
middleware and record the acting user for audit fields.

Endpoints:
  GET    /api/admin/tools                     available tools (from tool-manifest.json)
  GET    /api/admin/users                     users + direct/effective access
  POST   /api/admin/users                     add a user by email
  DELETE /api/admin/users/<email>             remove a user
  PUT    /api/admin/users/<email>/tools       set a user's direct tool access
  GET    /api/admin/groups                    groups + members + access
  GET    /api/admin/assignments               workspace assignments
  POST   /api/admin/groups                    create a group
  DELETE /api/admin/groups/<gid>              delete a group
  PUT    /api/admin/groups/<gid>/tools        set a group's tool access
  PUT    /api/admin/groups/<gid>/all-tools    grant/revoke access to ALL tools
  PUT    /api/admin/groups/<gid>/members      set a group's members
  GET    /api/admin/share/<tool>/recipients   who has a tool + roster (sharer)
  POST   /api/admin/share                     grant a tool to a user (sharer)
  POST   /api/admin/share/revoke              revoke a shared tool (sharer)
  GET    /api/admin/me                         effective access for the caller
  GET    /api/admin/health
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from admin import store

bp = Blueprint("admin", __name__)


def _actor() -> str:
    return store.user_from_headers(request.headers)


def _tools_from_body() -> list[str]:
    body = request.get_json(silent=True) or {}
    tools = body.get("tools", [])
    return [str(t) for t in tools] if isinstance(tools, list) else []


def _share_tools_from_body() -> list[str]:
    body = request.get_json(silent=True) or {}
    tools = body.get("share_tools", [])
    return [str(t) for t in tools] if isinstance(tools, list) else []


def _assignment_body() -> tuple[str, str, list[str]]:
    body = request.get_json(silent=True) or {}
    tools = body.get("home_tool_ids", [])
    tools = [str(t) for t in tools] if isinstance(tools, list) else []
    return str(body.get("name", "")), str(body.get("type", "")), tools


@bp.get("/health")
def health():
    return jsonify({"ok": True, "backup": store.backup_status()})


@bp.get("/me")
def me():
    """Effective access for the requesting user — powers live enforcement.

    First contact also auto-registers the caller in the roster (so a brand-new
    user shows up in the console and joins the derived "All Users" group). When
    enforcement is disabled (the default), every caller is reported as
    all-access so the UI never gates while the roster is still being built.
    """
    email = _actor()
    store.ensure_user(email)
    info = store.effective_for(email)
    info["enforced"] = store.enforcement_enabled()
    if not info["enforced"]:
        info["all_access"] = True
        info["can_share_all"] = True
    return jsonify({"ok": True, **info})


@bp.get("/tools")
def get_tools():
    return jsonify({"ok": True, "tools": store.available_tools()})


# ── users ────────────────────────────────────────────────────────────────────


@bp.get("/users")
def get_users():
    return jsonify({"ok": True, "users": store.list_users()})


@bp.post("/users")
def create_user():
    body = request.get_json(silent=True) or {}
    try:
        user = store.add_user(body.get("email", ""), _actor())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "user": user}), 201


@bp.delete("/users/<path:email>")
def delete_user(email: str):
    store.remove_user(email)
    return jsonify({"ok": True})


@bp.put("/users/<path:email>/tools")
def update_user_tools(email: str):
    try:
        user = store.set_user_tools(email, _tools_from_body(), _share_tools_from_body())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "user": user})


@bp.put("/users/<path:email>/assignment")
def update_user_assignment(email: str):
    body = request.get_json(silent=True) or {}
    try:
        user = store.set_user_assignment(
            email,
            body.get("assignment_id"),
            body.get("advisor_id_override"),
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "user": user})


# ── assignments ─────────────────────────────────────────────────────────────


@bp.get("/assignments")
def get_assignments():
    return jsonify({"ok": True, "assignments": store.list_assignments()})


@bp.post("/assignments")
def create_assignment():
    name, assignment_type, tools = _assignment_body()
    try:
        assignment = store.add_assignment(name, assignment_type, tools, _actor())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "assignment": assignment}), 201


@bp.put("/assignments/<aid>")
def edit_assignment(aid: str):
    name, assignment_type, tools = _assignment_body()
    try:
        assignment = store.update_assignment(aid, name, assignment_type, tools)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "assignment": assignment})


@bp.delete("/assignments/<aid>")
def delete_assignment(aid: str):
    try:
        store.remove_assignment(aid)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


# ── groups ───────────────────────────────────────────────────────────────────


@bp.get("/groups")
def get_groups():
    return jsonify({"ok": True, "groups": store.list_groups()})


@bp.post("/groups")
def create_group():
    body = request.get_json(silent=True) or {}
    try:
        group = store.add_group(body.get("name", ""), body.get("description", ""), _actor())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "group": group}), 201


@bp.delete("/groups/<gid>")
def delete_group(gid: str):
    try:
        store.remove_group(gid)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True})


@bp.put("/groups/<gid>/tools")
def update_group_tools(gid: str):
    try:
        group = store.set_group_tools(gid, _tools_from_body(), _share_tools_from_body())
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "group": group})


@bp.put("/groups/<gid>/all-tools")
def update_group_all_tools(gid: str):
    body = request.get_json(silent=True) or {}
    try:
        group = store.set_group_all_tools(gid, bool(body.get("all_tools", False)))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "group": group})


@bp.put("/groups/<gid>/members")
def update_group_members(gid: str):
    body = request.get_json(silent=True) or {}
    members = body.get("members", [])
    members = [str(m) for m in members] if isinstance(members, list) else []
    try:
        group = store.set_group_members(gid, members)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "group": group})


# ── tool sharing (delegated, non-admin) ──────────────────────────────────────
#
# A user granted "share" access to a tool (or an all-access admin) may grant
# view access to that tool to other users straight from the tool page, without
# opening the Admin console. The acting user is resolved from the SSO headers
# and must pass ``store.can_share`` for the requested tool.


def _require_can_share(tool_id: str):
    """Return (actor, None) when allowed, or (actor, error_response) when not.

    Sharing is always checked against real grants except when enforcement is
    off — in that mode the app runs fully open, matching ``/me``.
    """
    actor = _actor()
    if not store.enforcement_enabled() or store.can_share(actor, tool_id):
        return actor, None
    return actor, (jsonify({"ok": False, "error": "You don't have share access to this tool"}), 403)


@bp.get("/share/<tool_id>/recipients")
def get_share_recipients(tool_id: str):
    _actor_email, err = _require_can_share(tool_id)
    if err:
        return err
    return jsonify({"ok": True, **store.share_recipients(tool_id)})


@bp.post("/share")
def create_share():
    body = request.get_json(silent=True) or {}
    tool_id = str(body.get("tool", "")).strip()
    email = str(body.get("email", "")).strip()
    actor, err = _require_can_share(tool_id)
    if err:
        return err
    try:
        user = store.share_tool(tool_id, email, actor)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "user": user}), 201


@bp.post("/share/revoke")
def revoke_share():
    body = request.get_json(silent=True) or {}
    tool_id = str(body.get("tool", "")).strip()
    email = str(body.get("email", "")).strip()
    _actor_email, err = _require_can_share(tool_id)
    if err:
        return err
    store.revoke_share(tool_id, email)
    return jsonify({"ok": True})


# ── roster backups (restore) ─────────────────────────────────────────────────


@bp.get("/backups")
def get_backups():
    """List available roster snapshots (daily backups in ADLS)."""
    return jsonify({"ok": True, "backups": store.list_backups()})


@bp.post("/backups/restore")
def restore_backup():
    """Restore the roster from a named snapshot (admin recovery button)."""
    body = request.get_json(silent=True) or {}
    try:
        result = store.restore_backup(str(body.get("name", "")))
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, **result})
