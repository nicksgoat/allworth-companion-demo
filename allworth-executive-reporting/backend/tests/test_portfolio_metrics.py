"""Tests for the fact-sheet portfolio metrics engine."""

from __future__ import annotations

from datetime import date

from investments.models.bond import Bond, CreditRating
from investments.services import portfolio_metrics as pm

AS_OF = date(2026, 6, 24)


def _bond(**kw) -> Bond:
    defaults = dict(price=100.0, income_frequency="Semi-Annual")
    defaults.update(kw)
    return Bond(**defaults)


def test_solve_yield_par_bond_equals_coupon():
    # A bond priced at par yields approximately its coupon rate.
    y = pm.solve_yield(price=100.0, coupon_rate=4.0, years=5.0, frequency=2)
    assert y is not None
    assert abs(y - 4.0) < 0.02


def test_solve_yield_discount_bond_above_coupon():
    # Priced below par -> yield above coupon.
    y = pm.solve_yield(price=95.0, coupon_rate=4.0, years=5.0, frequency=2)
    assert y is not None
    assert y > 4.0


def test_solve_yield_premium_bond_below_coupon():
    y = pm.solve_yield(price=105.0, coupon_rate=4.0, years=5.0, frequency=2)
    assert y is not None
    assert y < 4.0


def test_bond_ytm_matches_solver():
    b = _bond(coupon=5.0, price=100.0, maturity_date=date(2031, 6, 24))
    ytm = pm.bond_ytm(b, AS_OF)
    assert ytm is not None
    assert abs(ytm - 5.0) < 0.05


def test_ytw_prefers_stored_value():
    b = _bond(coupon=4.0, price=99.0, yield_to_worst=4.12, maturity_date=date(2031, 6, 24))
    assert pm.bond_ytw(b, AS_OF) == 4.12


def test_tax_equivalent_yield_for_muni():
    # Municipal (tax-exempt) YTW 2.777% grosses up to ~4.408% at a 37% rate.
    muni = _bond(
        coupon=3.0,
        price=100.0,
        quantity=1_000_000,
        yield_to_worst=2.777,
        maturity_date=date(2031, 6, 24),
        federal_taxable=False,
        sector="Municipal",
    )
    m = pm.compute_metrics([muni], as_of=AS_OF, tax_rate=0.37)
    assert m["annual_tax_exempt_income"] > 0
    assert m["annual_taxable_income"] == 0
    assert abs(m["tax_equivalent_ytw"] - 4.408) < 0.01


def test_taxable_income_split_for_treasury():
    treasury = _bond(
        coupon=4.175,
        price=100.0,
        quantity=1_000_000,
        yield_to_worst=4.121,
        maturity_date=date(2031, 6, 24),
        federal_taxable=True,
        sector="US Treasury",
    )
    m = pm.compute_metrics([treasury], as_of=AS_OF, tax_rate=0.37)
    assert abs(m["annual_taxable_income"] - 41_750) < 1.0
    assert m["annual_tax_exempt_income"] == 0
    # Taxable bond: tax-equivalent yield equals the nominal yield.
    assert abs(m["tax_equivalent_ytw"] - m["yield_to_worst"]) < 1e-6


def test_credit_quality_distribution_sums_to_100():
    bonds = [
        _bond(coupon=3, quantity=100_000, maturity_date=date(2029, 1, 1),
              ratings=[CreditRating(agency="Moody's", current="Aaa")]),
        _bond(coupon=3, quantity=100_000, maturity_date=date(2029, 1, 1),
              ratings=[CreditRating(agency="Moody's", current="Aa2")]),
        _bond(coupon=3, quantity=100_000, maturity_date=date(2029, 1, 1),
              ratings=[CreditRating(agency="Moody's", current="A3")]),
    ]
    dist = pm.credit_quality_distribution(bonds)
    grades = {row["grade"]: row["pct"] for row in dist}
    assert abs(sum(grades.values()) - 100.0) < 0.1
    assert grades["AAA"] > 0 and grades["AA"] > 0 and grades["A"] > 0
    assert grades["BBB"] == 0


def test_average_credit_quality_label():
    bonds = [
        _bond(coupon=3, quantity=100_000, maturity_date=date(2029, 1, 1),
              ratings=[CreditRating(agency="Moody's", current="A1")]),
        _bond(coupon=3, quantity=100_000, maturity_date=date(2029, 1, 1),
              ratings=[CreditRating(agency="Moody's", current="A1")]),
    ]
    assert pm.average_credit_quality(bonds) == "A+"  # Fitch label for Moody's A1 rank


def test_income_schedule_is_decreasing_and_cumulative():
    bonds = [
        _bond(coupon=4, quantity=100_000, maturity_date=date(2028, 6, 24)),
        _bond(coupon=4, quantity=100_000, maturity_date=date(2030, 6, 24)),
    ]
    schedule = pm.income_schedule(bonds, as_of=AS_OF)
    assert schedule[0]["year"] == 2026
    # Annual income should not increase over time (bonds mature, no reinvestment).
    annuals = [row["annual"] for row in schedule]
    assert annuals == sorted(annuals, reverse=True)
    # Cumulative is monotonically non-decreasing.
    cumulative = [row["cumulative"] for row in schedule]
    assert cumulative == sorted(cumulative)


def test_metrics_totals():
    bonds = [
        _bond(coupon=4, price=100.0, quantity=500_000, maturity_date=date(2029, 6, 24),
              federal_taxable=True),
        _bond(coupon=5, price=100.0, quantity=500_000, maturity_date=date(2031, 6, 24),
              federal_taxable=True),
    ]
    m = pm.compute_metrics(bonds, as_of=AS_OF)
    assert m["number_of_securities"] == 2
    assert abs(m["total_face_value"] - 1_000_000) < 1
    assert abs(m["portfolio_value"] - 1_000_000) < 1
    assert abs(m["cash_invested"] - 1_000_000) < 1
