"""Flask Blueprint for the Data Catalog — mount at /catalog.

Web UI at ``/catalog/`` and JSON API at ``/catalog/api/...``. Mirrors the Jarvis
blueprint conventions (self-contained SPA served by Flask).
"""

from __future__ import annotations

import hmac
import logging
import os
from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template, request

from catalog import handler, storage
from catalog.loader import reload as reload_catalog

# Metric editing writes to the Jarvis knowledge YAMLs (single source of truth,
# also read by the MCP server). Defensive: metrics surface degrades if absent.
try:
    import markdown as _md
    from jarvis import storage as jarvis_storage
    from jarvis.knowledge_loader import reload_resources as reload_jarvis
    _METRICS_OK = True
except Exception:  # pragma: no cover - defensive
    _md = None  # type: ignore
    jarvis_storage = None  # type: ignore
    reload_jarvis = None  # type: ignore
    _METRICS_OK = False

logger = logging.getLogger(__name__)

bp = Blueprint(
    "catalog",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/static",
)


# ── Pages ─────────────────────────────────────────────────────────────────

@bp.get("/")
def index():
    # Cache-bust static assets so a redeploy always loads the latest app.js/css
    # (Flask serves them without a content hash, so browsers cache aggressively).
    static_dir = Path(__file__).parent / "static"
    version = 0
    for name in ("app.js", "styles.css"):
        f = static_dir / name
        if f.exists():
            version = max(version, int(f.stat().st_mtime))
    return render_template("catalog.html", base_url="/catalog", asset_version=version)


# ── JSON API ──────────────────────────────────────────────────────────────

@bp.get("/api/tables")
def api_tables():
    pii_arg = request.args.get("pii")
    payload = handler.list_tables(
        q=request.args.get("q", ""),
        schema=request.args.get("schema", ""),
        domain=request.args.get("domain", ""),
        kind=request.args.get("kind", ""),
        pii=True if pii_arg in ("1", "true", "yes") else None,
        include_deprecated=request.args.get("deprecated", "1") not in ("0", "false", "no"),
    )
    return jsonify(payload)


@bp.get("/api/tables/<slug>")
def api_table(slug):
    tbl = handler.get_table(slug)
    if not tbl:
        abort(404, description="table not found")
    tbl["last_history"] = storage.history_for_id(slug, limit=1)
    return jsonify(tbl)


@bp.get("/api/graph")
def api_graph():
    return jsonify(handler.graph(worksheet=request.args.get("worksheet", "")))


@bp.get("/api/worksheets")
def api_worksheets():
    return jsonify({"worksheets": handler.worksheets()})


@bp.get("/api/columns/<column>/where-used")
def api_where_used(column):
    return jsonify(handler.where_used(column))


@bp.get("/api/columns")
def api_columns():
    try:
        limit = int(request.args.get("limit", 500))
    except ValueError:
        limit = 500
    return jsonify(
        handler.list_columns(
            q=request.args.get("q", ""),
            kind=request.args.get("kind", ""),
            limit=limit,
        )
    )


@bp.get("/api/column")
def api_column_detail():
    name = request.args.get("name", "")
    detail = handler.column_detail(name)
    if not detail:
        abort(404, description="column not found")
    return jsonify(detail)


@bp.get("/api/business-logic")
def api_business_logic():
    return jsonify({"functions": handler.list_business_logic(q=request.args.get("q", ""))})


@bp.put("/api/business-logic/<name>")
def api_business_logic_put(name):
    body = request.get_json(silent=True) or {}
    user = storage.user_from_headers(request.headers)
    try:
        storage.write_function_plain_english(
            name,
            user=user,
            plain_english=body.get("plain_english", ""),
            summary=body.get("summary"),
        )
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    reload_catalog()
    handler.bump_reload_marker()
    return jsonify({"name": name, "user": user})


@bp.get("/api/glossary")
def api_glossary():
    return jsonify({"glossary": handler.glossary()})


