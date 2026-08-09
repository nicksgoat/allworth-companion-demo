"""HTTP adapter for assignment-aware workspace services."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request

from admin import store as admin_store
from workspace.errors import WorkspaceError
from workspace.service import workspace_service

logger = logging.getLogger(__name__)
bp = Blueprint("workspace", __name__)


def _actor() -> str:
    return admin_store.user_from_headers(request.headers)


@bp.errorhandler(WorkspaceError)
def workspace_error(error: WorkspaceError):
    payload = {"ok": False, "error": error.message, "code": error.code}
    if error.detail:
        logger.info("Workspace request failed (%s): %s", error.code, error.detail)
    return jsonify(payload), error.status_code


@bp.get("/me")
def me():
    email = _actor()
    admin_store.ensure_user(email)
    access = admin_store.effective_for(email)
    assignment = access["assignment"]
    advisor = workspace_service.advisor(email, access.get("advisor_id_override")) if assignment["type"] == "advisor" else None
    advisor_status = "resolved" if advisor else "unresolved" if assignment["type"] == "advisor" else "not_applicable"
    return jsonify({
        "ok": True, "email": email, "assignment": assignment,
        "home_tool_ids": access["home_tool_ids"], "all_access": access["all_access"],
        "effective_tools": access["effective_tools"], "advisor": advisor,
        "advisor_status": advisor_status,
    })


@bp.get("/advisors/resolve")
def resolve_advisor():
    email = request.args.get("email", "").strip()
    override = request.args.get("advisor_id", "").strip() or None
    if not email and not override:
        return jsonify({"ok": False, "error": "Email or advisor ID is required", "code": "invalid_request"}), 400
    advisor = workspace_service.advisor(email, override)
    if advisor is None:
        return jsonify({"ok": False, "error": "Advisor identity is not linked", "code": "advisor_unresolved"}), 404
    return jsonify({"ok": True, "advisor": advisor})


@bp.get("/households/resolve")
def resolve_household():
    identifiers = {
        "planning_id": request.args.get("planning_id"),
        "lead_id": request.args.get("lead_id"),
        "hhid": request.args.get("hhid"),
        "avhhid": request.args.get("avhhid"),
    }
    if not any(identifiers.values()):
        return jsonify({"ok": False, "error": "A household identifier is required", "code": "invalid_request"}), 400
    context = workspace_service.household_context(**identifiers)
    if context is None:
        return jsonify({"ok": False, "error": "Household not found", "code": "household_not_found"}), 404
    return jsonify({"ok": True, "household": context})


@bp.get("/advisor-home")
def advisor_home():
    email = _actor()
    access = admin_store.effective_for(email)
    advisor = workspace_service.advisor(email, access.get("advisor_id_override"))
    requested = request.args.get("advisor_id", "").strip()
    if requested and not access["all_access"] and (not advisor or requested != advisor.get("advisor_id")):
        return jsonify({"ok": False, "error": "Advisor workspace is not available", "code": "advisor_forbidden"}), 403
    advisor_id = requested or (advisor or {}).get("advisor_id")
    if not advisor_id:
        return jsonify({"ok": False, "error": "Advisor identity is not linked", "code": "advisor_unresolved"}), 409
    result = workspace_service.advisor_home(advisor_id)
    return jsonify({"ok": True, "advisor": advisor or {"advisor_id": advisor_id}, **result})
