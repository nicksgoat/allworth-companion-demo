"""Contract tests for the Financial Planning (PlanEngine) Flask blueprint.

Covers:
- Household lifecycle (create, summary, facts, list)
- JSON-Patch facts editing + commit versioning
- Scenario create/override/promote and projection
- Stress tests, solve-for, goals, compare
- Monte Carlo job lifecycle and seeded reproducibility
- Roth conversion analysis endpoint
- Client-role isolation (advisor-only surfaces hidden)

Run from the backend/ directory:

    python -m pytest tests/test_planning_api.py -v
"""
from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest

os.environ["AUTH_DISABLE"] = "1"
os.environ.pop("PLANNING_SYNAPSE_PERSISTENCE", None)

from planning.routes import bp as planning_bp
from planning.services.planning_store import store
from planning.services.projections import projection_service


HOUSEHOLD_PAYLOAD = {
    "name": "API Test Household",
    "people": [
        {"role": "client", "first_name": "Ada", "date_of_birth": "1958-06-15",
         "retirement_age": 65, "assumed_age_of_death": 90},
        {"role": "spouse", "first_name": "Sam", "date_of_birth": "1960-03-01",
         "retirement_age": 65, "assumed_age_of_death": 92},
    ],
    "accounts": [
        {"kind": "taxable", "name": "Brokerage", "value": 800000,
         "tax_basis": 500000, "growth_rate": "0.05", "income_yield": "0.02"},
        {"kind": "qualified", "name": "IRA", "owner": "client", "value": 1200000,
         "growth_rate": "0.05", "apply_rmd": True},
        {"kind": "roth", "name": "Roth IRA", "value": 50000, "growth_rate": "0.05"},
    ],
    "income": [
        {"name": "Client SS", "kind": "social_security", "amount": 36000,
         "owner": "client", "starts": {"kind": "immediately"},
         "ends": {"kind": "client_death"}},
    ],
    "expenses": [
        {"name": "Living", "kind": "living", "amount": 110000, "required": True,
         "starts": {"kind": "immediately"}, "ends": {"kind": "second_death"}},
    ],
    "assumptions": {"start_year": 2026, "inflation_rate": "0.03",
                    "tax_mode": "form_1040", "plan_end_age": 95},
    # Offline Monte Carlo inputs: an advisor-reviewed allocation snapshot so the
    # MC endpoint is "ready" without a live Synapse session.
    "metadata": {"monte_carlo_inputs": {"holding_classes": [
        {"asset_class": "U.S. Equity", "market_value": 1230000},
        {"asset_class": "Fixed Income", "market_value": 820000},
    ]}},
}


@pytest.fixture()
def app():
    from flask import Flask

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(planning_bp, url_prefix="/api/v1")
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def household(client):
    """Create a household and return (household_id, scenario_ids)."""
    response = client.post("/api/v1/households", json=HOUSEHOLD_PAYLOAD)
    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    household_id = body["household_id"]
    yield household_id, body["scenario_ids"]
    # Teardown directly through the store to keep tests independent.
    try:
        store.delete_household(__import__("uuid").UUID(household_id), "tests", "cleanup")
    except KeyError:
        pass
    projection_service.clear()


def _proposed_scenario(client, household_id):
    scenarios = client.get(f"/api/v1/households/{household_id}/scenarios").get_json()["scenarios"]
    return next(s["id"] for s in scenarios if s["name"] == "Proposed Plan")


class TestHouseholdLifecycle:
    def test_create_returns_two_default_scenarios(self, household):
        _, scenario_ids = household
        assert len(scenario_ids) == 2

    def test_summary_reports_net_worth_and_quality(self, client, household):
        household_id, _ = household
        summary = client.get(f"/api/v1/households/{household_id}/summary").get_json()
        assert summary["total_assets"] == "2050000"
        assert summary["data_quality"]["has_client"] is True
        assert summary["scenario_count"] == 2

    def test_facts_round_trip(self, client, household):
        household_id, _ = household
        facts = client.get(f"/api/v1/households/{household_id}/facts").get_json()
        assert facts["name"] == "API Test Household"
        assert len(facts["accounts"]) == 3

    def test_unknown_household_is_404(self, client):
        assert client.get(f"/api/v1/households/{uuid4()}/summary").status_code == 404


