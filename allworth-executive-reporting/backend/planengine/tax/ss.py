"""Social Security benefit approximations for planning (not claiming advice)."""

from decimal import Decimal

D = Decimal


def estimate_pia(aime: Decimal, tables_year: int = 2026) -> Decimal:
    # 2026 projected bend points; kept in one function pending annual table load.
    b1, b2 = D("1286"), D("7752")
    aime = max(D("0"), D(aime))
    return (min(aime, b1) * D("0.90") +
            max(D("0"), min(aime, b2) - b1) * D("0.32") +
            max(D("0"), aime - b2) * D("0.15"))


def claiming_adjustment(claim_age: int, fra: int = 67) -> Decimal:
    months = (claim_age - fra) * 12
    if months >= 0:
        return D("1") + D(min(months, 36)) * D("0.08") / 12
    early = -months
    reduction = min(early, 36) * D("5") / D("900")
    reduction += max(0, early - 36) * D("5") / D("1200")
    return D("1") - reduction


def survivor_benefit(deceased: Decimal, own: Decimal) -> Decimal:
    return max(D(deceased), D(own))
