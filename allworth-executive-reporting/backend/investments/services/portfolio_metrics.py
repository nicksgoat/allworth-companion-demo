"""Fact-sheet portfolio metrics for the sample bond portfolio generator.

Pure functions over the canonical :class:`app.models.bond.Bond`. These implement
the exact metrics shown on the Allworth bond-ladder fact sheets:

- Investment: portfolio value, cash invested, total face value, number of securities
- Income: annual taxable vs tax-exempt interest income
- Yields: market-value-weighted YTW / YTM, tax-equivalent YTW / YTM
- Credit: average credit quality (notch label) and grade distribution
- Estimated annual & cumulative income by year

Yield-to-maturity is computed here (Newton-Raphson with a bisection fallback)
because the security master does not carry a reliable YTM column.

See docs/Sample_Bond_Portfolio_Generator_Spec.md for the formulas.
"""

from __future__ import annotations

import math
from datetime import date

from investments.models.bond import Bond, normalize_rating, rank_to_rating, rating_rank

DEFAULT_TAX_RATE = 0.37

# Fitch 22-notch scale, ordered best → worst, parallel to the Moody's scale
# used internally for ranking.  Displayed labels use Fitch notation.
_FITCH_SCALE: list[str] = [
    "AAA",
    "AA+", "AA", "AA-",
    "A+",  "A",  "A-",
    "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-",
    "B+",  "B",  "B-",
    "CCC+", "CCC", "CCC-",
    "CC", "C", "D",
]


def rank_to_fitch_rating(rank: float) -> str:
    """Convert a numeric rank (0 = AAA, 21 = D) to a Fitch-style label."""
    idx = max(0, min(len(_FITCH_SCALE) - 1, round(rank)))
    return _FITCH_SCALE[idx]

# Coupon payments per year keyed by the free-text frequency label.
_FREQ_PER_YEAR = {
    "monthly": 12,
    "quarterly": 4,
    "semi-annual": 2,
    "semiannual": 2,
    "semi annual": 2,
    "annual": 1,
    "annually": 1,
    "yearly": 1,
}

# Moody's notch -> fact-sheet letter grade.
_GRADE_ORDER = ["AAA", "AA", "A", "BBB", "BB and Lower", "Unrated"]


def _freq_per_year(frequency: str | None) -> int:
    return _FREQ_PER_YEAR.get((frequency or "").strip().lower(), 2)


def years_to_maturity(bond: Bond, as_of: date) -> float | None:
    if not bond.maturity_date:
        return None
    return (bond.maturity_date - as_of).days / 365.25


# ---------------------------------------------------------------------------
# Yield to maturity / yield to call
# ---------------------------------------------------------------------------

def _price_from_yield(periodic_yield: float, coupon_per_period: float, periods: int, redemption: float) -> float:
    """Present value (per 100 face) of the bond's cash flows at a periodic yield."""
    if periodic_yield <= -0.999999:
        return math.inf
    discount = 1.0 + periodic_yield
    pv = 0.0
    factor = 1.0
    for _ in range(periods):
        factor *= discount
        pv += coupon_per_period / factor
    pv += redemption / factor
    return pv


def _price_derivative(periodic_yield: float, coupon_per_period: float, periods: int, redemption: float) -> float:
    discount = 1.0 + periodic_yield
    deriv = 0.0
    for k in range(1, periods + 1):
        deriv -= k * coupon_per_period / discount ** (k + 1)
    deriv -= periods * redemption / discount ** (periods + 1)
    return deriv


