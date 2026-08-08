"""mailer HTTP API — lets pipelines and other services send email.

Mounted at /mailer. Gated by the same global JWT / Easy Auth middleware as every
other tool, so callers must present a valid Entra token. A Synapse pipeline
authenticates with its workspace **managed identity** (Web activity →
Authentication: Managed Identity, Resource = this app's client id); no user, no
API key, no change to the auth layer required.

The send itself runs **app-only** from a service mailbox (MAILER_FROM, or the
per-request 'mailbox'), so it never depends on a signed-in user's token — which
is exactly what an unattended pipeline needs.

    POST /mailer/api/send
      { "to": "a@x.com" | ["a@x.com", ...],
        "subject": "...", "body": "...",
        "cc": [...]?, "html": false?, "mailbox": "automations@allworthfinancial.com"? }

Requires APPLICATION Graph Mail.Send admin-consented on the app registration and
a MAILER_FROM (or per-request mailbox) the app is allowed to send as.
"""
from __future__ import annotations

import logging
import os

from flask import Blueprint, jsonify, request

import mailer
from mailer import events

logger = logging.getLogger(__name__)

bp = Blueprint("mailer", __name__)


def _caller() -> str:
    return request.environ.get("user.email") or "app-token"


@bp.route("/api/health")
def health():
    return jsonify({
        "success": True,
        "tool": "mailer",
        "from_configured": bool(os.getenv("MAILER_FROM")),
    })


@bp.route("/api/send", methods=["POST"])
def send():
    body = request.get_json(silent=True) or {}
    to = body.get("to")
    subject = body.get("subject")
    text = body.get("body")
    if not to or not subject or text is None:
        return jsonify({"success": False, "error": "to, subject, and body are required"}), 400
    try:
        mailer.send_email(
            to,
            subject,
            text,
            cc=body.get("cc"),
            html=bool(body.get("html")),
            mailbox=body.get("mailbox"),  # None → MAILER_FROM default (app-only)
        )
    except mailer.MailError as e:
        logger.warning("mailer send failed (caller=%s): %s", _caller(), e)
        return jsonify({"success": False, "error": str(e)}), e.status
    recipients = [to] if isinstance(to, str) else to
    logger.info("mailer sent to %s (subject=%r, caller=%s)", recipients, subject, _caller())
    return jsonify({"success": True, "sent": True})


@bp.route("/api/reply", methods=["POST"])
def reply():
    body = request.get_json(silent=True) or {}
    message_id = body.get("id")
    text = body.get("body")
    if not message_id or not text:
        return jsonify({"success": False, "error": "id and body are required"}), 400
    try:
        mailer.reply_to(message_id, text, mailbox=body.get("mailbox"))
    except mailer.MailError as e:
        logger.warning("mailer reply failed (caller=%s): %s", _caller(), e)
        return jsonify({"success": False, "error": str(e)}), e.status
    return jsonify({"success": True, "sent": True})


# --------------------------------------------------------------------------- #
# Event-driven inbound: 'an email triggers the pipeline'.
#   * Manage trigger rules (which mailbox + match → which pipeline URL).
#   * A scheduled, authenticated caller (e.g. a Synapse timer with managed
#     identity) hits /api/poll every few minutes to fan out new mail.
# --------------------------------------------------------------------------- #
@bp.route("/api/rules", methods=["GET"])
def list_rules():
    return jsonify({"success": True, "rules": events.list_rules()})


@bp.route("/api/rules", methods=["POST"])
def create_rule():
    body = request.get_json(silent=True) or {}
    mailbox = body.get("mailbox") or os.getenv("MAILER_FROM")
    target_url = body.get("target_url")
    if not mailbox or not target_url:
        return jsonify({"success": False, "error": "mailbox (or MAILER_FROM) and target_url are required"}), 400
    match = {
        k: v for k, v in {
            "from_contains": body.get("from_contains"),
            "subject_contains": body.get("subject_contains"),
        }.items() if v
    }
    rule = events.add_rule(mailbox, target_url, match)
    logger.info("mailer rule created %s → %s (caller=%s)", rule["id"], target_url, _caller())
    return jsonify({"success": True, "rule": rule})


@bp.route("/api/rules/<rule_id>", methods=["DELETE"])
def remove_rule(rule_id: str):
    ok = events.delete_rule(rule_id)
    return jsonify({"success": ok}), (200 if ok else 404)


@bp.route("/api/poll", methods=["POST"])
def poll():
    """Run one polling pass. Call on a schedule (every 2–5 min) from an
    authenticated timer (Synapse/ADF Web activity with managed identity)."""
    result = events.poll_once()
    return jsonify(result)
