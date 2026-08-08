"""Tests for the Executive Report blueprint.

Covers:
- NCNM model helpers + component math (pure functions, no DB)
- flows helpers (_fnum) and dynamic YTD window shape
- summary fallback (deterministic, viewer-independent)
- API endpoints (report, refresh, health) with a mocked Synapse connection

Run from the backend/ directory:

    python -m pytest tests/test_executive_report.py -v
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

# Disable auth so tests can hit routes without a JWT
os.environ["AUTH_DISABLE"] = "1"

from executive_report import ncnm_model, summary as summary_mod  # noqa: E402
from executive_report.routes import _cache, _json_safe  # noqa: E402


@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


@pytest.fixture()
def app():
    from flask import Flask
    from executive_report.routes import bp

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(bp, url_prefix="/executive-report")
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Unit: NCNM model helpers
# ---------------------------------------------------------------------------

class TestNcnmModel:
    def test_add_and_diff_months(self):
        assert ncnm_model._add_months("2026-01", 3) == "2026-04"
        assert ncnm_model._add_months("2026-11", 2) == "2027-01"
        assert ncnm_model._month_diff_ym("2026-04", "2026-01") == 3
        assert ncnm_model._month_diff_ym("2027-01", "2026-11") == 2

    def test_get_funding_cycle_fallback(self):
        assert ncnm_model.get_funding_cycle("CRP") == [0.74, 0.17, 0.02, 0.07]
        assert ncnm_model.get_funding_cycle("Unknown") == ncnm_model.FUNDING_CYCLE

    def test_build_ncnm_paum_ratio(self):
        rows = [
            {"channel_group": "CRP", "total_ncnm": 50.0, "PAUM": 100.0},
            {"channel_group": "CRP", "total_ncnm": 30.0, "PAUM": 100.0},
            {"channel_group": "Paid Leads", "total_ncnm": 20.0, "PAUM": 200.0},
        ]
        ratios = ncnm_model.build_ncnm_paum_ratio(rows)
        assert ratios["CRP"] == pytest.approx(0.4)
        assert ratios["Paid Leads"] == pytest.approx(0.1)

    def test_component_a_offsets_funding(self):
        # A CRP close last month should schedule its M+1..M+3 tail into forecast months.
        recent = [{"channel_group": "CRP", "close_month": "2026-01", "close_paum": 1_000_000.0}]
        ratios = {"CRP": 0.5}
        months = ["2026-02", "2026-03", "2026-04", "2026-05"]
        df = ncnm_model.component_a(recent, ratios, months)
        assert not df.empty
        # M+0 (close month) is excluded — only offsets >= 1 appear
        assert set(df["forecast_month"]) <= set(months)
        assert (df["expected_ncnm"] > 0).all()

    def test_build_volatility_fallback(self):
        vol = ncnm_model.build_volatility([])
        assert vol["_total"] == 0.20


# ---------------------------------------------------------------------------
# Unit: flows + summary
# ---------------------------------------------------------------------------

class TestFlowsAndSummary:
    def test_fnum(self):
        from executive_report import flows
        assert flows._fnum(None) == 0.0
        assert flows._fnum("3.5") == 3.5
        assert flows._fnum("bad") == 0.0

    def test_json_safe(self):
        assert _json_safe(float("nan")) is None
        assert _json_safe({"a": float("inf"), "b": [1.0]}) == {"a": None, "b": [1.0]}

    def test_summary_fallback_is_deterministic(self):
        flows = {"kpis": {"current_year": 2026, "prior_year": 2025,
                          "appts_current": 100, "appts_prior": 80,
                          "appts_yoy_pct": 0.25, "appt_paum_current": 5e8,
                          "appt_paum_prior": 4e8, "appt_paum_yoy_pct": 0.25}}
        ncnm = {"eom_projection": 1e7, "mtd_actual": 4e6, "remaining_expected": 6e6,
                "confidence": {"low": 8e6, "high": 1.2e7}}
        # Force the LLM path unavailable so we exercise the deterministic fallback.
        with patch("executive_report.summary._build_client", return_value=(None, None)):
            a = summary_mod.generate_summary(flows, ncnm)
            b = summary_mod.generate_summary(flows, ncnm)
        assert a["source"] == "fallback"
        assert a["summary"] == b["summary"]  # identical for all viewers
        assert "**Bottom line**" in a["summary"]


# ---------------------------------------------------------------------------
# API endpoints (mocked DB + summary)
# ---------------------------------------------------------------------------

def _empty_conn():
    """A connection whose cursor returns no rows for every query."""
    cursor = MagicMock()
    cursor.description = []
    cursor.fetchall.return_value = []
    cursor.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


class TestEndpoints:
    def test_health_empty(self, client):
        rv = client.get("/executive-report/api/health")
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["success"] is True
        assert body["cached"] is False

    def test_report_builds_and_caches(self, client):
        fake_flows = {"kpis": {"current_year": 2026, "prior_year": 2025,
                               "appts_current": 1, "appts_prior": 1,
                               "appts_yoy_pct": 0.0, "appt_paum_current": 0.0,
                               "appt_paum_prior": 0.0, "appt_paum_yoy_pct": 0.0},
                      "appts_paum_by_channel": [], "funnel_by_channel_yoy": []}
        fake_ncnm = {"eom_projection": 0.0, "mtd_actual": 0.0, "remaining_expected": 0.0,
                     "grand_total": 0.0, "by_component": [], "by_channel": [],
                     "component_detail": {"A": [], "B": [], "C": []},
                     "confidence": {"cv": 0.2, "low": 0.0, "high": 0.0}}
        with patch("executive_report.routes._get_db_connection", return_value=_empty_conn()), \
             patch("executive_report.flows.compute_flows", return_value=fake_flows), \
             patch("executive_report.ncnm_model.compute_forecast", return_value=fake_ncnm), \
             patch("executive_report.summary.generate_summary",
                   return_value={"summary": "ok", "model": None, "source": "fallback"}):
            rv = client.get("/executive-report/api/report")
        assert rv.status_code == 200
        data = rv.get_json()["data"]
        assert data["flows"] == fake_flows
        assert data["ncnm"] == fake_ncnm
        assert data["summary"]["summary"] == "ok"
        # Second call served from cache (health now reports cached)
        rv2 = client.get("/executive-report/api/health")
        assert rv2.get_json()["cached"] is True
