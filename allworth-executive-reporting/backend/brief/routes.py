"""Executive Brief API blueprint.

The Executive Brief tool ("CEO inbox operating system") serves a mobile-first
React page at /brief. It runs in one of two modes:

  MOCK MODE (default) - the page renders bundled sanitized sample emails
    client-side; per-email actions persist to localStorage. Requires nothing
    from IT and is the concept demo.

  LIVE MODE (USE_LIVE_MAIL=1 AND an Easy Auth Graph token present) - the
    backend reads the signed-in user's own mailbox via Microsoft Graph
    (delegated, read-only), classifies it with Claude, and serves it here.
    Actions still never send; drafts save to Outlook only if Mail.ReadWrite is
    granted, otherwise locally.

Live mode is gated so the tool degrades safely: if the flag is off, the token
is absent (token store / Mail.Read not yet provisioned), or any Graph/Claude
call fails, the API reports mock mode and the frontend uses bundled data. The
original email is never hidden by an analysis failure.

All routes are gated by the global JWT / Easy Auth middleware — nothing here is
reachable anonymously.
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, request

from . import analyze, graph

logger = logging.getLogger(__name__)

bp = Blueprint("brief", __name__)

# Neutral defaults when triage can't classify a message (Claude unavailable).
_DEFAULT_CLASS = {
    "category": "needs_response",
    "priority": "medium",
    "recommended_action": "",
    "confidence": 0.0,
}


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def _user_email() -> str | None:
    """Identity resolved by the global auth middleware (JWT claims or the
    Easy Auth X-MS-CLIENT-PRINCIPAL headers forwarded by nginx)."""
    return request.environ.get("user.email")


def _graph_token() -> str | None:
    """Delegated Graph token injected by App Service Easy Auth's token store."""
    return request.headers.get("X-MS-TOKEN-AAD-ACCESS-TOKEN")


def _live_enabled() -> bool:
    return _truthy(os.getenv("USE_LIVE_MAIL"))


def _live_active() -> bool:
    """Live mode only when the flag is on AND a Graph token is present."""
    return _live_enabled() and bool(_graph_token())


# --------------------------------------------------------------------------- #
# Health / identity / capability
# --------------------------------------------------------------------------- #
@bp.route("/api/health")
def health():
    return jsonify({"success": True, "status": "ok", "tool": "brief"})


@bp.route("/api/me")
def me():
    return jsonify({"success": True, "email": _user_email()})


@bp.route("/api/status")
def status():
    """Capability report the frontend reads once to pick mock vs live.

    ?probe=1 additionally runs a tiny live Claude call (plain ping + a one-item
    forced-tool triage) and returns the outcome/error, so triage failures can be
    diagnosed without server-log access. Reveals only the error class/message —
    never the API key."""
    graph_token = bool(_graph_token())
    live = _live_enabled() and graph_token
    body = {
        "success": True,
        "mode": "live" if live else "mock",
        "mock_mode": not live,
        "use_live_mail": _live_enabled(),
        "graph_token_available": graph_token,
        "anthropic_configured": analyze.is_configured(),
        "user": _user_email(),
    }
    if request.args.get("probe") == "1":
        body["probe"] = analyze.self_test()
    return jsonify(body)


# --------------------------------------------------------------------------- #
# Live mail (no-ops in mock mode → frontend falls back to bundled data)
# --------------------------------------------------------------------------- #
def _to_executive_email(item: dict, cls: dict) -> dict:
    """Merge Graph list metadata + Claude triage into the frontend's
    ExecutiveEmail shape (camelCase)."""
    return {
        "id": item["id"],
        "threadId": item["threadId"],
        "senderName": item["senderName"],
        "senderEmail": item["senderEmail"],
        "subject": item["subject"],
        "receivedAt": item["receivedAt"],
        "priority": cls.get("priority", _DEFAULT_CLASS["priority"]),
        "category": cls.get("category", _DEFAULT_CLASS["category"]),
        "summary": cls.get("summary") or item.get("bodyPreview", ""),
        "request": cls.get("request", ""),
        "deadline": cls.get("deadline"),
        "recommendedAction": cls.get("recommended_action", ""),
        "confidence": cls.get("confidence", 0.0),
        "attachmentCount": item["attachmentCount"],
        "unread": item["unread"],
        "completed": False,
    }


@bp.route("/api/messages")
def messages():
    """Live inbox: Graph list → Claude triage → ExecutiveEmail[]. In mock mode
    returns an empty live set with mode=mock so the frontend uses bundled data."""
    if not _live_active():
        return jsonify({"success": True, "mode": "mock", "emails": []})
    token = _graph_token()
    try:
        items = graph.get_inbox_messages(token, top=50)
    except graph.GraphError as e:
        logger.warning("inbox fetch failed: %s", e)
        return jsonify({"success": False, "mode": "mock", "error": str(e)}), e.status
    classifications = analyze.triage_messages(items)
    emails = [_to_executive_email(it, classifications.get(it["id"], _DEFAULT_CLASS)) for it in items]
    return jsonify({"success": True, "mode": "live", "emails": emails})


