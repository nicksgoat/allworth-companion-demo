"""Flask Blueprint for Jarvis — mount at /jarvis.

Equivalent of the FastAPI ``app.py`` from the standalone jarvis_bot project,
rewritten for Flask. All routes live under the blueprint's ``url_prefix``,
so the web UI is reached at ``/jarvis/`` and the JSON API at ``/jarvis/api/...``.
"""

from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path

import markdown as md
from flask import (
    Blueprint,
    abort,
    jsonify,
    make_response,
    render_template,
    request,
    send_file,
)

from jarvis import handler, storage
from jarvis.knowledge_loader import reload_resources

logger = logging.getLogger(__name__)

# Flask auto-finds templates/ and static/ relative to this file.
bp = Blueprint(
    "jarvis",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)

_LOGO_PATH = Path(__file__).parent / "static" / "logo.png"


# ── Pages ─────────────────────────────────────────────────────────────────


@bp.get("/")
def index():
    """Serve the SPA shell. Jinja injects base_url so fetch() calls hit /jarvis/api/..."""
    return render_template("index.html", base_url="/jarvis")


@bp.get("/logo.png")
def logo():
    if not _LOGO_PATH.exists():
        # Not fatal — UI hides the <img> if it 404s.
        abort(404)
    return send_file(_LOGO_PATH, mimetype="image/png")


# ── JSON API ──────────────────────────────────────────────────────────────


@bp.get("/api/search")
def api_search():
    q = request.args.get("q", "")
    result = handler.search(q)
    if "error" in result:
        return jsonify(result), (404 if q else 400)
    result["body_html"] = md.markdown(result["body"], extensions=["tables"])
    return jsonify(result)


@bp.get("/api/search/all")
def api_search_all():
    q = request.args.get("q", "")
    matches = handler.search_all(q)
    rendered = [
        {**m, "snippet_html": md.markdown(m["snippet"], extensions=["tables"])}
        for m in matches
    ]
    return jsonify({"query": q, "matches": rendered})


@bp.get("/api/docs")
def api_list_docs():
    payload = handler.list_docs()
    payload["categories"] = handler.known_categories()
    return jsonify(payload)


@bp.get("/api/docs/<key>")
def api_get_doc(key):
    doc = handler.get_doc(key)
    if not doc:
        abort(404, description="doc not found")
    doc["content_html"] = md.markdown(doc["content"], extensions=["tables", "fenced_code"])
    doc["last_edit"] = storage.last_edit_for_key(key)
    return jsonify(doc)


@bp.put("/api/docs/<key>")
def api_put_doc(key):
    body = request.get_json(silent=True) or {}
    user = storage.user_from_headers(request.headers)
    try:
        data = storage.write_doc(
            key,
            name=body.get("name", ""),
            description=body.get("description", ""),
            keywords=body.get("keywords", []) or [],
            content=body.get("content", ""),
            category=body.get("category") or None,
            user=user,
            summary=body.get("summary"),
        )
    except ValueError as e:
        return jsonify({"detail": str(e)}), 400
    reload_resources()
    handler.bump_reload_marker()
    return jsonify({"key": key, "user": user, "data": data})


@bp.delete("/api/docs/<key>")
def api_delete_doc(key):
    user = storage.user_from_headers(request.headers)
    summary = request.args.get("summary", "")
    try:
        ok = storage.delete_doc(key, user=user, summary=summary)
    except ValueError as e:
        return jsonify({"detail": str(e)}), 400
    if not ok:
        abort(404, description="doc not found")
    reload_resources()
    handler.bump_reload_marker()
    return jsonify({"deleted": key, "user": user})


@bp.get("/api/docs/<key>/history")
def api_doc_history(key):
    return jsonify({"key": key, "history": storage.history_for_key(key)})


@bp.get("/api/history")
def api_global_history():
    return jsonify({"history": storage.global_history()})


@bp.get("/api/docs/<key>/history/<ts>/diff")
def api_doc_diff(key, ts):
    try:
        return jsonify(storage.diff_for_event(key, ts))
    except ValueError as e:
        return jsonify({"detail": str(e)}), 404


@bp.post("/api/docs/<key>/restore")
def api_restore_doc(key):
    body = request.get_json(silent=True) or {}
    ts = body.get("ts")
    if not ts:
        return jsonify({"detail": "ts is required"}), 400
    user = storage.user_from_headers(request.headers)
    try:
        data = storage.restore_doc(key, ts, user=user)
    except ValueError as e:
        return jsonify({"detail": str(e)}), 400
    reload_resources()
    handler.bump_reload_marker()
    return jsonify({"restored": key, "ts": ts, "user": user, "data": data})


@bp.get("/api/me")
def api_me():
    return jsonify({"user": storage.user_from_headers(request.headers)})


@bp.post("/api/admin/reload")
def api_admin_reload():
    """Force an immediate reload. Auth via JARVIS_ADMIN_TOKEN env var + X-Admin-Token header."""
    expected = os.environ.get("JARVIS_ADMIN_TOKEN", "")
    if not expected:
        return jsonify({"detail": "admin reload disabled (no token configured)"}), 403
    provided = request.headers.get("X-Admin-Token", "")
    if not hmac.compare_digest(provided, expected):
        return jsonify({"detail": "invalid admin token"}), 401
    count = handler.force_reload()
    return jsonify({"reloaded": count})


@bp.get("/api/health")
def api_health():
    return jsonify({"status": "ok", "resources": len(handler.RESOURCES) if hasattr(handler, "RESOURCES") else None})