class TestFactsEditing:
    def test_json_patch_replace_and_commit(self, client, household):
        household_id, _ = household
        patch = {"ops": [{"op": "replace", "path": "/expenses/0/amount", "value": "95000"}]}
        response = client.patch(f"/api/v1/households/{household_id}/facts", json=patch)
        assert response.status_code == 200
        assert response.get_json()["expenses"][0]["amount"] == "95000"
        commit = client.post(f"/api/v1/households/{household_id}/facts/commit")
        assert commit.status_code == 201
        assert "facts_version_id" in commit.get_json()

    def test_invalid_patch_op_rejected(self, client, household):
        household_id, _ = household
        patch = {"ops": [{"op": "move", "path": "/name", "from": "/name"}]}
        response = client.patch(f"/api/v1/households/{household_id}/facts", json=patch)
        assert response.status_code == 422

    def test_warehouse_assets_are_read_only(self, client):
        payload = dict(HOUSEHOLD_PAYLOAD, name="Warehouse HH",
                       metadata={"source": "datawarehouse"})
        created = client.post("/api/v1/households", json=payload).get_json()
        household_id = created["household_id"]
        try:
            patch = {"ops": [{"op": "replace", "path": "/accounts/0/value", "value": "1"}]}
            response = client.patch(f"/api/v1/households/{household_id}/facts", json=patch)
            assert response.status_code == 409
        finally:
            store.delete_household(__import__("uuid").UUID(household_id), "tests", "cleanup")


