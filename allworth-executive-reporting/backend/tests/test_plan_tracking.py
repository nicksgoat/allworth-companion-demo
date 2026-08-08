"""Tests for plan-vs-actual tracking (diff, drift, apply) and its endpoint.

Run from the backend/ directory:

    python -m pytest tests/test_plan_tracking.py -v
"""
from __future__ import annotations

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

os.environ["AUTH_DISABLE"] = "1"

from planengine.engine import run_projection
from planengine.models import Facts
from planning.routes import bp as planning_bp
from planning.services.plan_tracking import (apply_actuals, diff_accounts,
                                             drift_status)
from planning.services.planning_store import store

D = Decimal


def make_facts(values: dict[str, int], source: str = "datawarehouse") -> Facts:
    return Facts.model_validate({
        "name": "Tracked Household",
        "people": [{"role": "client", "date_of_birth": "1960-01-01",
                    "retirement_age": 65, "assumed_age_of_death": 90}],
        "accounts": [{"kind": "taxable", "name": name, "value": value,
                      "growth_rate": "0.05", "source_id": f"sf-{name}"}
                     for name, value in values.items()],
        "expenses": [{"name": "Living", "kind": "living", "amount": 60000,
                      "starts": {"kind": "immediately"},
                      "ends": {"kind": "client_death"}}],
        "assumptions": {"start_year": 2026},
        "metadata": {"source": source, "source_id": "001XX000003GXXX",
                     "data_quality_warnings": []},
    })


class TestDiffAccounts:
    def test_matched_added_removed(self):
        plan = make_facts({"Brokerage": 500000, "Old Account": 100000})
        fresh = make_facts({"Brokerage": 550000, "New Account": 25000})
        diff = diff_accounts(plan, fresh)
        assert [m["name"] for m in diff["matched"]] == ["Brokerage"]
        assert diff["matched"][0]["delta"] == "50000"
        assert [a["name"] for a in diff["added"]] == ["New Account"]
        assert [r["name"] for r in diff["removed"]] == ["Old Account"]
        assert diff["total_delta"] == str(D("575000") - D("600000"))

    def test_accounts_match_on_source_id_not_name(self):
        plan = make_facts({"Brokerage": 500000})
        fresh = make_facts({"Brokerage": 500000})
        fresh.accounts[0].name = "Brokerage (renamed)"
        # source_id is derived from original name in the fixture, so force match:
        fresh.accounts[0].source_id = plan.accounts[0].source_id
        diff = diff_accounts(plan, fresh)
        assert len(diff["matched"]) == 1
        assert diff["added"] == [] and diff["removed"] == []


class TestDriftStatus:
    @pytest.fixture(scope="class")
    def projection(self):
        return run_projection(make_facts({"Brokerage": 1000000}))

    def test_on_track_within_tolerance(self, projection):
        row = projection.rows[0]
        projected = sum(row.account_balances.values(), D("0"))
        result = drift_status(projection, projected, row.year)
        assert result["status"] == "on_track"

    def test_behind_below_tolerance(self, projection):
        row = projection.rows[0]
        projected = sum(row.account_balances.values(), D("0"))
        result = drift_status(projection, projected * D("0.90"), row.year)
        assert result["status"] == "behind"

    def test_ahead_above_tolerance(self, projection):
        row = projection.rows[0]
        projected = sum(row.account_balances.values(), D("0"))
        result = drift_status(projection, projected * D("1.10"), row.year)
        assert result["status"] == "ahead"


class TestApplyActuals:
    def test_assets_replaced_planning_inputs_preserved(self):
        plan = make_facts({"Brokerage": 500000})
        plan.expenses[0].amount = D("77777")  # advisor-owned input
        fresh = make_facts({"Brokerage": 610000})
        updated = apply_actuals(plan, fresh, synced_at="2026-07-31T00:00:00Z")
        assert updated.accounts[0].value == D("610000")
        assert updated.expenses[0].amount == D("77777")
        assert updated.metadata["last_actuals_sync"] == "2026-07-31T00:00:00Z"

    def test_household_identity_unchanged(self):
        plan = make_facts({"Brokerage": 500000})
        fresh = make_facts({"Brokerage": 610000})
        updated = apply_actuals(plan, fresh)
        assert updated.household_id == plan.household_id
        assert updated.name == plan.name


class TestSyncActualsEndpoint:
    @pytest.fixture()
    def client(self):
        from flask import Flask

        app = Flask(__name__)
        app.testing = True
        app.register_blueprint(planning_bp, url_prefix="/api/v1", name="planning_sync")
        return app.test_client()

    @pytest.fixture()
    def warehouse_household(self, client):
        plan = make_facts({"Brokerage": 500000})
        created, _ = store.create_household(plan.model_dump(mode="json"), "tests")
        yield created.household_id
        try:
            store.delete_household(created.household_id, "tests", "cleanup")
        except KeyError:
            pass

    def _mock_session(self):
        factory = MagicMock()
        factory.return_value = MagicMock()
        return factory

    def test_sync_reports_drift_without_applying(self, client, warehouse_household):
        fresh = make_facts({"Brokerage": 300000})  # far behind plan
        with patch("planning.routes.get_session_factory", self._mock_session()), \
             patch("planning.routes.import_household", return_value=fresh):
            response = client.post(
                f"/api/v1/households/{warehouse_household}/sync-actuals", json={})
        body = response.get_json()
        assert response.status_code == 200, body
        assert body["applied"] is False
        assert body["drift"]["status"] == "behind"
        assert body["alert"] is not None and body["alert"]["payload"]["kind"] == "plan_drift"
        # Plan copy untouched.
        assert store.get_facts(warehouse_household).accounts[0].value == D("500000")

    def test_sync_apply_replaces_assets(self, client, warehouse_household):
        projection = run_projection(make_facts({"Brokerage": 500000}))
        projected = sum(projection.rows[0].account_balances.values(), D("0"))
        fresh = make_facts({"Brokerage": int(projected)})  # exactly on plan
        with patch("planning.routes.get_session_factory", self._mock_session()), \
             patch("planning.routes.import_household", return_value=fresh):
            response = client.post(
                f"/api/v1/households/{warehouse_household}/sync-actuals",
                json={"apply": True})
        body = response.get_json()
        assert response.status_code == 200, body
        assert body["applied"] is True
        assert body["drift"]["status"] == "on_track"
        assert body["alert"] is None
        assert store.get_facts(warehouse_household).accounts[0].value == D(int(projected))

    def test_sync_rejected_for_manual_households(self, client):
        manual = make_facts({"Brokerage": 100000}, source="planning")
        manual.metadata.pop("source_id")
        created, _ = store.create_household(manual.model_dump(mode="json"), "tests")
        try:
            response = client.post(
                f"/api/v1/households/{created.household_id}/sync-actuals", json={})
            assert response.status_code == 422
        finally:
            store.delete_household(created.household_id, "tests", "cleanup")
