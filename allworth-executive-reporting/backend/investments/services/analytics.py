"""Portfolio analytics engine.

Pure functions that transform a list of canonical :class:`Bond` objects
into KPIs, distributions, ladders, and forecasts. No I/O, no framework
types — everything here is unit-testable in isolation and reusable by any
API surface.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from investments.models.bond import Bond, rank_to_rating, rating_rank

_MONTHS_PER_FREQ = {
    "monthly": 1,
    "quarterly": 3,
    "semi-annual": 6,
    "semiannual": 6,
    "semi annual": 6,
    "annual": 12,
    "annually": 12,
    "yearly": 12,
}


def _weighted_average(pairs: list[tuple[float, float]]) -> float | None:
    """Weighted average of (value, weight) pairs, ignoring zero weights."""
    total_weight = sum(weight for _, weight in pairs if weight > 0)
    if total_weight <= 0:
        return None
    return sum(value * weight for value, weight in pairs if weight > 0) / total_weight


def _round(value: float | None, digits: int) -> float | None:
    return round(value, digits) if value is not None else None


def compute_kpis(bonds: list[Bond]) -> dict:
    """Headline portfolio KPI cards."""
    market_value = sum(b.effective_market_value() for b in bonds)
    annual_income = sum(b.effective_annual_income() for b in bonds)

    coupon_pairs = [(b.coupon, b.effective_market_value()) for b in bonds if b.coupon is not None]
    yield_pairs = [
        (b.yield_to_worst, b.effective_market_value()) for b in bonds if b.yield_to_worst is not None
    ]
    duration_pairs = [
        (b.effective_duration, b.effective_market_value())
        for b in bonds
        if b.effective_duration is not None
    ]
    rating_pairs = [
        (float(rating_rank(b.best_rating)), b.effective_market_value())
        for b in bonds
        if rating_rank(b.best_rating) is not None
    ]

    avg_rating_rank = _weighted_average(rating_pairs)
    callable_value = sum(b.effective_market_value() for b in bonds if b.callable)

    return {
        "market_value": round(market_value, 2),
        "annual_income": round(annual_income, 2),
        "average_coupon": _round(_weighted_average(coupon_pairs), 3),
        "average_yield": _round(_weighted_average(yield_pairs), 3),
        "average_duration": _round(_weighted_average(duration_pairs), 2),
        "average_rating": rank_to_rating(avg_rating_rank) if avg_rating_rank is not None else None,
        "callable_pct": _round(
            (callable_value / market_value * 100.0) if market_value > 0 else 0.0, 1
        ),
        "holdings": len(bonds),
        "health_score": portfolio_health_score(bonds),
    }


def maturity_ladder(bonds: list[Bond], today: date | None = None) -> list[dict]:
    """Market value bucketed by calendar maturity year."""
    today = today or date.today()
    totals: dict[str, float] = {}
    for bond in bonds:
        if not bond.maturity_date or bond.maturity_date < today:
            continue
        label = str(bond.maturity_date.year)
        totals[label] = totals.get(label, 0.0) + bond.effective_market_value()
    return [{"bucket": label, "market_value": round(totals[label], 2)} for label in sorted(totals)]


def call_ladder(bonds: list[Bond], today: date | None = None) -> list[dict]:
    """Callable market value bucketed by years-to-call."""
    today = today or date.today()
    buckets = [("0-1y", 0, 1), ("1-2y", 1, 2), ("2-3y", 2, 3), ("3-5y", 3, 5), ("5y+", 5, 1_000)]
    totals = {label: 0.0 for label, _, _ in buckets}
    for bond in bonds:
        if not bond.callable or not bond.call_date:
            continue
        years = (bond.call_date - today).days / 365.25
        for label, low, high in buckets:
            if low <= years < high:
                totals[label] += bond.effective_market_value()
                break
    return [{"bucket": label, "market_value": round(totals[label], 2)} for label, _, _ in buckets]


def credit_distribution(bonds: list[Bond]) -> list[dict]:
    """Market value grouped by best rating, ordered high to low quality."""
    totals: dict[str, float] = defaultdict(float)
    for bond in bonds:
        label = bond.best_rating or "NR"
        totals[label] += bond.effective_market_value()

    def sort_key(label: str) -> int:
        rank = rating_rank(label)
        return rank if rank is not None else 999

    return [
        {"rating": label, "market_value": round(value, 2)}
        for label, value in sorted(totals.items(), key=lambda kv: sort_key(kv[0]))
    ]


def _group_allocation(bonds: list[Bond], key) -> list[dict]:
    totals: dict[str, float] = defaultdict(float)
    grand_total = 0.0
    for bond in bonds:
        value = bond.effective_market_value()
        grand_total += value
        totals[key(bond) or "Unclassified"] += value
    rows = [
        {
            "label": label,
            "market_value": round(value, 2),
            "pct": round(value / grand_total * 100.0, 2) if grand_total > 0 else 0.0,
        }
        for label, value in totals.items()
    ]
    return sorted(rows, key=lambda row: row["market_value"], reverse=True)


def sector_allocation(bonds: list[Bond]) -> list[dict]:
    return _group_allocation(bonds, lambda b: b.sector)


def state_allocation(bonds: list[Bond]) -> list[dict]:
    return _group_allocation(bonds, lambda b: b.state)


def issuer_concentration(bonds: list[Bond], top_n: int = 10) -> list[dict]:
    rows = _group_allocation(bonds, lambda b: b.issuer or b.description)
    return rows[:top_n]


def cash_flow_projection(bonds: list[Bond], years: int = 10, today: date | None = None) -> list[dict]:
    """Projected principal returned and income earned per calendar year."""
    today = today or date.today()
    principal: dict[int, float] = defaultdict(float)
    income: dict[int, float] = defaultdict(float)
    for bond in bonds:
        annual = bond.effective_annual_income()
        mv = bond.effective_market_value()
        if bond.maturity_date:
            mat_year = bond.maturity_date.year
            if mat_year >= today.year:
                principal[mat_year] += mv
            for yr in range(today.year, min(mat_year, today.year + years) + 1):
                income[yr] += annual
        else:
            for yr in range(today.year, today.year + years):
                income[yr] += annual

    rows = []
    for yr in range(today.year, today.year + years + 1):
        rows.append(
            {
                "year": yr,
                "principal": round(principal.get(yr, 0.0), 2),
                "income": round(income.get(yr, 0.0), 2),
            }
        )
    return rows


def monthly_income(bonds: list[Bond]) -> list[dict]:
    """Estimated income by calendar month based on payment frequency."""
    totals = [0.0] * 12
    for bond in bonds:
        annual = bond.effective_annual_income()
        if annual <= 0:
            continue
        freq_months = _MONTHS_PER_FREQ.get((bond.income_frequency or "").strip().lower(), 6)
        per_payment = annual / (12 / freq_months)
        if bond.next_income_date:
            # Anchor payment schedule to the known next payment month.
            anchor = bond.next_income_date.month - 1
        else:
            # No anchor: distribute evenly across all payment months starting
            # from January so the chart isn't artificially front-loaded.
            anchor = 0
        month = anchor
        while month < 12:
            totals[month] += per_payment
            month += freq_months
    labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return [{"month": labels[i], "income": round(totals[i], 2)} for i in range(12)]


def _histogram(values: list[float], edges: list[float], labels: list[str]) -> list[dict]:
    counts = [0] * len(labels)
    for value in values:
        for i in range(len(labels)):
            if edges[i] <= value < edges[i + 1]:
                counts[i] += 1
                break
    return [{"bucket": labels[i], "count": counts[i]} for i in range(len(labels))]


def coupon_distribution(bonds: list[Bond]) -> list[dict]:
    edges = [0, 1, 2, 3, 4, 5, 6, 100]
    labels = ["0-1%", "1-2%", "2-3%", "3-4%", "4-5%", "5-6%", "6%+"]
    return _histogram([b.coupon for b in bonds if b.coupon is not None], edges, labels)


def yield_distribution(bonds: list[Bond]) -> list[dict]:
    edges = [0, 1, 2, 3, 4, 5, 6, 100]
    labels = ["0-1%", "1-2%", "2-3%", "3-4%", "4-5%", "5-6%", "6%+"]
    return _histogram(
        [b.yield_to_worst for b in bonds if b.yield_to_worst is not None], edges, labels
    )


def upcoming_calls(bonds: list[Bond], within_days: int = 90, today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = []
    for bond in bonds:
        if not bond.callable or not bond.call_date:
            continue
        days = (bond.call_date - today).days
        if 0 <= days <= within_days:
            rows.append(
                {
                    "cusip": bond.cusip,
                    "description": bond.description,
                    "call_date": bond.call_date.isoformat(),
                    "call_price": bond.call_price,
                    "market_value": round(bond.effective_market_value(), 2),
                    "days_until": days,
                }
            )
    return sorted(rows, key=lambda r: r["days_until"])


def upcoming_maturities(bonds: list[Bond], within_days: int = 180, today: date | None = None) -> list[dict]:
    today = today or date.today()
    rows = []
    for bond in bonds:
        if not bond.maturity_date:
            continue
        days = (bond.maturity_date - today).days
        if 0 <= days <= within_days:
            rows.append(
                {
                    "cusip": bond.cusip,
                    "description": bond.description,
                    "maturity_date": bond.maturity_date.isoformat(),
                    "market_value": round(bond.effective_market_value(), 2),
                    "days_until": days,
                }
            )
    return sorted(rows, key=lambda r: r["days_until"])


def rating_changes(bonds: list[Bond]) -> list[dict]:
    """Detected upgrades/downgrades across all agencies."""
    changes = []
    for bond in bonds:
        for rating in bond.ratings:
            if not rating.changed:
                continue
            cur = rating_rank(rating.current)
            prev = rating_rank(rating.previous)
            if cur is None or prev is None:
                continue
            notches = cur - prev
            changes.append(
                {
                    "cusip": bond.cusip,
                    "description": bond.description,
                    "agency": rating.agency,
                    "from_rating": rating.previous,
                    "to_rating": rating.current,
                    "effective_date": rating.effective_date.isoformat()
                    if rating.effective_date
                    else None,
                    "direction": "downgrade" if notches > 0 else "upgrade",
                    "notches": abs(notches),
                }
            )
    return sorted(changes, key=lambda c: (c["direction"] != "downgrade", -c["notches"]))


def ladder_quality_score(bonds: list[Bond], today: date | None = None) -> float:
    """0-100 score rewarding an even spread of maturities (low concentration)."""
    ladder = maturity_ladder(bonds, today)
    values = [row["market_value"] for row in ladder]
    total = sum(values)
    if total <= 0:
        return 0.0
    shares = [v / total for v in values]
    hhi = sum(s * s for s in shares)
    even = 1 / len(values)
    score = max(0.0, min(100.0, (1 - (hhi - even) / (1 - even)) * 100.0))
    return round(score, 1)


def portfolio_health_score(bonds: list[Bond]) -> float:
    """Composite 0-100 health score across credit, diversification, duration.

    Credit component distinguishes three buckets:
      - Investment grade  → full credit (counts as 100%)
      - Not rated         → partial credit (counts as 50%), ambiguous risk
      - Below investment grade → no credit (counts as 0%), known risk
    """
    if not bonds:
        return 0.0
    total_mv = sum(b.effective_market_value() for b in bonds) or 1.0

    ig_mv = sum(b.effective_market_value() for b in bonds if b.is_investment_grade is True)
    nr_mv = sum(b.effective_market_value() for b in bonds if b.is_investment_grade is None)
    # NR counts at half weight; below-IG counts as 0.
    credit = (ig_mv + nr_mv * 0.5) / total_mv * 100.0

    issuers = issuer_concentration(bonds, top_n=1)
    top_issuer_pct = issuers[0]["pct"] if issuers else 100.0
    diversification = max(0.0, 100.0 - max(0.0, top_issuer_pct - 10.0) * 2.0)

    ladder = ladder_quality_score(bonds)

    dur_pairs = [
        (b.effective_duration, b.effective_market_value())
        for b in bonds
        if b.effective_duration is not None
    ]
    avg_dur = _weighted_average(dur_pairs)
    duration = 70.0 if avg_dur is None else max(0.0, 100.0 - abs(avg_dur - 5.0) * 8.0)

    score = credit * 0.35 + diversification * 0.25 + ladder * 0.20 + duration * 0.20
    return round(max(0.0, min(100.0, score)), 1)


def build_dashboard(bonds: list[Bond], today: date | None = None) -> dict:
    """Aggregate every analytic the dashboard needs in one payload."""
    return {
        "kpis": compute_kpis(bonds),
        "maturity_ladder": maturity_ladder(bonds, today),
        "call_ladder": call_ladder(bonds, today),
        "credit_distribution": credit_distribution(bonds),
        "sector_allocation": sector_allocation(bonds),
        "state_allocation": state_allocation(bonds),
        "issuer_concentration": issuer_concentration(bonds),
        "cash_flow": cash_flow_projection(bonds, today=today),
        "monthly_income": monthly_income(bonds),
        "coupon_distribution": coupon_distribution(bonds),
        "yield_distribution": yield_distribution(bonds),
        "upcoming_calls": upcoming_calls(bonds, today=today),
        "upcoming_maturities": upcoming_maturities(bonds, today=today),
        "rating_changes": rating_changes(bonds),
        "ladder_quality_score": ladder_quality_score(bonds, today),
    }