def solve_yield(
    price: float,
    coupon_rate: float,
    years: float,
    *,
    frequency: int = 2,
    redemption: float = 100.0,
) -> float | None:
    """Annualized yield (percent) that discounts the cash flows to ``price``.

    ``price`` and ``redemption`` are per 100 face; ``coupon_rate`` is the annual
    coupon in percent. Uses Newton-Raphson seeded at the coupon rate, falling
    back to bisection on [1e-6, 1.0] periodic yield.
    """
    if price is None or price <= 0 or years is None or years <= 0:
        return None
    periods = max(1, round(years * frequency))
    coupon_per_period = (coupon_rate / 100.0) * 100.0 / frequency

    # Newton-Raphson
    i = max((coupon_rate / 100.0) / frequency, 1e-4)
    for _ in range(100):
        pv = _price_from_yield(i, coupon_per_period, periods, redemption)
        if not math.isfinite(pv):
            break
        deriv = _price_derivative(i, coupon_per_period, periods, redemption)
        if deriv == 0:
            break
        step = (pv - price) / deriv
        i_new = i - step
        if not math.isfinite(i_new):
            break
        if abs(i_new - i) < 1e-10:
            i = i_new
            break
        i = i_new

    if not (math.isfinite(i)) or i <= -0.99:
        i = None

    # Bisection fallback for robustness.
    if i is None or abs(_price_from_yield(i, coupon_per_period, periods, redemption) - price) > 1e-4:
        lo, hi = 1e-6, 1.0
        f_lo = _price_from_yield(lo, coupon_per_period, periods, redemption) - price
        f_hi = _price_from_yield(hi, coupon_per_period, periods, redemption) - price
        if f_lo * f_hi <= 0:
            for _ in range(200):
                mid = (lo + hi) / 2
                f_mid = _price_from_yield(mid, coupon_per_period, periods, redemption) - price
                if abs(f_mid) < 1e-9:
                    lo = hi = mid
                    break
                if f_lo * f_mid < 0:
                    hi = mid
                    f_hi = f_mid
                else:
                    lo = mid
                    f_lo = f_mid
            i = (lo + hi) / 2

    if i is None or not math.isfinite(i):
        return None
    return i * frequency * 100.0


def bond_ytm(bond: Bond, as_of: date) -> float | None:
    """Yield to maturity (percent) computed from clean price and cash flows."""
    years = years_to_maturity(bond, as_of)
    if years is None or bond.price is None or bond.coupon is None:
        return None
    return solve_yield(bond.price, bond.coupon, years, frequency=_freq_per_year(bond.income_frequency))


def bond_ytw(bond: Bond, as_of: date) -> float | None:
    """Yield to worst — the stored value when present, else min(YTM, YTC)."""
    if bond.yield_to_worst is not None:
        return bond.yield_to_worst
    ytm = bond_ytm(bond, as_of)
    if not bond.callable or not bond.call_date or bond.price is None or bond.coupon is None:
        return ytm
    call_years = (bond.call_date - as_of).days / 365.25
    ytc = solve_yield(
        bond.price,
        bond.coupon,
        call_years,
        frequency=_freq_per_year(bond.income_frequency),
        redemption=bond.call_price if bond.call_price is not None else 100.0,
    )
    candidates = [y for y in (ytm, ytc) if y is not None]
    return min(candidates) if candidates else None


# ---------------------------------------------------------------------------
# Portfolio aggregates
# ---------------------------------------------------------------------------

def _weighted_average(pairs: list[tuple[float, float]]) -> float | None:
    total_weight = sum(w for _, w in pairs if w > 0)
    if total_weight <= 0:
        return None
    return sum(v * w for v, w in pairs if w > 0) / total_weight


def _is_tax_exempt(bond: Bond) -> bool:
    """Federally tax-exempt when explicitly flagged, else inferred from sector."""
    if bond.federal_taxable is False:
        return True
    if bond.federal_taxable is True:
        return False
    sector = (bond.sector or "").lower()
    return "muni" in sector or "municipal" in sector


def annual_income(bond: Bond) -> float:
    """Annual coupon income = coupon% * face."""
    if bond.coupon is not None and bond.quantity is not None:
        return bond.coupon / 100.0 * bond.quantity
    return bond.effective_annual_income()


def grade_of(bond: Bond) -> str:
    """Collapse a bond's best rating to a fact-sheet letter grade."""
    canonical = normalize_rating(bond.best_rating)
    if canonical is None:
        return "Unrated"
    if canonical == "Aaa":
        return "AAA"
    if canonical.startswith("Aa"):
        return "AA"
    if canonical.startswith("A"):
        return "A"
    if canonical.startswith("Baa"):
        return "BBB"
    return "BB and Lower"


