"""Tests for the analytics engine."""

from __future__ import annotations

from investments.services import analytics


def test_kpis(sample_bonds):
    kpis = analytics.compute_kpis(sample_bonds)
    assert kpis["holdings"] == 3
    assert kpis["market_value"] > 0
    assert kpis["average_coupon"] is not None
    assert 0 <= kpis["health_score"] <= 100
    assert kpis["callable_pct"] > 0


def test_maturity_ladder_sums_to_market_value(sample_bonds):
    ladder = analytics.maturity_ladder(sample_bonds)
    total = sum(row["market_value"] for row in ladder)
    mv = analytics.compute_kpis(sample_bonds)["market_value"]
    assert round(total, 2) == round(mv, 2)


def test_sector_allocation_percentages(sample_bonds):
    rows = analytics.sector_allocation(sample_bonds)
    assert abs(sum(r["pct"] for r in rows) - 100.0) < 0.5


def test_rating_changes_detects_downgrade(sample_bonds):
    changes = analytics.rating_changes(sample_bonds)
    # Bank of America: A3 -> Baa1 is a downgrade.
    downgrades = [c for c in changes if c["direction"] == "downgrade"]
    assert any(c["cusip"] == "333" for c in downgrades)


def test_build_dashboard_has_all_sections(sample_bonds):
    dash = analytics.build_dashboard(sample_bonds)
    for key in (
        "kpis", "maturity_ladder", "call_ladder", "credit_distribution",
        "sector_allocation", "cash_flow", "monthly_income", "upcoming_calls",
    ):
        assert key in dash
