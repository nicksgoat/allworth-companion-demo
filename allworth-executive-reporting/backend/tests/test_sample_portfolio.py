"""Tests for the sample bond portfolio generator (selection + optimizer)."""

from __future__ import annotations

from datetime import date, timedelta

from investments.models.bond import Bond, CreditRating
from investments.services import sample_portfolio as sp

AS_OF = date(2026, 6, 24)


def _make_universe(asset: str, sector: str, rating: str, taxable: bool, n_per_year: int = 5) -> list[Bond]:
    """Build a synthetic universe spanning 1..10 years with several bonds per year."""
    bonds: list[Bond] = []
    for year in range(1, 11):
        for j in range(n_per_year):
            maturity = AS_OF + timedelta(days=int(round(365.25 * year)))
            bonds.append(
                Bond(
                    cusip=f"{asset[:2].upper()}{year:02d}{j}",
                    symbol=f"{asset[:3].upper()}{year}{j}",
                    description=f"{sector} GO bond {year}Y #{j}" if asset == "municipal" else f"{sector} bond {year}Y #{j}",
                    coupon=3.5 + 0.1 * j,
                    price=100.0,
                    yield_to_worst=3.8 + 0.05 * j,
                    maturity_date=maturity,
                    sector=sector,
                    issuer=f"{sector} issuer {year}-{j}",
                    federal_taxable=taxable,
                    ratings=[CreditRating(agency="Moody's", current=rating)],
                )
            )
    return bonds


def test_strategies_registered():
    assert set(sp.STRATEGIES) == {
        "municipal-1-5", "municipal-1-10",
        "treasury-1-5", "treasury-1-10",
        "corporate-1-5", "corporate-1-10",
    }


def test_treasury_1_5_builds_five_bond_ladder():
    universe = _make_universe("treasury", "US Treasury", "Aa2", taxable=True)
    strategy = sp.STRATEGIES["treasury-1-5"]
    portfolio = sp.build_sample_portfolio(universe, strategy, as_of=AS_OF)

    assert portfolio.metrics["number_of_securities"] == 5  # 1 per year, 5 rungs
    # One bond in each maturity year 2027..2031.
    years = sorted({b.maturity_date.year for b in portfolio.bonds})
    assert years == [2027, 2028, 2029, 2030, 2031]
    # Portfolio value is within 5% of target (lot rounding can shift the total slightly).
    assert abs(portfolio.metrics["portfolio_value"] - sp.DEFAULT_TARGET_VALUE) < sp.DEFAULT_TARGET_VALUE * 0.05


def test_corporate_1_5_builds_fifteen_bond_ladder():
    universe = _make_universe("corporate", "Corporate", "A2", taxable=True)
    strategy = sp.STRATEGIES["corporate-1-5"]
    portfolio = sp.build_sample_portfolio(universe, strategy, as_of=AS_OF)
    assert portfolio.metrics["number_of_securities"] == 15  # 3 per year x 5 rungs
    assert portfolio.metrics["annual_taxable_income"] > 0
    assert portfolio.metrics["annual_tax_exempt_income"] == 0


def test_municipal_income_is_tax_exempt():
    universe = _make_universe("municipal", "Municipal", "A1", taxable=False)
    strategy = sp.STRATEGIES["municipal-1-5"]
    portfolio = sp.build_sample_portfolio(universe, strategy, as_of=AS_OF)
    assert portfolio.metrics["annual_tax_exempt_income"] > 0
    assert portfolio.metrics["annual_taxable_income"] == 0
    # Tax-equivalent yield is grossed up above the nominal yield.
    assert portfolio.metrics["tax_equivalent_ytw"] > portfolio.metrics["yield_to_worst"]


def test_optimizer_weights_sum_to_one():
    universe = _make_universe("corporate", "Corporate", "A2", taxable=True)
    strategy = sp.STRATEGIES["corporate-1-5"]
    candidates = sp.filter_candidates(universe, strategy, AS_OF)
    selected = sp.select_ladder(candidates, strategy, AS_OF)
    weights = sp._quality_weights(selected, AS_OF, strategy.target_ytw, 5.0)
    assert abs(sum(weights) - 1.0) < 1e-6
    assert all(w >= 0 for w in weights)


