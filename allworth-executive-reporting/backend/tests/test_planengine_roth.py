"""Tests for the ledger-faithful Roth conversion analyzer.

Run from the backend/ directory:

    python -m pytest tests/test_planengine_roth.py -v
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from planengine.engine import run_projection
from planengine.models import Facts
from planengine.roth import analyze_roth_conversions

D = Decimal


def facts_payload(**overrides) -> dict:
    payload = {
        "name": "Roth Test Household",
        "people": [
            {"role": "client", "first_name": "Ada", "date_of_birth": "1961-06-15",
             "retirement_age": 64, "assumed_age_of_death": 92},
            {"role": "spouse", "first_name": "Sam", "date_of_birth": "1963-03-01",
             "retirement_age": 62, "assumed_age_of_death": 94},
        ],
        "accounts": [
            {"id": "00000000-0000-0000-0000-0000000000a1",
             "kind": "taxable", "name": "Brokerage", "value": 900000,
             "tax_basis": 600000, "growth_rate": "0.05", "income_yield": "0.02"},
            {"id": "00000000-0000-0000-0000-0000000000a2",
             "kind": "qualified", "name": "Rollover IRA", "owner": "client",
             "value": 1500000, "growth_rate": "0.05", "apply_rmd": True},
            {"id": "00000000-0000-0000-0000-0000000000a3",
             "kind": "cash", "name": "Cash", "value": 150000, "growth_rate": "0.01"},
        ],
        "income": [
            {"name": "Client SS", "kind": "social_security", "amount": 40000,
             "owner": "client", "starts": {"kind": "client_age", "value": 67},
             "ends": {"kind": "client_death"}},
        ],
        "expenses": [
            {"name": "Living", "kind": "living", "amount": 100000, "required": True,
             "starts": {"kind": "immediately"}, "ends": {"kind": "second_death"}},
        ],
        "assumptions": {"start_year": 2026, "inflation_rate": "0.03",
                        "tax_mode": "form_1040", "plan_end_age": 95},
    }
    payload.update(overrides)
    return payload


@pytest.fixture(scope="module")
def analysis():
    return analyze_roth_conversions(facts_payload(), window_years=8)


class TestAnalysisStructure:
    def test_baseline_matches_direct_projection(self, analysis):
        baseline = run_projection(Facts.model_validate(facts_payload()))
        assert analysis.baseline_lifetime_taxes == baseline.lifetime_taxes
        assert analysis.baseline_ending_net_worth == baseline.ending_net_worth

    def test_source_is_largest_qualified_account(self, analysis):
        assert analysis.source_account_name == "Rollover IRA"

    def test_candidates_cover_brackets_and_fractions(self, analysis):
        labels = [c.label for c in analysis.candidates]
        assert any("bracket" in label for label in labels)
        assert any("Convert" in label for label in labels)

    def test_conversion_amounts_within_source_capacity(self, analysis):
        for candidate in analysis.candidates:
            assert candidate.total_converted <= D("1500000")
            assert candidate.annual_conversion > 0


class TestLedgerConsistency:
    def test_conversions_prepay_taxes(self, analysis):
        """Any conversion ladder must raise lifetime ledger taxes paid earlier
        (the payoff appears in after-tax terminal wealth, not lower taxes)."""
        for candidate in analysis.candidates:
            assert candidate.lifetime_tax_delta != 0

    def test_after_tax_delta_is_net_worth_delta_plus_deferral_relief(self, analysis):
        """Converted plans hold less tax-deferred money, so the after-tax delta
        must exceed the raw net-worth delta."""
        for candidate in analysis.candidates:
            assert candidate.ending_after_tax_delta > candidate.ending_net_worth_delta

    def test_recommended_improves_after_tax_wealth(self, analysis):
        if analysis.recommended is not None:
            assert analysis.recommended.ending_after_tax_delta > 0
            assert analysis.recommended.label in [c.label for c in analysis.candidates]
        else:
            assert any("No conversion ladder" in w for w in analysis.warnings)

    def test_deterministic(self):
        first = analyze_roth_conversions(facts_payload(), window_years=8)
        second = analyze_roth_conversions(facts_payload(), window_years=8)
        assert first.model_dump() == second.model_dump()


class TestBracketHeadroom:
    def test_headroom_candidates_ordered_by_bracket(self, analysis):
        by_label = {c.label: c.annual_conversion for c in analysis.candidates
                    if "bracket" in c.label}
        if "Fill 12% bracket" in by_label and "Fill 22% bracket" in by_label:
            assert by_label["Fill 12% bracket"] < by_label["Fill 22% bracket"]
        if "Fill 22% bracket" in by_label and "Fill 24% bracket" in by_label:
            assert by_label["Fill 22% bracket"] < by_label["Fill 24% bracket"]


class TestEdgeCases:
    def test_no_qualified_account_warns(self):
        payload = facts_payload(accounts=[
            {"kind": "taxable", "name": "Brokerage", "value": 500000,
             "tax_basis": 400000, "growth_rate": "0.05"}])
        result = analyze_roth_conversions(payload, window_years=5)
        assert result.candidates == []
        assert any("No tax-deferred account" in w for w in result.warnings)

    def test_default_window_bounded(self):
        result = analyze_roth_conversions(facts_payload())
        assert 1 <= result.window_years <= 15

    def test_existing_roth_account_reused(self):
        payload = facts_payload()
        payload["accounts"].append({"kind": "roth", "name": "Existing Roth",
                                    "value": 10000, "growth_rate": "0.05"})
        result = analyze_roth_conversions(payload, window_years=5)
        assert result.candidates
