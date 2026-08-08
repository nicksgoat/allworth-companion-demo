"""Tests for the Avantos advisor cockpit aggregation.

Run from the backend/ directory:

    python -m pytest tests/test_avantos.py -v
"""
from __future__ import annotations

import os
from uuid import UUID

import pytest

os.environ["AUTH_DISABLE"] = "1"

from avantos.routes import bp as avantos_bp
from planning.routes import bp as planning_bp
from planning.services.planning_store import store
from planning.services.publication import publication_registry


def household_payload(name: str, value: int, spending: int) -> dict:
    return {
        "name": name,
        "people": [{"role": "client", "date_of_birth": "1960-01-01",
                    "retirement_age": 65, "assumed_age_of_death": 90}],
        "accounts": [{"kind": "taxable", "name": "Brokerage", "value": value,
                      "growth_rate": "0.05"}],
        "expenses": [{"name": "Living", "kind": "living", "amount": spending,
                      "starts": {"kind": "immediately"},
                      "ends": {"kind": "client_death"}}],
        "assumptions": {"start_year": 2026},
    }


@pytest.fixture()
def client():
    from flask import Flask

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(planning_bp, url_prefix="/api/v1", name="planning_av")
    app.register_blueprint(avantos_bp, url_prefix="/api/avantos", name="avantos_test")
    return app.test_client()


@pytest.fixture()
def book(client):
    """Two households: one healthy, one guaranteed shortfall."""
    created = []
    for payload in (household_payload("Healthy HH", 5000000, 50000),
                    household_payload("AtRisk HH", 100000, 200000)):
        body = client.post("/api/v1/households", json=payload).get_json()
        created.append(body["household_id"])
    yield created
    for household_id in created:
        try:
            store.delete_household(UUID(household_id), "tests", "cleanup")
        except KeyError:
            pass
        publication_registry.purge_household(UUID(household_id))


class TestCockpit:
    def test_summary_rollup_counts(self, client, book):
        body = client.get("/api/avantos/cockpit").get_json()
        names = [row["name"] for row in body["households"]]
        assert "Healthy HH" in names and "AtRisk HH" in names
        assert body["summary"]["households"] >= 2
        assert body["summary"]["at_risk"] >= 1

    def test_at_risk_households_sort_first(self, client, book):
        body = client.get("/api/avantos/cockpit").get_json()
        rows = [row for row in body["households"] if row["name"].endswith("HH")]
        assert rows[0]["name"] == "AtRisk HH"
        assert rows[0]["health_band"] == "at_risk"
        assert rows[0]["first_shortfall_year"] is not None

    def test_publication_status_reflected(self, client, book):
        healthy_id = next(row["household_id"] for row
                          in client.get("/api/avantos/cockpit").get_json()["households"]
                          if row["name"] == "Healthy HH")
        scenarios = client.get(f"/api/v1/households/{healthy_id}/scenarios").get_json()["scenarios"]
        scenario_id = scenarios[0]["id"]
        client.post(f"/api/v1/scenarios/{scenario_id}/publish", json={})
        row = next(row for row
                   in client.get("/api/avantos/cockpit").get_json()["households"]
                   if row["household_id"] == healthy_id)
        assert row["publication_status"] == "published"
        assert row["published_at"] is not None

    def test_open_work_items_counted(self, client, book):
        at_risk_id = next(row["household_id"] for row
                          in client.get("/api/avantos/cockpit").get_json()["households"]
                          if row["name"] == "AtRisk HH")
        client.post(f"/api/v1/households/{at_risk_id}/alerts",
                    json={"payload": {"kind": "plan_drift", "title": "behind"}})
        client.post(f"/api/v1/households/{at_risk_id}/tasks",
                    json={"payload": {"title": "call client"}})
        row = next(row for row
                   in client.get("/api/avantos/cockpit").get_json()["households"]
                   if row["household_id"] == at_risk_id)
        assert row["open_alerts"] >= 1
        assert row["open_tasks"] >= 1
        assert row["drift_flagged"] is True

    def test_client_role_gets_404(self, book):
        from flask import Flask, request

        app = Flask(__name__)
        app.testing = True

        @app.before_request
        def _client_claims():
            request.environ["user.claims"] = {"roles": ["client"]}

        app.register_blueprint(avantos_bp, url_prefix="/api/avantos",
                               name="avantos_client")
        assert app.test_client().get("/api/avantos/cockpit").status_code == 404

    def test_health_endpoint(self, client):
        assert client.get("/api/avantos/health").get_json()["status"] == "ok"