class TestScenarios:
    def test_projection_has_rows_and_ending_net_worth(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        projection = client.post(f"/api/v1/scenarios/{scenario_id}/project").get_json()
        assert projection["start_year"] == 2026
        assert len(projection["rows"]) > 20
        assert "ending_net_worth" in projection

    def test_override_changes_projection(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        base = client.post(f"/api/v1/scenarios/{scenario_id}/project").get_json()
        response = client.patch(
            f"/api/v1/scenarios/{scenario_id}/overrides",
            json={"overrides": [{"op": "replace", "path": "/expenses/0/amount",
                                 "value": "150000"}]})
        assert response.status_code == 200
        changed = client.post(f"/api/v1/scenarios/{scenario_id}/project").get_json()
        assert changed["ending_net_worth"] != base["ending_net_worth"]

    def test_duplicate_scenario_name_conflicts(self, client, household):
        household_id, _ = household
        first = client.post(f"/api/v1/households/{household_id}/scenarios",
                            json={"name": "What If"})
        assert first.status_code == 201
        duplicate = client.post(f"/api/v1/households/{household_id}/scenarios",
                                json={"name": "what if"})
        assert duplicate.status_code == 409

    def test_stress_crash_reduces_ending_net_worth(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        stressed = client.post(f"/api/v1/scenarios/{scenario_id}/stress/crash").get_json()
        assert float(stressed["delta_ending_net_worth"]) < 0

    def test_unsupported_stress_kind_rejected(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        assert client.post(f"/api/v1/scenarios/{scenario_id}/stress/asteroid").status_code == 422

    def test_goals_endpoint_returns_list(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        assert client.get(f"/api/v1/scenarios/{scenario_id}/goals").get_json()["goals"] == []

    def test_compare_returns_series_per_scenario(self, client, household):
        household_id, scenario_ids = household
        response = client.post(f"/api/v1/households/{household_id}/compare",
                               json={"scenario_ids": scenario_ids})
        body = response.get_json()
        assert len(body["scenarios"]) == 2
        assert all("ending_net_worth" in s and s["series"] for s in body["scenarios"])

    def test_solve_monthly_savings(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        response = client.post(f"/api/v1/scenarios/{scenario_id}/solve",
                               json={"lever": "monthly_savings", "target": 3000000})
        body = response.get_json()
        assert response.status_code == 200
        assert body["lever"] == "monthly_savings"


class TestRothConversion:
    def test_analysis_returns_candidates_and_baseline(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        response = client.post(f"/api/v1/scenarios/{scenario_id}/roth-conversion",
                               json={"window_years": 5})
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        assert body["window_years"] == 5
        assert body["source_account_name"] == "IRA"
        assert body["candidates"], "expected at least one conversion candidate"
        for candidate in body["candidates"]:
            assert {"label", "annual_conversion", "lifetime_tax_delta",
                    "ending_after_tax_delta", "breakeven_year"} <= set(candidate)

    def test_invalid_window_rejected(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        assert client.post(f"/api/v1/scenarios/{scenario_id}/roth-conversion",
                           json={"window_years": 99}).status_code == 422

    def test_invalid_heir_rate_rejected(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        assert client.post(f"/api/v1/scenarios/{scenario_id}/roth-conversion",
                           json={"heir_tax_rate": "2"}).status_code == 422


class TestMonteCarlo:
    def _await_job(self, client, job_id, timeout=30.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = client.get(f"/api/v1/jobs/{job_id}").get_json()
            if job["status"] in {"succeeded", "failed"}:
                return job
            time.sleep(0.1)
        pytest.fail("Monte Carlo job did not finish in time")

    def test_job_lifecycle_and_seeded_reproducibility(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        results = []
        for _ in range(2):
            queued = client.post(f"/api/v1/scenarios/{scenario_id}/monte-carlo",
                                 json={"trials": 50, "seed": 7,
                                       "refresh_synapse_inputs": False})
            assert queued.status_code == 202, queued.get_json()
            job = self._await_job(client, queued.get_json()["job_id"])
            assert job["status"] == "succeeded", job.get("error")
            results.append(job["result"])
        assert results[0]["probability_of_success"] == results[1]["probability_of_success"]
        assert results[0]["ending_value_percentiles"] == results[1]["ending_value_percentiles"]

    def test_inputs_endpoint_reports_readiness(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        inputs = client.get(
            f"/api/v1/scenarios/{scenario_id}/monte-carlo/inputs?refresh_synapse=0").get_json()
        assert "ready" in inputs and "warnings" in inputs


class TestReports:
    def test_definitions_listed(self, client, household):
        definitions = client.get("/api/v1/report-definitions").get_json()["definitions"]
        assert len(definitions) == 20

    def test_report_renders_html(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        response = client.get(f"/api/v1/scenarios/{scenario_id}/reports/1")
        assert response.status_code == 200
        assert b"<html" in response.data

    @pytest.mark.parametrize("definition_id,marker", [
        (1, b"Assets"),                      # Balance Sheet / Net Worth
        (6, b"Retirement begins"),           # Retirement Analysis
        (7, b"Claim age"),                   # Social Security Comparison
        (9, b"conversion"),                  # Roth Conversion Analysis
        (13, b"Gross estate"),               # Estate Flowchart
        (16, b"Asset class"),                # Asset Allocation
    ])
    def test_named_renderers_produce_specific_content(self, client, household,
                                                      definition_id, marker):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        response = client.get(f"/api/v1/scenarios/{scenario_id}/reports/{definition_id}")
        assert response.status_code == 200
        assert marker in response.data, response.data[:500]

    def test_generic_fallback_still_renders(self, client, household):
        household_id, _ = household
        scenario_id = _proposed_scenario(client, household_id)
        response = client.get(f"/api/v1/scenarios/{scenario_id}/reports/2")  # Cash Flow
        assert response.status_code == 200
        assert b"Ending net worth" in response.data


class TestClientRoleIsolation:
    """Client-portal roles must never see advisor planning surfaces."""

    @pytest.fixture()
    def client_role_app(self):
        from flask import Flask, request

        app = Flask(__name__)
        app.testing = True

        @app.before_request
        def _inject_client_claims():
            request.environ["user.email"] = "client@example.com"
            request.environ["user.claims"] = {"roles": ["client"],
                                              "email": "client@example.com"}

        app.register_blueprint(planning_bp, url_prefix="/api/v1", name="planning_client")
        return app

    def test_client_cannot_read_facts_or_mutate(self, client, household, client_role_app):
        household_id, _ = household
        portal = client_role_app.test_client()
        assert portal.get(f"/api/v1/households/{household_id}/facts").status_code == 404
        assert portal.patch(f"/api/v1/households/{household_id}/facts",
                            json={"ops": []}).status_code == 404
