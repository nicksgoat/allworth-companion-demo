"""Named retirement strategy optimizers from the extended specification."""

from dataclasses import dataclass
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class SocialSecurityChoice:
    client_claim_age: int
    spouse_claim_age: int
    expected_lifetime_benefit: Decimal


def optimize_social_security(client_pia: Decimal, spouse_pia: Decimal,
                             client_longevity: int = 92, spouse_longevity: int = 94,
                             discount_rate: Decimal = D("0.02")) -> SocialSecurityChoice:
    from .tax.ss import claiming_adjustment
    best = SocialSecurityChoice(62, 62, D("-1"))
    for ca in range(62, 71):
        for sa in range(62, 71):
            c = D(client_pia) * claiming_adjustment(ca) * max(0, client_longevity - ca)
            s = D(spouse_pia) * claiming_adjustment(sa) * max(0, spouse_longevity - sa)
            pv = (c + s) / ((D("1") + D(discount_rate)) ** max(0, min(ca, sa) - 62))
            if pv > best.expected_lifetime_benefit: best = SocialSecurityChoice(ca, sa, pv)
    return best


def inherited_ira_schedules(balance: Decimal, years: int = 10,
                            growth: Decimal = D("0.05")) -> dict[str, list[Decimal]]:
    balance = D(balance)
    even = [balance / years] * years
    front = [balance / D("2")] + [balance / D("2") / (years - 1)] * (years - 1)
    back = [D("0")] * (years - 1) + [balance * ((D("1") + D(growth)) ** years)]
    return {"front_loaded": front, "even": even, "back_loaded": back}


@dataclass(frozen=True)
class NUAResult:
    rollover_tax: Decimal
    nua_tax: Decimal
    estimated_savings: Decimal


def analyze_nua(cost_basis: Decimal, market_value: Decimal, ordinary_rate: Decimal,
                ltcg_rate: Decimal) -> NUAResult:
    rollover = D(market_value) * D(ordinary_rate)
    nua = D(cost_basis) * D(ordinary_rate) + max(D("0"), D(market_value) - D(cost_basis)) * D(ltcg_rate)
    return NUAResult(rollover, nua, rollover - nua)