@bp.get("/api/sources")
def api_sources():
    return jsonify(handler.sources())


@bp.get("/api/facets")
def api_facets():
    return jsonify(handler.facets())


# ── Metrics (Jarvis encyclopedia, cross-linked to tables) ───────────────────

@bp.get("/api/metrics")
def api_metrics():
    return jsonify(handler.list_metrics())


@bp.get("/api/metrics/search")
def api_metrics_search():
    q = request.args.get("q", "")
    return jsonify({"query": q, "matches": handler.search_metrics(q)})


@bp.get("/api/metrics/<key>")
def api_metric(key):
    doc = handler.get_metric(key)
    if not doc:
        abort(404, description="metric not found")
    if _md is not None:
        doc["content_html"] = _md.markdown(
            doc.get("content", ""), extensions=["tables", "fenced_code"]
        )
    if _METRICS_OK:
        doc["last_edit"] = (jarvis_storage.history_for_key(key, limit=1) or [None])[0]
    return jsonify(doc)


@bp.put("/api/metrics/<key>")
def api_metric_put(key):
    if not _METRICS_OK:
        abort(503, description="metrics editing unavailable")
    body = request.get_json(silent=True) or {}
    user = jarvis_storage.user_from_headers(request.headers)
    try:
        data = jarvis_storage.write_doc(
            key,
            name=body.get("name", ""),
            description=body.get("description", ""),
            keywords=body.get("keywords", []) or [],
            content=body.get("content", ""),
            category=body.get("category") or None,
            related_tables=body.get("related_tables") or None,
            related_columns=body.get("related_columns") or None,
            user=user,
            summary=body.get("summary"),
        )
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    reload_jarvis()
    return jsonify({"key": key, "user": user, "data": data})


@bp.delete("/api/metrics/<key>")
def api_metric_delete(key):
    if not _METRICS_OK:
        abort(503, description="metrics editing unavailable")
    user = jarvis_storage.user_from_headers(request.headers)
    summary = request.args.get("summary", "")
    ok = jarvis_storage.delete_doc(key, user=user, summary=summary)
    if not ok:
        abort(404, description="metric not found")
    reload_jarvis()
    return jsonify({"deleted": key, "user": user})


@bp.get("/api/metrics/<key>/history")
def api_metric_history(key):
    if not _METRICS_OK:
        return jsonify({"key": key, "history": []})
    return jsonify({"key": key, "history": jarvis_storage.history_for_key(key)})


# ── Curation (write) ───────────────────────────────────────────────────────

@bp.put("/api/tables/<slug>/curation")
def api_curate(slug):
    body = request.get_json(silent=True) or {}
    user = storage.user_from_headers(request.headers)
    try:
        overlay = storage.write_curation(
            slug,
            user=user,
            description=body.get("description"),
            notes=body.get("notes"),
            columns=body.get("columns"),
            deprecated=body.get("deprecated"),
            summary=body.get("summary"),
        )
    except ValueError as exc:
        return jsonify({"detail": str(exc)}), 400
    reload_catalog()
    handler.bump_reload_marker()
    return jsonify({"id": slug, "user": user, "overlay": overlay})


@bp.get("/api/tables/<slug>/history")
def api_history(slug):
    return jsonify({"id": slug, "history": storage.history_for_id(slug)})


@bp.get("/api/history")
def api_global_history():
    return jsonify({"history": storage.global_history()})


@bp.get("/api/me")
def api_me():
    return jsonify({"user": storage.user_from_headers(request.headers)})


@bp.post("/api/admin/reload")
def api_reload():
    token = os.environ.get("CATALOG_ADMIN_TOKEN") or os.environ.get("JARVIS_ADMIN_TOKEN")
    if token:
        sent = request.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(sent, token):
            abort(403, description="bad admin token")
    count = reload_catalog()
    handler.bump_reload_marker()
    return jsonify({"reloaded": count})
