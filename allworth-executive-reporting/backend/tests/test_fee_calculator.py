"""Tests for the Fee Calculator blueprint.

Covers:
- Tiered fee calculation engine (blended rates, min fee logic)
- Schedule definitions and listing
- API endpoints (calculate, calculate-all, schedules, search, household, filters)
- Billing CSV upload with aggregation and schedule detection
- Billing definition → schedule mapping

Run from the backend/ directory:

    python -m pytest tests/test_fee_calculator.py -v
"""
from __future__ import annotations

import io
import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Disable auth so tests can hit routes without JWT
os.environ["AUTH_DISABLE"] = "1"

from fee_calculator.routes import (
    ALL_SCHEDULES,
    GM_SCHEDULE_NEW,
    AIRLINE_SCHEDULE,
    REPRICING_SCHEDULES,
    calculate_tiered_fee,
    _recommend_schedule_by_aum,
    _cache_clear,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_cache():
    """Ensure each test starts with a clean cache."""
    _cache_clear()
    yield
    _cache_clear()


@pytest.fixture()
def app():
    """Create a minimal Flask app with the fee_calculator blueprint."""
    from flask import Flask
    from fee_calculator.routes import bp

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(bp, url_prefix="/fee-calculator")
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


# ---------------------------------------------------------------------------
# Unit tests: calculate_tiered_fee
# ---------------------------------------------------------------------------

class TestCalculateTieredFee:
    """Test the core fee calculation engine."""

    def test_zero_aum(self):
        result = calculate_tiered_fee(0, GM_SCHEDULE_NEW)
        assert result["aum"] == 0
        # Min fee applies when calculated fee is 0
        assert result["min_fee_applied"] is True
        assert result["quarterly_fee"] == 2_500
        assert result["annual_fee"] == 10_000

    def test_single_tier_small_aum(self):
        """$100k should be entirely in first tier at 1.50%."""
        result = calculate_tiered_fee(100_000, GM_SCHEDULE_NEW)
        assert result["breakdown"][0]["assets_in_tier"] == 100_000
        assert result["breakdown"][0]["fee"] == 1_500.0  # 100k * 1.5%
        # Min fee check: $1500/4 = $375 < $2500 min quarterly → min applies
        assert result["min_fee_applied"] is True
        assert result["quarterly_fee"] == 2_500
        assert result["annual_fee"] == 10_000

    def test_min_fee_not_applied_large_aum(self):
        """$2M should exceed the minimum quarterly fee threshold."""
        result = calculate_tiered_fee(2_000_000, GM_SCHEDULE_NEW)
        assert result["min_fee_applied"] is False
        # Verify total is reasonable (blended ~1.0-1.1%)
        assert 18_000 < result["annual_fee"] < 24_000

    def test_blended_rate_two_tiers(self):
        """$500k spans first two tiers of GM Schedule New."""
        result = calculate_tiered_fee(500_000, GM_SCHEDULE_NEW)
        # Tier 1: 250k * 1.5% = 3750
        assert result["breakdown"][0]["assets_in_tier"] == 250_000
        assert result["breakdown"][0]["fee"] == 3_750.0
        # Tier 2: 250k * 1.25% = 3125
        assert result["breakdown"][1]["assets_in_tier"] == 250_000
        assert result["breakdown"][1]["fee"] == 3_125.0
        # Raw fee = 6875, but quarterly = 1718.75 < $2500 min → min applies
        assert result["min_fee_applied"] is True
        assert result["quarterly_fee"] == 2_500
        assert result["annual_fee"] == 10_000

    def test_blended_rate_no_min_fee(self):
        """$500k with Airline schedule (no min fee) shows pure blended rate."""
        result = calculate_tiered_fee(500_000, AIRLINE_SCHEDULE)
        # Tier 1: 500k * 1.2% = 6000
        assert result["breakdown"][0]["assets_in_tier"] == 500_000
        assert result["breakdown"][0]["fee"] == 6_000.0
        assert result["min_fee_applied"] is False
        assert result["annual_fee"] == 6_000.0
        assert result["quarterly_fee"] == 1_500.0

    def test_unbounded_top_tier(self):
        """$100M should overflow into the unbounded top tier."""
        result = calculate_tiered_fee(100_000_000, GM_SCHEDULE_NEW)
        # Last tier catches everything above $50M at 0.30%
        last_tier = result["breakdown"][-1]
        assert last_tier["to"] is None
        assert last_tier["assets_in_tier"] == 50_000_000  # 100M - 50M
        assert last_tier["rate"] == 0.003

    def test_airline_schedule_basic(self):
        """Airline schedule has no minimum fee."""
        result = calculate_tiered_fee(300_000, AIRLINE_SCHEDULE)
        assert result["min_fee_applied"] is False
        assert result["min_quarterly_fee"] == 0
        # First tier: 300k but the first tier goes to 500k
        assert result["breakdown"][0]["assets_in_tier"] == 300_000
        assert result["breakdown"][0]["fee"] == 3_600.0  # 300k * 1.2%

    def test_repricing_elite_flat(self):
        """Elite schedule has the same rate for first 4 tiers (0.95%)."""
        elite = REPRICING_SCHEDULES["Elite (5)"]
        result = calculate_tiered_fee(1_000_000, elite)
        # All first tiers at 0.95%
        assert result["breakdown"][0]["rate"] == 0.0095
        assert result["breakdown"][2]["rate"] == 0.0095

    def test_effective_rate_makes_sense(self):
        """Effective rate should be between lowest and highest tier rates."""
        result = calculate_tiered_fee(5_000_000, GM_SCHEDULE_NEW)
        lowest = min(t["rate"] for t in GM_SCHEDULE_NEW["tiers"])
        highest = max(t["rate"] for t in GM_SCHEDULE_NEW["tiers"])
        eff = result["effective_rate_pct"] / 100
        assert lowest <= eff <= highest

    def test_bps_conversion(self):
        """effective_rate_bps should be effective_rate_pct * 100."""
        result = calculate_tiered_fee(1_000_000, GM_SCHEDULE_NEW)
        assert abs(result["effective_rate_bps"] - result["effective_rate_pct"] * 100) < 0.01


# ---------------------------------------------------------------------------
# Unit tests: _recommend_schedule_by_aum
# ---------------------------------------------------------------------------

class TestRecommendScheduleByAum:
    """Test AUM-band-based schedule recommendation."""

    def test_below_300k_silver(self):
        assert _recommend_schedule_by_aum(100_000) == "repricing_silver"

    def test_at_300k_silver(self):
        assert _recommend_schedule_by_aum(300_000) == "repricing_silver"

    def test_above_300k_gold(self):
        assert _recommend_schedule_by_aum(300_000.01) == "repricing_gold"

    def test_at_1m_gold(self):
        assert _recommend_schedule_by_aum(1_000_000) == "repricing_gold"

    def test_above_1m_platinum(self):
        assert _recommend_schedule_by_aum(1_000_000.01) == "repricing_platinum"

    def test_at_2m_platinum(self):
        assert _recommend_schedule_by_aum(2_000_000) == "repricing_platinum"

    def test_above_2m_elite(self):
        assert _recommend_schedule_by_aum(2_000_000.01) == "repricing_elite"

    def test_at_5m_elite(self):
        assert _recommend_schedule_by_aum(5_000_000) == "repricing_elite"

    def test_above_5m_fixed_080(self):
        assert _recommend_schedule_by_aum(5_000_000.01) == "fixed_080"

    def test_at_7_5m_fixed_080(self):
        assert _recommend_schedule_by_aum(7_500_000) == "fixed_080"

    def test_above_7_5m_fixed_075(self):
        assert _recommend_schedule_by_aum(7_500_000.01) == "fixed_075"

    def test_at_10m_fixed_075(self):
        assert _recommend_schedule_by_aum(10_000_000) == "fixed_075"

    def test_above_10m_fixed_070(self):
        assert _recommend_schedule_by_aum(10_000_000.01) == "fixed_070"

    def test_at_20m_fixed_070(self):
        assert _recommend_schedule_by_aum(20_000_000) == "fixed_070"

    def test_above_20m_none(self):
        """$20M+ should return None (no recommendation)."""
        assert _recommend_schedule_by_aum(20_000_000.01) is None

    def test_50m_none(self):
        assert _recommend_schedule_by_aum(50_000_000) is None

    def test_zero_aum_silver(self):
        assert _recommend_schedule_by_aum(0) == "repricing_silver"


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestSchedulesEndpoint:
    """GET /fee-calculator/api/schedules."""

    def test_returns_all_schedules(self, client):
        resp = client.get("/fee-calculator/api/schedules")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        schedules = data["schedules"]
        assert "gm_schedule_new" in schedules
        assert "airline" in schedules
        assert "repricing_silver" in schedules
        assert "repricing_elite" in schedules
        # Each schedule has name and tiers
        for key, sched in schedules.items():
            assert "name" in sched
            assert "tiers" in sched
            assert len(sched["tiers"]) > 0


class TestCalculateEndpoint:
    """POST /fee-calculator/api/calculate."""

    def test_valid_request(self, client):
        resp = client.post(
            "/fee-calculator/api/calculate",
            json={"aum": 1_000_000, "schedule": "gm_schedule_new"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["aum"] == 1_000_000
        assert data["data"]["annual_fee"] > 0

    def test_missing_aum(self, client):
        resp = client.post(
            "/fee-calculator/api/calculate",
            json={"schedule": "gm_schedule_new"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["success"] is False

    def test_negative_aum(self, client):
        resp = client.post(
            "/fee-calculator/api/calculate",
            json={"aum": -100, "schedule": "gm_schedule_new"},
        )
        assert resp.status_code == 400

    def test_invalid_schedule(self, client):
        resp = client.post(
            "/fee-calculator/api/calculate",
            json={"aum": 1_000_000, "schedule": "nonexistent"},
        )
        assert resp.status_code == 400
        assert "Unknown schedule" in resp.get_json()["error"]

    def test_default_schedule(self, client):
        """If schedule is omitted, defaults to gm_schedule_new."""
        resp = client.post(
            "/fee-calculator/api/calculate",
            json={"aum": 500_000},
        )
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["schedule_name"] == "GM Schedule New (Min Fee)"


class TestCalculateAllEndpoint:
    """POST /fee-calculator/api/calculate-all."""

    def test_returns_all_schedules(self, client):
        resp = client.post(
            "/fee-calculator/api/calculate-all",
            json={"aum": 2_000_000},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        results = data["data"]
        assert len(results) == len(ALL_SCHEDULES)
        for key in ALL_SCHEDULES:
            assert key in results
            assert results[key]["annual_fee"] > 0

    def test_missing_aum(self, client):
        resp = client.post(
            "/fee-calculator/api/calculate-all",
            json={},
        )
        assert resp.status_code == 400


class TestCacheClearEndpoint:
    """POST /fee-calculator/api/cache-clear."""

    def test_clears_cache(self, client):
        resp = client.post("/fee-calculator/api/cache-clear")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True


# ---------------------------------------------------------------------------
# Tests requiring mocked Synapse connection
# ---------------------------------------------------------------------------


class TestFiltersEndpoint:
    """GET /fee-calculator/api/filters (mocked Synapse)."""

    @patch("fee_calculator.routes._get_db_connection")
    def test_returns_filters(self, mock_conn, client):
        import pandas as pd
        mock_conn.return_value = MagicMock()

        advisors_df = pd.DataFrame({"User_ID": ["U1", "U2"], "Name": ["Alice", "Bob"]})
        regions_df = pd.DataFrame({"Operational_Region": ["West", "East"]})
        channels_df = pd.DataFrame({"Channel_Middle": ["Advisor Enabled", "CRP"]})

        with patch("pandas.read_sql", side_effect=[advisors_df, regions_df, channels_df]):
            resp = client.get("/fee-calculator/api/filters")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "advisors" in data["data"]
        assert "regions" in data["data"]
        assert "channels" in data["data"]


class TestSearchEndpoint:
    """GET /fee-calculator/api/search (mocked Synapse)."""

    @patch("fee_calculator.routes._get_db_connection")
    def test_search_by_name(self, mock_conn, client):
        columns = ["AVHHID", "advisorid", "advisor_name", "region", "AUM", "current_aum"]
        rows = [
            (1001, "U1", "Alice", "West", 1_000_000.0, 1_100_000.0),
            (1002, "U2", "Bob", "East", 2_000_000.0, 2_100_000.0),
        ]
        cursor = MagicMock()
        cursor.description = [(c,) for c in columns]
        cursor.fetchall.return_value = rows
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_conn.return_value = conn

        resp = client.get("/fee-calculator/api/search?q=Alice")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert len(data["results"]) > 0

    def test_short_query_returns_empty(self, client):
        resp = client.get("/fee-calculator/api/search?q=A")
        assert resp.status_code == 200
        assert resp.get_json()["results"] == []


class TestHouseholdEndpoint:
    """GET /fee-calculator/api/household/<avhhid> (mocked Synapse)."""

    @patch("fee_calculator.routes._get_db_connection")
    def test_found(self, mock_conn, client):
        columns = ["AVHHID", "advisorid", "advisor_name", "Office_Location",
                   "fact_aum", "current_aum", "aum_as_of"]
        row = (1001, "U1", "Alice", "Sacramento", 1_500_000.0, 1_600_000.0, "2026-04-30")
        cursor = MagicMock()
        cursor.description = [(c,) for c in columns]
        cursor.fetchone.return_value = row
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_conn.return_value = conn

        resp = client.get("/fee-calculator/api/household/1001")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["data"]["avhhid"] == 1001
        assert data["data"]["current_aum"] == 1_600_000.0

    @patch("fee_calculator.routes._get_db_connection")
    def test_not_found(self, mock_conn, client):
        cursor = MagicMock()
        cursor.description = []
        cursor.fetchone.return_value = None
        conn = MagicMock()
        conn.cursor.return_value = cursor
        mock_conn.return_value = conn

        resp = client.get("/fee-calculator/api/household/9999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Billing upload tests
# ---------------------------------------------------------------------------

class TestBillingUpload:
    """POST /fee-calculator/api/upload-billing."""

    def _make_csv(self, rows: list[dict]) -> io.BytesIO:
        """Build a CSV file-like object from row dicts."""
        output = io.StringIO()
        if rows:
            import csv
            writer = csv.DictWriter(output, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        buf = io.BytesIO(output.getvalue().encode("utf-8"))
        buf.name = "billing.csv"
        return buf

    def test_no_file(self, client):
        resp = client.post("/fee-calculator/api/upload-billing")
        assert resp.status_code == 400
        assert "No file" in resp.get_json()["error"]

    def test_missing_columns(self, client):
        csv_data = self._make_csv([{"AVHHID": 1001, "Bad Column": 100}])
        resp = client.post(
            "/fee-calculator/api/upload-billing",
            data={"file": (csv_data, "billing.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "Missing columns" in resp.get_json()["error"]

    @patch("fee_calculator.routes._get_db_connection")
    def test_valid_csv(self, mock_conn, client):
        """Valid CSV with required columns should parse and return results."""
        import pandas as pd

        # Mock AUM lookup to return empty (will fall back to CSV billable)
        mock_conn.return_value = MagicMock()
        with patch("pandas.read_sql", return_value=pd.DataFrame(columns=["acct", "tav"])):
            csv_data = self._make_csv([
                {"AVHHID": 1001, "Account Number": "A1", "Billable Value": "$1,000,000", "Gross Billed Amount": "$2,500", "Billing Definitions": "GM Schedule New", "Advisor": "Alice"},
                {"AVHHID": 1001, "Account Number": "A2", "Billable Value": "$500,000", "Gross Billed Amount": "$1,200", "Billing Definitions": "GM Schedule New", "Advisor": "Alice"},
                {"AVHHID": 1002, "Account Number": "A3", "Billable Value": "$2,000,000", "Gross Billed Amount": "$5,000", "Billing Definitions": "Elite Tier", "Advisor": "Bob"},
            ])
            resp = client.post(
                "/fee-calculator/api/upload-billing",
                data={"file": (csv_data, "billing.csv")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        result = data["data"]

        # Summary — 2 unique households
        assert result["summary"]["total_households"] == 2
        # 2 rows: (1001, "GM Schedule New") and (1002, "Elite Tier")
        assert result["total_returned"] == 2

        # Schedule summary has all schedules
        assert len(result["schedule_summary"]) == len(ALL_SCHEDULES)

        # Households have expected keys
        hh = result["households"][0]
        assert "avhhid" in hh
        assert "current_annual_fee" in hh
        assert "proposed" in hh
        assert "auto_schedule" in hh
        assert "billing_def" in hh

    @patch("fee_calculator.routes._get_db_connection")
    def test_waived_detection(self, mock_conn, client):
        """Accounts with 'waiv' in billing def get their own group row."""
        import pandas as pd

        mock_conn.return_value = MagicMock()
        with patch("pandas.read_sql", return_value=pd.DataFrame(columns=["acct", "tav"])):
            csv_data = self._make_csv([
                {"AVHHID": 1001, "Account Number": "A1", "Billable Value": "$1,000,000", "Gross Billed Amount": "$2,500", "Billing Definitions": "GM Schedule New"},
                {"AVHHID": 1001, "Account Number": "A2", "Billable Value": "$200,000", "Gross Billed Amount": "$0", "Billing Definitions": "Fee Waived"},
            ])
            resp = client.post(
                "/fee-calculator/api/upload-billing",
                data={"file": (csv_data, "billing.csv")},
                content_type="multipart/form-data",
            )

        assert resp.status_code == 200
        hhs = resp.get_json()["data"]["households"]
        # 1 HH, 2 billing defs → 2 rows
        assert len(hhs) == 2
        waived_row = [h for h in hhs if h["has_waived"]][0]
        non_waived_row = [h for h in hhs if not h["has_waived"]][0]
        assert waived_row["total_billable"] == 200_000.0
        assert non_waived_row["total_billable"] == 1_000_000.0

    def test_unsupported_file_type(self, client):
        buf = io.BytesIO(b"not a csv")
        resp = client.post(
            "/fee-calculator/api/upload-billing",
            data={"file": (buf, "data.txt")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400
        assert "Unsupported" in resp.get_json()["error"]


class TestCachedBillingEndpoint:
    """GET /fee-calculator/api/billing-data."""

    def test_no_cache_returns_404(self, client):
        resp = client.get("/fee-calculator/api/billing-data")
        assert resp.status_code == 404

    @patch("fee_calculator.routes._get_db_connection")
    def test_returns_cached_after_upload(self, mock_conn, client):
        """After a successful upload, GET billing-data returns cached result."""
        import pandas as pd

        mock_conn.return_value = MagicMock()
        with patch("pandas.read_sql", return_value=pd.DataFrame(columns=["acct", "tav"])):
            csv_buf = io.BytesIO(
                b"AVHHID,Billable Value,Gross Billed Amount\n1001,$1000000,$2500\n"
            )
            client.post(
                "/fee-calculator/api/upload-billing",
                data={"file": (csv_buf, "billing.csv")},
                content_type="multipart/form-data",
            )

        resp = client.get("/fee-calculator/api/billing-data")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True