def credit_quality_distribution(bonds: list[Bond]) -> list[dict]:
    """Market-value percentage per fact-sheet credit grade (all grades present)."""
    totals: dict[str, float] = {grade: 0.0 for grade in _GRADE_ORDER}
    grand_total = sum(b.effective_market_value() for b in bonds) or 1.0
    for bond in bonds:
        totals[grade_of(bond)] += bond.effective_market_value()
    return [
        {"grade": grade, "pct": round(totals[grade] / grand_total * 100.0, 2)}
        for grade in _GRADE_ORDER
    ]


def average_credit_quality(bonds: list[Bond]) -> str | None:
    """MV-weighted average credit quality returned as a Fitch-scale label (AA+, A, etc.)."""
    pairs = [
        (float(rating_rank(b.best_rating)), b.effective_market_value())
        for b in bonds
        if rating_rank(b.best_rating) is not None
    ]
    avg_rank = _weighted_average(pairs)
    return rank_to_fitch_rating(avg_rank) if avg_rank is not None else None


def compute_metrics(
    bonds: list[Bond],
    *,
    as_of: date | None = None,
    tax_rate: float = DEFAULT_TAX_RATE,
) -> dict:
    """All fact-sheet metrics for a sample portfolio."""
    as_of = as_of or date.today()

    market_value = sum(b.effective_market_value() for b in bonds)
    cash_invested = sum(
        (b.price / 100.0 * b.quantity)
        for b in bonds
        if b.price is not None and b.quantity is not None
    )
    total_face = sum(b.quantity for b in bonds if b.quantity is not None)

    taxable_income = sum(annual_income(b) for b in bonds if not _is_tax_exempt(b))
    exempt_income = sum(annual_income(b) for b in bonds if _is_tax_exempt(b))

    ytw_pairs, ytm_pairs, tey_ytw_pairs, tey_ytm_pairs = [], [], [], []
    for b in bonds:
        mv = b.effective_market_value()
        ytw = bond_ytw(b, as_of)
        ytm = bond_ytm(b, as_of)
        gross = 1.0 / (1.0 - tax_rate) if _is_tax_exempt(b) else 1.0
        if ytw is not None:
            ytw_pairs.append((ytw, mv))
            tey_ytw_pairs.append((ytw * gross, mv))
        if ytm is not None:
            ytm_pairs.append((ytm, mv))
            tey_ytm_pairs.append((ytm * gross, mv))

    def _r(value: float | None, digits: int) -> float | None:
        return round(value, digits) if value is not None else None

    return {
        "portfolio_value": round(market_value, 2),
        "cash_invested": round(cash_invested, 2),
        "total_face_value": round(total_face, 2),
        "number_of_securities": len(bonds),
        "annual_taxable_income": round(taxable_income, 2),
        "annual_tax_exempt_income": round(exempt_income, 2),
        "yield_to_worst": _r(_weighted_average(ytw_pairs), 3),
        "yield_to_maturity": _r(_weighted_average(ytm_pairs), 3),
        "tax_equivalent_ytw": _r(_weighted_average(tey_ytw_pairs), 3),
        "tax_equivalent_ytm": _r(_weighted_average(tey_ytm_pairs), 3),
        "average_credit_quality": average_credit_quality(bonds),
        "investor_federal_tax_rate": round(tax_rate * 100.0, 1),
        "credit_quality_distribution": credit_quality_distribution(bonds),
        "income_schedule": income_schedule(bonds, as_of=as_of),
    }


def income_schedule(bonds: list[Bond], *, as_of: date | None = None) -> list[dict]:
    """Estimated annual & cumulative coupon income per calendar year to maturity."""
    as_of = as_of or date.today()
    maturities = [b.maturity_date.year for b in bonds if b.maturity_date]
    if not maturities:
        return []
    last_year = max(maturities)
    rows: list[dict] = []
    cumulative = 0.0
    for year in range(as_of.year, last_year + 1):
        annual = sum(
            annual_income(b)
            for b in bonds
            if b.maturity_date and b.maturity_date.year >= year
        )
        cumulative += annual
        rows.append({"year": year, "annual": round(annual, 2), "cumulative": round(cumulative, 2)})
    return rows
