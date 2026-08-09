"""Plan-health domain service shared by Avantos and advisor workspaces."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from planengine.goals import evaluate_goals
from planning.services.planning_store import store
from planning.services.projections import projection_service
from planning.services.publication import publication_registry


def _health_score(projection, goals: list[dict]) -> int:
    components = [1.0 if projection.first_shortfall_year is None else 0.35]
    if goals:
        components.append(sum(1 for goal in goals if goal.get("status") == "funded") / len(goals))
    return round(sum(components) / len(components) * 100)


def household_health_row(household: dict) -> dict | None:
    household_id = UUID(household["id"])
    try:
        facts = store.get_facts(household_id)
    except KeyError:
        return None
    projection = projection_service.project(facts)
    goals = evaluate_goals(facts, projection)
    alerts = store.list_portal(household_id, "alerts")
    tasks = store.list_portal(household_id, "tasks")
    open_alerts = [row for row in alerts if str(row.get("payload", {}).get("status", "open")).lower() not in {"resolved", "closed", "dismissed"}]
    open_tasks = [row for row in tasks if str(row.get("payload", {}).get("status", "open")).lower() not in {"done", "completed", "closed"}]
    drift_alerts = [row for row in open_alerts if row.get("payload", {}).get("kind") == "plan_drift"]
    publications = publication_registry.for_household(household_id)
    active_publication = next((publication for publication in publications if publication.status == "published"), None)
    total_assets = sum((account.value for account in facts.accounts if not account.exclude_from_planning), Decimal("0"))
    score = _health_score(projection, goals)
    return {
        "household_id": str(household_id), "name": facts.name,
        "source": facts.metadata.get("source", "planning"),
        "source_id": facts.metadata.get("source_id"),
        "avhhid": facts.metadata.get("household_avhhid"),
        "advisor_id": facts.metadata.get("advisor_id"),
        "crm_lead_id": facts.metadata.get("crm_lead_id"),
        "total_assets": str(total_assets),
        "ending_net_worth": str(projection.ending_net_worth),
        "first_shortfall_year": projection.first_shortfall_year,
        "health_score": score,
        "health_band": "healthy" if score >= 80 else "watch" if score >= 60 else "at_risk",
        "goals_total": len(goals),
        "goals_funded": sum(1 for goal in goals if goal.get("status") == "funded"),
        "open_alerts": len(open_alerts), "open_tasks": len(open_tasks),
        "drift_flagged": bool(drift_alerts),
        "last_actuals_sync": facts.metadata.get("last_actuals_sync"),
        "publication_status": active_publication.status if active_publication else ("withdrawn" if any(publication.status == "withdrawn" for publication in publications) else "unpublished"),
        "published_at": active_publication.published_at if active_publication else None,
        "data_quality_warnings": len(facts.metadata.get("data_quality_warnings", [])),
    }
