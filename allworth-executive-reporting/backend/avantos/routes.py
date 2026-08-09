"""Avantos cockpit routes — advisor book-of-business aggregation."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from flask import Blueprint, jsonify, request

from planengine.goals import evaluate_goals
from planning.services.planning_store import store
from planning.services.projections import projection_service
from planning.services.publication import publication_registry

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


def _health_score(projection, goals: list[dict]) -> int:
    """Composite plan health matching the frontend PlanHealthCard formula
    (deterministic components only; Monte Carlo is surfaced separately)."""
    components = [1.0 if projection.first_shortfall_year is None else 0.35]
    if goals:
        funded = sum(1 for goal in goals if goal.get("status") == "funded")
        components.append(funded / len(goals))
    return round(sum(components) / len(components) * 100)


def _household_row(household: dict) -> dict | None:
    household_id = UUID(household["id"])
    try:
        facts = store.get_facts(household_id)
    except KeyError:
        return None
    projection = projection_service.project(facts)
    goals = evaluate_goals(facts, projection)
    alerts = store.list_portal(household_id, "alerts")
    tasks = store.list_portal(household_id, "tasks")
    open_alerts = [row for row in alerts
                   if str(row.get("payload", {}).get("status", "open")).lower()
                   not in {"resolved", "closed", "dismissed"}]
    open_tasks = [row for row in tasks
                  if str(row.get("payload", {}).get("status", "open")).lower()
                  not in {"done", "completed", "closed"}]
    drift_alerts = [row for row in open_alerts
                    if row.get("payload", {}).get("kind") == "plan_drift"]
    publications = publication_registry.for_household(household_id)
    active_publication = next((p for p in publications if p.status == "published"), None)
    total_assets = sum((a.value for a in facts.accounts
                        if not a.exclude_from_planning), D("0"))
    score = _health_score(projection, goals)
    return {
        "household_id": str(household_id),
        "name": facts.name,
        "source": facts.metadata.get("source", "planning"),
        "total_assets": str(total_assets),
        "ending_net_worth": str(projection.ending_net_worth),
        "first_shortfall_year": projection.first_shortfall_year,
        "health_score": score,
        "health_band": "healthy" if score >= 80 else "watch" if score >= 60 else "at_risk",
        "goals_total": len(goals),
        "goals_funded": sum(1 for goal in goals if goal.get("status") == "funded"),
        "open_alerts": len(open_alerts),
        "open_tasks": len(open_tasks),
        "drift_flagged": bool(drift_alerts),
        "last_actuals_sync": facts.metadata.get("last_actuals_sync"),
        "publication_status": active_publication.status if active_publication else
                              ("withdrawn" if any(p.status == "withdrawn" for p in publications)
                               else "unpublished"),
        "published_at": active_publication.published_at if active_publication else None,
        "data_quality_warnings": len(facts.metadata.get("data_quality_warnings", [])),
    }


@bp.get("/cockpit")
def cockpit():
    """Book-of-business rollup plus one actionable row per household."""
    if _is_client():
        return jsonify(detail="resource not found"), 404
    rows = []
    for household in store.list_households():
        row = _household_row(household)
        if row is not None:
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
