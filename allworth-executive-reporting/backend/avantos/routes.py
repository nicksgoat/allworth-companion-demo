"""Avantos cockpit routes — advisor book-of-business aggregation."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from flask import Blueprint, jsonify, request

from planning.services.planning_store import store
from avantos.service import household_health_row

bp = Blueprint("avantos", __name__)

D = Decimal


def _roles() -> set[str]:
    claims = request.environ.get("user.claims") or {}
    roles = claims.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    return {str(role).lower() for role in roles}


def _is_client() -> bool:
    return bool(_roles() & {"client", "portal_client", "planengine.client"})


_household_row = household_health_row


@bp.get("/cockpit")
def cockpit():
    """Book-of-business rollup plus one actionable row per household."""
    if _is_client():
        return jsonify(detail="resource not found"), 404
    advisor_id = request.args.get("advisor_id", "").strip()
    rows = []
    for household in store.list_households():
        row = _household_row(household)
        if row is not None and (not advisor_id or row.get("advisor_id") == advisor_id):
            rows.append(row)
    # Highest-need households first: at-risk, then drift, then open work.
    band_rank = {"at_risk": 0, "watch": 1, "healthy": 2}
    rows.sort(key=lambda row: (band_rank[row["health_band"]],
                               not row["drift_flagged"],
                               -(row["open_alerts"] + row["open_tasks"]),
                               row["name"].lower()))
    total_assets = sum(D(row["total_assets"]) for row in rows) if rows else D("0")
    summary = {
        "households": len(rows),
        "total_assets": str(total_assets),
        "at_risk": sum(1 for row in rows if row["health_band"] == "at_risk"),
        "watch": sum(1 for row in rows if row["health_band"] == "watch"),
        "healthy": sum(1 for row in rows if row["health_band"] == "healthy"),
        "drift_flagged": sum(1 for row in rows if row["drift_flagged"]),
        "unpublished": sum(1 for row in rows
                           if row["publication_status"] == "unpublished"),
        "open_alerts": sum(row["open_alerts"] for row in rows),
        "open_tasks": sum(row["open_tasks"] for row in rows),
    }
    return jsonify(summary=summary, households=rows)


@bp.get("/health")
def health():
    return jsonify(status="ok", module="avantos")
