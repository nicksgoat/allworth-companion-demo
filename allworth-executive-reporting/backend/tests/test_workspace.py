"""Exact workspace household-context and service-boundary tests."""

from __future__ import annotations

from uuid import UUID

import pytest
from flask import Flask

import workspace.routes as workspace_routes
import workspace.repositories as workspace_repositories
from planning.services.planning_store import store
from workspace.errors import HouseholdIdentifierConflict
from workspace.repositories import PlanningWorkspaceRepository
from workspace.service import WorkspaceService


RELATIONSHIP = {
    "crm_lead_id": "lead-1", "salesforce_household_id": "hhid-1",
    "avhhid": "av-1", "advisor_id": "advisor-1", "advisor_name": "Morgan Lee",
    "aum": 1_250_000, "name": "Duplicate Family",
}


class FakeCrmRepository:
    def advisor(self, *, email=None, advisor_id=None):
        if advisor_id == "advisor-1" or email == "advisor@example.com":
            return {"advisor_id": "advisor-1", "name": "Morgan Lee", "email": "advisor@example.com", "resolution": "override" if advisor_id else "email"}
        return None

    def household(self, *, lead_id=None, hhid=None, avhhid=None):
        supplied = {value for value in (lead_id, hhid, avhhid) if value}
        exact = {RELATIONSHIP["crm_lead_id"], RELATIONSHIP["salesforce_household_id"], RELATIONSHIP["avhhid"]}
        return dict(RELATIONSHIP) if supplied and supplied <= exact else None

    def advisor_book(self, advisor_id):
        return [dict(RELATIONSHIP)] if advisor_id == "advisor-1" else []


@pytest.fixture()
def service():
    return WorkspaceService(FakeCrmRepository(), PlanningWorkspaceRepository())


@pytest.fixture()
def client(monkeypatch, service):
    monkeypatch.setattr(workspace_routes, "workspace_service", service)
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(workspace_routes.bp, url_prefix="/api/workspace")
    return app.test_client()


@pytest.fixture()
def connected_plan():
    facts, _ = store.create_household({
        "name": "Duplicate Family",
        "people": [{"role": "client", "date_of_birth": "1960-01-01"}],
        "accounts": [{"name": "Portfolio", "kind": "taxable", "value": 1250000}],
        "assumptions": {},
        "metadata": {"source": "datawarehouse", "source_id": "hhid-1", "household_avhhid": "av-1", "crm_lead_id": "lead-1", "advisor_id": "advisor-1"},
    }, "test")
    yield facts
    store.delete_household(UUID(str(facts.household_id)), "test", "cleanup")


def test_resolves_by_exact_lead_id(client, connected_plan):
    body = client.get("/api/workspace/households/resolve?lead_id=lead-1").get_json()
    assert body["household"]["planning_household_id"] == str(connected_plan.household_id)
    assert body["household"]["crm_lead_id"] == "lead-1"


def test_does_not_fuzzy_match_name(client, connected_plan):
    response = client.get("/api/workspace/households/resolve?lead_id=different")
    assert response.status_code == 404


def test_resolves_planning_id_and_enriches_relationship(client, connected_plan):
    body = client.get(f"/api/workspace/households/resolve?planning_id={connected_plan.household_id}").get_json()
    assert body["household"]["salesforce_household_id"] == "hhid-1"
    assert body["household"]["advisor_id"] == "advisor-1"


def test_conflicting_exact_ids_are_rejected(client, connected_plan):
    response = client.get(f"/api/workspace/households/resolve?planning_id={connected_plan.household_id}&lead_id=other")
    assert response.status_code == 409
    assert response.get_json()["code"] == "household_identifier_conflict"


def test_crm_only_relationship_has_clear_plan_state(client):
    body = client.get("/api/workspace/households/resolve?lead_id=lead-1").get_json()
    assert body["household"]["planning_household_id"] is None
    assert body["household"]["plan_status"] == "not_started"


def test_invalid_planning_id_is_not_found(client):
    assert client.get("/api/workspace/households/resolve?planning_id=not-a-uuid").status_code == 404


def test_planning_join_accepts_partial_exact_source_metadata(monkeypatch):
    class PartialStore:
        def find_facts(self, **lookup):
            if lookup == {"crm_lead_id": "lead-1"}:
                return type("Facts", (), {"household_id": UUID("00000000-0000-0000-0000-000000000001")})()
            return None

    monkeypatch.setattr(workspace_repositories, "planning_store", PartialStore())
    resolved = PlanningWorkspaceRepository().find(lead_id="lead-1", hhid="hhid-not-indexed", avhhid="av-not-indexed")
    assert str(resolved.household_id) == "00000000-0000-0000-0000-000000000001"


def test_planning_join_rejects_conflicting_exact_sources(monkeypatch):
    class ConflictingStore:
        def find_facts(self, **lookup):
            household_id = (
                "00000000-0000-0000-0000-000000000001"
                if "crm_lead_id" in lookup
                else "00000000-0000-0000-0000-000000000002"
            )
            return type("Facts", (), {"household_id": UUID(household_id)})()

    monkeypatch.setattr(workspace_repositories, "planning_store", ConflictingStore())
    with pytest.raises(HouseholdIdentifierConflict, match="different households"):
        PlanningWorkspaceRepository().find(lead_id="lead-1", hhid="hhid-2")
