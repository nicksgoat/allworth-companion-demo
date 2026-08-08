"""Smoke tests for the CRM blueprint (read-only Client 360 over Synapse).

The CRM queries the live warehouse, so these tests verify the offline
contract: every route registers, degrades to the ``{success, error}``
envelope without a database, and never raises.

Run from the backend/ directory:

    python -m pytest tests/test_crm.py -v
"""
from __future__ import annotations

import os

import pytest

os.environ["AUTH_DISABLE"] = "1"

from crm.routes import _clamp_limit, _json_safe, bp as crm_bp


@pytest.fixture()
def client(monkeypatch):
    from flask import Flask

    import crm.routes as crm_routes

    # Fail the connection instantly instead of waiting out the ODBC login
    # timeout — these tests only assert the offline error contract.
    def _no_db():
        raise RuntimeError("warehouse unavailable (test)")

    monkeypatch.setattr(crm_routes, "_get_db_connection", _no_db)
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(crm_bp, url_prefix="/api/crm")
    return app.test_client()


ROUTES = [
    "/api/crm/summary",
    "/api/crm/filters",
    "/api/crm/clients",
    "/api/crm/clients/00Q000000000001",
    "/api/crm/clients/00Q000000000001/activities",
    "/api/crm/clients/00Q000000000001/opportunities",
    "/api/crm/clients/00Q000000000001/accounts",
    "/api/crm/clients/00Q000000000001/flows",
    "/api/crm/clients/00Q000000000001/portfolio",
    "/api/crm/opportunities",
    "/api/crm/tasks",
    "/api/crm/advisors",
    "/api/crm/advisors/005000000000001",
    "/api/crm/advisors/005000000000001/book",
]


class TestOfflineContract:
    @pytest.mark.parametrize("route", ROUTES)
    def test_route_degrades_to_envelope(self, client, route):
        """Without a warehouse connection every route must return the JSON
        envelope (success: false + error) instead of raising."""
        response = client.get(route)
        body = response.get_json()
        assert body is not None, f"{route} did not return JSON"
        assert "success" in body
        if response.status_code != 200:
            assert body["success"] is False
            assert body.get("error")


class TestHelpers:
    def test_json_safe_strips_non_finite_floats(self):
        cleaned = _json_safe({"a": float("nan"), "b": [float("inf"), 1.5], "c": "x"})
        assert cleaned == {"a": None, "b": [None, 1.5], "c": "x"}

    def test_clamp_limit_bounds(self):
        assert _clamp_limit("50", default=200, ceiling=1000) == 50
        assert _clamp_limit("999999", default=200, ceiling=1000) == 1000
        assert _clamp_limit(None, default=200, ceiling=1000) == 200
        assert _clamp_limit("junk", default=200, ceiling=1000) == 200