@bp.route("/api/messages/<message_id>")
def message_detail(message_id: str):
    """Full message + thread + deep analysis for the detail view."""
    if not _live_active():
        return jsonify({"success": False, "mode": "mock", "error": "live mode off"}), 409
    token = _graph_token()
    try:
        msg = graph.get_message(token, message_id)
        thread = graph.get_thread(token, msg["threadId"])
    except graph.GraphError as e:
        logger.warning("message fetch failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), e.status
    analysis = analyze.analyze_message(msg, thread)  # None → frontend fallback
    return jsonify({"success": True, "message": msg, "thread": thread, "analysis": analysis})


@bp.route("/api/analyze", methods=["POST"])
def analyze_route():
    """Re-run deep analysis for a message id (mail is always re-fetched from
    Graph server-side — never trusted from the client body)."""
    if not _live_active():
        return jsonify({"success": False, "mode": "mock", "error": "live mode off"}), 409
    body = request.get_json(silent=True) or {}
    message_id = body.get("id")
    if not message_id:
        return jsonify({"success": False, "error": "missing id"}), 400
    token = _graph_token()
    try:
        msg = graph.get_message(token, message_id)
        thread = graph.get_thread(token, msg["threadId"])
    except graph.GraphError as e:
        return jsonify({"success": False, "error": str(e)}), e.status
    analysis = analyze.analyze_message(msg, thread)
    if analysis is None:
        return jsonify({"success": True, "analysis": None, "fallback": True})
    return jsonify({"success": True, "analysis": analysis})


@bp.route("/api/draft-reply", methods=["POST"])
def draft_reply_route():
    """Generate an editable draft for an intent + tone. Never sends."""
    if not _live_active():
        return jsonify({"success": False, "mode": "mock", "error": "live mode off"}), 409
    body = request.get_json(silent=True) or {}
    message_id = body.get("id")
    intent = body.get("intent", "custom")
    tone = body.get("tone", "executive")
    if not message_id:
        return jsonify({"success": False, "error": "missing id"}), 400
    token = _graph_token()
    try:
        msg = graph.get_message(token, message_id)
        thread = graph.get_thread(token, msg["threadId"])
    except graph.GraphError as e:
        return jsonify({"success": False, "error": str(e)}), e.status
    analysis = analyze.analyze_message(msg, thread)
    draft = analyze.draft_reply(msg, analysis, intent, tone)
    if draft is None:
        return jsonify({"success": False, "error": "draft generation unavailable"}), 503
    return jsonify({"success": True, "draft": draft})


@bp.route("/api/save-draft", methods=["POST"])
def save_draft_route():
    """Save a reviewed draft. With Mail.ReadWrite → an Outlook reply draft;
    otherwise report local-only so the frontend keeps it in localStorage.
    There is no send path."""
    if not _live_active():
        return jsonify({"success": True, "saved": "local", "mode": "mock"})
    body = request.get_json(silent=True) or {}
    message_id = body.get("id")
    text = body.get("text", "")
    if not message_id or not text:
        return jsonify({"success": False, "error": "missing id or text"}), 400
    token = _graph_token()
    try:
        result = graph.create_reply_draft(token, message_id, text)
    except graph.GraphError as e:
        if e.status == 403:
            # Read-only tenant grant — expected until Mail.ReadWrite lands.
            return jsonify({"success": True, "saved": "local", "reason": "read_only"})
        logger.warning("save-draft failed: %s", e)
        return jsonify({"success": False, "error": str(e)}), e.status
    logger.info("Draft saved to Outlook for %s by %s", message_id, _user_email())
    return jsonify({"success": True, "saved": "outlook", "draft": result})


@bp.route("/api/send-reply", methods=["POST"])
def send_reply_route():
    """Send a reviewed reply. THE ONLY SEND PATH. Invoked solely by an explicit,
    confirmed user action in the composer — never automatically, never from AI
    output. Sends exactly the text supplied; performs no analysis on it."""
    if not _live_active():
        return jsonify({"success": False, "mode": "mock", "error": "live mode off"}), 409
    body = request.get_json(silent=True) or {}
    message_id = body.get("id")
    text = (body.get("text") or "").strip()
    if not message_id or not text:
        return jsonify({"success": False, "error": "missing id or text"}), 400
    token = _graph_token()
    try:
        graph.send_reply(token, message_id, text)
    except graph.GraphError as e:
        logger.warning("send-reply failed for %s: %s", message_id, e)
        return jsonify({"success": False, "error": str(e)}), e.status
    logger.info("Reply SENT for %s by %s", message_id, _user_email())
    return jsonify({"success": True, "sent": True})
