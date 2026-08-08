"""Executive Report routes — combined flows + NCNM forecast + AI summary.

READ-ONLY against Synapse. The full payload (flows metrics, NCNM forecast, and the
GPT-4.1 executive summary) is built ONCE per data refresh and stored in a single
global cache entry with a daily TTL. Every viewer of the same refresh therefore
receives byte-identical data AND commentary. A ``POST /api/refresh`` regenerates
the payload globally (for everyone), not per-user.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from threading import Lock
from typing import Any

from flask import Blueprint, jsonify, request, send_from_directory

from executive_report import flows as flows_mod
from executive_report import highlights as highlights_mod
from executive_report import ncnm_model
from executive_report import summary as summary_mod

bp = Blueprint("executive_report", __name__, template_folder="templates")


# ─── JSON safety ─────────────────────────────────────────────────────────────

def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


# ─── DB + global daily cache ─────────────────────────────────────────────────

def _get_db_connection():
    from app import get_database_connection
    return get_database_connection()


_CACHE_TTL_SECONDS = 24 * 60 * 60  # daily — the warehouse refreshes once per day
_cache: dict[str, tuple[float, Any]] = {}
_build_lock = Lock()


def _build_payload() -> dict:
    """Build the full report payload (flows + NCNM + AI summary). Called once
    per refresh under ``_build_lock`` so concurrent first-hits don't duplicate
    the Synapse round-trips or the GPT-4.1 call."""
    conn = _get_db_connection()
    flows_data = flows_mod.compute_flows(conn)
    ncnm_data = ncnm_model.compute_forecast(conn, months_n=1)
    try:
        ncnm_data["closes_by_advisor"] = ncnm_model.compute_closes_by_advisor(conn)
    except Exception:  # pragma: no cover - defensive
        ncnm_data["closes_by_advisor"] = []
    summary = summary_mod.generate_summary(flows_data, ncnm_data)
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "flows": flows_data,
        "ncnm": ncnm_data,
        "summary": summary,
        "highlights": highlights_mod.build_highlights(flows_data, ncnm_data),
    }
    return _json_safe(payload)


def _get_report(force: bool = False) -> dict:
    now = time.time()
    if not force:
        entry = _cache.get("report")
        if entry and (now - entry[0]) < _CACHE_TTL_SECONDS:
            return entry[1]
    with _build_lock:
        # Re-check inside the lock: another request may have just built it.
        entry = _cache.get("report")
        if not force and entry and (time.time() - entry[0]) < _CACHE_TTL_SECONDS:
            return entry[1]
        payload = _build_payload()
        _cache["report"] = (time.time(), payload)
        return payload


# ─── Routes ──────────────────────────────────────────────────────────────────

@bp.route("/")
def index():
    """Serve the Executive Report SPA (falls back to the frontend build)."""
    tmpl = Path(__file__).parent / "templates" / "index.html"
    if tmpl.exists():
        return send_from_directory(str(tmpl.parent), "index.html")
    return jsonify({"success": True, "message": "Executive Report API. Use /executive-report/api/report."})


@bp.route("/api/report", methods=["GET"])
def get_report():
    """Return the full cached report payload (builds it on first hit)."""
    try:
        data = _get_report(force=False)
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/refresh", methods=["POST"])
def refresh_report():
    """Force a global rebuild (new data + new AI summary) for all viewers."""
    try:
        data = _get_report(force=True)
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/health", methods=["GET"])
def health():
    entry = _cache.get("report")
    return jsonify({
        "success": True,
        "cached": entry is not None,
        "cache_age_seconds": (time.time() - entry[0]) if entry else None,
    })