def test_corporate_quality_score_rewards_credit_and_momentum():
    strong = Bond(
        cusip="STRONG",
        description="Strong Company 4.000 06/24/31",
        coupon=4.0,
        price=100.0,
        yield_to_worst=4.2,
        effective_duration=3.0,
        maturity_date=AS_OF + timedelta(days=int(365.25 * 5)),
        sector="Corporate Bonds",
        broad_sector="Corporate Bonds",
        segment="Industrial",
        issuer="Strong Company",
        ratings=[CreditRating(agency="Fitch", current="A", previous="A-")],
    )
    weaker = Bond(
        cusip="WEAKER",
        description="Weaker Company 6.000 06/24/31",
        coupon=6.0,
        price=100.0,
        yield_to_worst=6.0,
        effective_duration=3.0,
        maturity_date=AS_OF + timedelta(days=int(365.25 * 5)),
        sector="Corporate Bonds",
        ratings=[CreditRating(agency="Fitch", current="BBB-", previous="BBB")],
    )

    strong_score, strong_components = sp.corporate_quality_score(strong, 6.0)
    weaker_score, weaker_components = sp.corporate_quality_score(weaker, 6.0)

    assert strong_score > weaker_score
    assert strong_components["credit"] > weaker_components["credit"]
    assert strong_components["momentum"] > weaker_components["momentum"]


def test_corporate_selection_uses_quality_score_over_raw_yield():
    strategy = sp.STRATEGIES["corporate-1-5"]
    maturity = AS_OF + timedelta(days=int(365.25 * 3))
    candidates = [
        Bond(
            cusip=f"GOOD{i}",
            description=f"Quality Company {i} 4.000 06/24/29",
            coupon=4.0,
            price=100.0,
            yield_to_worst=4.0 + i * 0.1,
            effective_duration=3.0,
            maturity_date=maturity,
            sector="Corporate Bonds",
            broad_sector="Corporate Bonds",
            segment="Industrial",
            issuer=f"Quality Company {i}",
            state=f"S{i}",
            ratings=[CreditRating(agency="Fitch", current="A", previous="A")],
        )
        for i in range(3)
    ]
    candidates.append(
        Bond(
            cusip="RISKY",
            description="Risky Company 8.000 06/24/29",
            coupon=8.0,
            price=80.0,
            yield_to_worst=8.0,
            effective_duration=3.0,
            maturity_date=maturity,
            sector="Corporate Bonds",
            state="RX",
            ratings=[CreditRating(agency="Fitch", current="BBB-", previous="BBB")],
        )
    )

    selected = sp.select_ladder(candidates, strategy, AS_OF)

    assert "RISKY" not in {b.cusip for b in selected}
    assert all(b.corporate_quality_score is not None for b in selected)


def test_treasury_filter_excludes_corporates():
    universe = _make_universe("treasury", "US Treasury", "Aa2", taxable=True)
    universe += _make_universe("corporate", "Corporate", "A2", taxable=True)
    strategy = sp.STRATEGIES["treasury-1-5"]
    candidates = sp.filter_candidates(universe, strategy, AS_OF)
    assert candidates
    assert all("treasury" in (b.sector or "").lower() for b in candidates)


def test_empty_universe_raises():
    import pytest

    with pytest.raises(ValueError):
        sp.build_sample_portfolio([], sp.STRATEGIES["treasury-1-5"], as_of=AS_OF)


def test_derive_issuer_strips_coupon_and_maturity():
    # Issuer name is the leading text before the coupon/maturity (Rule 11).
    assert sp._derive_issuer("Abilene Tex Indpt Sch Dist 5.000 02/15/29") == "ABILENE TEX INDPT SCH DIST"
    assert sp._derive_issuer("Apple Inc 3.25 02/23/26") == "APPLE INC"
    # A bare-CUSIP description falls back to the 6-character issuer prefix.
    assert sp._derive_issuer("509628AK9", cusip="509628AK9") == "509628"


def _muni(desc: str, price: float = 101.0, taxable: bool = False) -> Bond:
    return Bond(description=desc, price=price, federal_taxable=taxable, sector="Municipal Bonds")


