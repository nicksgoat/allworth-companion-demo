"""Connected workspace orchestration independent of Flask routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from avantos.service import household_health_row
from planning.services.publication import publication_registry
from workspace.errors import HouseholdIdentifierConflict
from workspace.repositories import CrmWorkspaceRepository, PlanningWorkspaceRepository


class WorkspaceService:
    def __init__(self, crm: CrmWorkspaceRepository | None = None,
                 planning: PlanningWorkspaceRepository | None = None):
        self.crm = crm or CrmWorkspaceRepository()
        self.planning = planning or PlanningWorkspaceRepository()

    def advisor(self, email: str, override: str | None = None) -> dict[str, Any] | None:
        return self.crm.advisor(advisor_id=override) if override else self.crm.advisor(email=email)

    @staticmethod
    def _facts_ids(facts) -> dict[str, str | None]:
        metadata = facts.metadata
        return {
            "lead_id": str(metadata.get("crm_lead_id") or "") or None,
            "hhid": str(metadata.get("source_id") or "") or None,
            "avhhid": str(metadata.get("household_avhhid") or "") or None,
        }

    @staticmethod
    def _ensure_consistent(facts, *, lead_id: str | None, hhid: str | None,
                           avhhid: str | None) -> None:
        stored = WorkspaceService._facts_ids(facts)
        requested = {"lead_id": lead_id, "hhid": hhid, "avhhid": avhhid}
        conflicts = [key for key, value in requested.items() if value and stored[key] and value != stored[key]]
        if conflicts:
            raise HouseholdIdentifierConflict("Household identifiers refer to different records", detail=", ".join(conflicts))

    def household_context(self, *, planning_id: str | None = None,
                          lead_id: str | None = None, hhid: str | None = None,
                          avhhid: str | None = None) -> dict[str, Any] | None:
        facts = self.planning.find(planning_id=planning_id) if planning_id else None
        if facts:
            self._ensure_consistent(facts, lead_id=lead_id, hhid=hhid, avhhid=avhhid)
            stored = self._facts_ids(facts)
            lead_id, hhid, avhhid = lead_id or stored["lead_id"], hhid or stored["hhid"], avhhid or stored["avhhid"]
        warehouse = self.crm.household(lead_id=lead_id, hhid=hhid, avhhid=avhhid)
        if not facts and warehouse:
            facts = self.planning.find(lead_id=warehouse["crm_lead_id"],
                                       hhid=warehouse["salesforce_household_id"],
                                       avhhid=warehouse["avhhid"])
        return self.context_payload(facts, warehouse)

    @staticmethod
    def context_payload(facts, warehouse: dict[str, Any] | None) -> dict[str, Any] | None:
        if not facts and not warehouse:
            return None
        metadata = facts.metadata if facts else {}
        publications = publication_registry.for_household(facts.household_id) if facts else []
        published = next((publication for publication in publications if publication.status == "published"), None)
        assets = sum((account.value for account in facts.accounts if not account.exclude_from_planning), Decimal("0")) if facts else Decimal("0")
        warnings = len(metadata.get("data_quality_warnings", []))
        sync = metadata.get("last_actuals_sync")
        warehouse_aum = warehouse.get("aum") if warehouse else None
        return {
            "planning_household_id": str(facts.household_id) if facts else None,
            "crm_lead_id": (warehouse or {}).get("crm_lead_id") or metadata.get("crm_lead_id"),
            "salesforce_household_id": (warehouse or {}).get("salesforce_household_id") or metadata.get("source_id"),
            "avhhid": (warehouse or {}).get("avhhid") or metadata.get("household_avhhid"),
            "name": facts.name if facts else (warehouse or {}).get("name"),
            "advisor_id": (warehouse or {}).get("advisor_id") or metadata.get("advisor_id"),
            "advisor_name": (warehouse or {}).get("advisor_name"),
            "aum": float(assets) if warehouse_aum is None else warehouse_aum,
            "plan_status": "published" if published else "draft" if facts else "not_started",
            "last_actuals_sync": sync,
            "freshness": "unknown" if not sync else "available",
            "data_quality_warnings": warnings,
            "data_quality_state": "warning" if warnings else "healthy",
        }

    @staticmethod
    def _warehouse_for_facts(facts, by_lead, by_hhid, by_avhhid):
        ids = WorkspaceService._facts_ids(facts)
        return by_lead.get(ids["lead_id"]) or by_hhid.get(ids["hhid"]) or by_avhhid.get(ids["avhhid"])

    def advisor_home(self, advisor_id: str) -> dict[str, Any]:
        warehouse_book = self.crm.advisor_book(advisor_id)
        by_lead = {row["crm_lead_id"]: row for row in warehouse_book if row["crm_lead_id"]}
        by_hhid = {row["salesforce_household_id"]: row for row in warehouse_book if row["salesforce_household_id"]}
        by_avhhid = {row["avhhid"]: row for row in warehouse_book if row["avhhid"]}

        planning_facts = {facts.household_id: facts for facts in self.planning.for_advisor(advisor_id)}
        for relationship in warehouse_book:
            facts = self.planning.find(lead_id=relationship["crm_lead_id"],
                                       hhid=relationship["salesforce_household_id"],
                                       avhhid=relationship["avhhid"])
            if facts:
                planning_facts[facts.household_id] = facts

        joined_relationships: set[str] = set()
        rows: list[dict[str, Any]] = []
        for facts in planning_facts.values():
            warehouse = self._warehouse_for_facts(facts, by_lead, by_hhid, by_avhhid)
            if warehouse:
                joined_relationships.add(warehouse["crm_lead_id"] or warehouse["salesforce_household_id"] or warehouse["avhhid"])
            health = household_health_row({"id": str(facts.household_id)})
            context = self.context_payload(facts, warehouse)
            if health and context:
                rows.append({**health, "context": context})

        for warehouse in warehouse_book:
            relationship_key = warehouse["crm_lead_id"] or warehouse["salesforce_household_id"] or warehouse["avhhid"]
            if relationship_key in joined_relationships:
                continue
            context = self.context_payload(None, warehouse)
            rows.append({
                "household_id": relationship_key, "name": warehouse["name"],
                "source": "relationship", "source_id": warehouse["salesforce_household_id"],
                "avhhid": warehouse["avhhid"], "advisor_id": warehouse["advisor_id"],
                "crm_lead_id": warehouse["crm_lead_id"], "total_assets": str(warehouse["aum"]),
                "ending_net_worth": "0", "first_shortfall_year": None,
                "health_score": 0, "health_band": "watch", "goals_total": 0,
                "goals_funded": 0, "open_alerts": 0, "open_tasks": 0,
                "drift_flagged": False, "last_actuals_sync": None,
                "publication_status": "unpublished", "published_at": None,
                "data_quality_warnings": 0, "context": context,
            })

        rank = {"at_risk": 0, "watch": 1, "healthy": 2}
        rows.sort(key=lambda row: (rank.get(row["health_band"], 3),
                                   -(row["open_alerts"] + row["open_tasks"]), row["name"].lower()))
        total_assets = sum(Decimal(row["total_assets"]) for row in rows) if rows else Decimal("0")
        return {
            "summary": {
                "households": len(rows), "total_assets": str(total_assets),
                "at_risk": sum(row["health_band"] == "at_risk" for row in rows),
                "needs_attention": sum(bool(row["open_alerts"] or row["open_tasks"] or row["drift_flagged"] or row["publication_status"] != "published") for row in rows),
                "unpublished": sum(row["publication_status"] != "published" for row in rows),
            },
            "households": rows,
        }


workspace_service = WorkspaceService()