def test_eligible_muni_go_included_revenue_amt_excluded():
    # GO / school-district issues at or above par are eligible.
    assert sp._eligible_muni(_muni("Abilene Tex Indpt Sch Dist 5.0 02/15/29"))
    assert sp._eligible_muni(_muni("Some City G O Bds 4.0 06/01/30"))
    # Revenue bonds, AMT issues, sub-par, and taxable issues are excluded.
    assert not sp._eligible_muni(_muni("Some Auth Wtr Rev 4.0 06/01/30"))
    assert not sp._eligible_muni(_muni("Some City G O AMT 4.0 06/01/30"))
    assert not sp._eligible_muni(_muni("Some City G O 4.0 06/01/30", price=99.0))
    assert not sp._eligible_muni(_muni("Some City G O 4.0 06/01/30", taxable=True))
    # No GO signal at all -> excluded (GO-only ladders).
    assert not sp._eligible_muni(_muni("Mystery Structure 4.0 06/01/30"))


def test_issuer_uniqueness_enforced_in_selection():
    strategy = sp.STRATEGIES["corporate-1-5"]
    maturity = AS_OF + timedelta(days=int(365.25 * 3))

    def mk(cid: str, issuer: str, ytw: float) -> Bond:
        return Bond(
            cusip=cid,
            description=f"{issuer} 4.0 06/24/29",
            coupon=4.0,
            price=100.0,
            yield_to_worst=ytw,
            effective_duration=3.0,
            maturity_date=maturity,
            sector="Corporate Bonds",
            broad_sector="Corporate Bonds",
            segment="Industrial",
            issuer=issuer,
            ratings=[CreditRating(agency="Fitch", current="A", previous="A")],
        )

    candidates = [
        mk("A1", "Acme Corp", 4.5),
        mk("A2", "Acme Corp", 4.4),
        mk("B1", "Beta Inc", 4.3),
        mk("C1", "Gamma Inc", 4.2),
    ]
    selected = sp.select_ladder(candidates, strategy, AS_OF)
    issuers = [b.issuer for b in selected]
    assert issuers.count("Acme Corp") == 1


def test_strict_rating_excludes_nr_and_below_a_minus():
    strategy = sp.STRATEGIES["corporate-1-5"]
    maturity = AS_OF + timedelta(days=int(365.25 * 2))

    def mk(cid: str, rating: str | None) -> Bond:
        return Bond(
            cusip=cid,
            description=f"{cid} 4.0 06/24/28",
            coupon=4.0,
            price=100.0,
            yield_to_worst=4.0,
            maturity_date=maturity,
            sector="Corporate Bonds",
            issuer=cid,
            ratings=[CreditRating(agency="Fitch", current=rating)] if rating else [],
        )

    universe = [mk("AOK", "A-"), mk("BBB", "BBB+"), mk("NRB", "NR"), mk("NONE", None)]
    kept = {b.cusip for b in sp.filter_candidates(universe, strategy, AS_OF)}
    assert "AOK" in kept
    assert kept.isdisjoint({"BBB", "NRB", "NONE"})


def test_unrated_included_when_rating_screen_off():
    strategy = sp.STRATEGIES["corporate-1-5"]
    maturity = AS_OF + timedelta(days=int(365.25 * 2))

    def mk(cid: str, rating: str | None) -> Bond:
        return Bond(
            cusip=cid,
            description=f"{cid} 4.0 06/24/28",
            coupon=4.0,
            price=100.0,
            yield_to_worst=4.0,
            maturity_date=maturity,
            sector="Corporate Bonds",
            issuer=cid,
            ratings=[CreditRating(agency="Fitch", current=rating)] if rating else [],
        )

    universe = [mk("AOK", "A-"), mk("BBB", "BBB+"), mk("NRB", "NR"), mk("NONE", None)]
    # exclude_unrated=False keeps unrated bonds but still enforces A- where a rating exists.
    kept = {b.cusip for b in sp.filter_candidates(universe, strategy, AS_OF, exclude_unrated=False)}
    assert {"AOK", "NRB", "NONE"} <= kept
    assert "BBB" not in kept
