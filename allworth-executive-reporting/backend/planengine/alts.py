"""Alternative-asset annual mechanics and tax-character contracts."""

from dataclasses import dataclass
from decimal import Decimal
import random

D = Decimal


@dataclass
class TaxCharacterVector:
    ordinary: Decimal = D("0")
    qualified_dividends: Decimal = D("0")
    st_capital_gain: Decimal = D("0")
    lt_capital_gain: Decimal = D("0")
    sec1256_gain: Decimal = D("0")
    collectibles_gain: Decimal = D("0")
    unrecaptured_1250: Decimal = D("0")
    sec1231_gain: Decimal = D("0")
    return_of_capital: Decimal = D("0")
    tax_exempt: Decimal = D("0")
    ubti: Decimal = D("0")
    foreign_tax_paid: Decimal = D("0")
    sec988_ordinary: Decimal = D("0")
    deferred: Decimal = D("0")


@dataclass
class HedgeFundYear:
    ending_nav: Decimal
    distributions: Decimal
    net_investment_gain: Decimal
    tax_character: TaxCharacterVector


def hedge_fund_year(nav: Decimal, gross_return: Decimal, strategy: str,
                    mgmt_fee: Decimal = D("0.015"), incentive_fee: Decimal = D("0.20")) -> HedgeFundYear:
    nav, gross_return = D(nav), D(gross_return)
    gross = nav * gross_return
    fees = nav * D(mgmt_fee) + max(D("0"), gross - nav * D(mgmt_fee)) * D(incentive_fee)
    net = gross - fees
    # High-turnover L/S defaults; remaining return is deferred appreciation.
    profiles = {
        "long_short_equity": (D("0.15"), D("0.10"), D("0.40"), D("0.15")),
        "market_neutral": (D("0.30"), D("0.05"), D("0.45"), D("0.05")),
        "credit": (D("0.55"), D("0.05"), D("0.15"), D("0.10")),
    }
    ordinary, qd, st, lt = profiles.get(strategy, profiles["long_short_equity"])
    deferred = D("1") - ordinary - qd - st - lt
    v = TaxCharacterVector(ordinary=net * ordinary, qualified_dividends=net * qd,
                           st_capital_gain=net * st, lt_capital_gain=net * lt,
                           deferred=net * deferred)
    return HedgeFundYear(nav + net, D("0"), net, v)


@dataclass
class Redemption:
    received_this_year: Decimal
    queued: Decimal


def redeem(nav: Decimal, requested: Decimal, redemption_frequency: str,
           gate_pct: Decimal, windows_available_this_year: int = 1) -> Redemption:
    capacity = D(nav) * D(gate_pct) * max(1, windows_available_this_year)
    received = min(D(requested), capacity)
    # queued remains nonzero when a request exceeds one window even if the
    # annual aggregate can service it, because later windows are pending.
    queued = max(D("0"), D(requested) - D(nav) * D(gate_pct))
    return Redemption(received, queued)


@dataclass
class PEYear:
    year: int
    capital_call: Decimal
    distribution: Decimal
    nav: Decimal


def pe_pacing_schedule(committed: Decimal, rate_of_contribution: Decimal,
                       bow: Decimal, fund_life: int, growth: Decimal) -> list[PEYear]:
    committed = D(committed)
    # Yale/Takahashi-inspired declining contribution weights, normalized so
    # calls conserve the commitment exactly.
    raw = [(D("1") - D(rate_of_contribution)) ** i for i in range(fund_life)]
    scale = committed / sum(raw, D("0"))
    calls = [x * scale for x in raw]
    nav, rows = D("0"), []
    for i, call in enumerate(calls):
        nav = (nav + call) * (D("1") + D(growth))
        dist_rate = (D(i + 1) / D(fund_life)) ** D(bow)
        distribution = nav * min(D("0.85"), dist_rate)
        nav -= distribution
        rows.append(PEYear(i + 1, call, distribution, nav))
    if rows and rows[-1].nav:
        rows[-1].distribution += rows[-1].nav
        rows[-1].nav = D("0")
    return rows


@dataclass
class LongShortYear:
    ending_value: Decimal
    pre_tax_return: Decimal
    tax_character: TaxCharacterVector
    investment_interest_expense: Decimal


def long_short_year(value: Decimal, market_return: Decimal, gross_long: Decimal,
                    gross_short: Decimal, alpha: Decimal = D("0"),
                    borrow_cost: Decimal = D("0"), dividend_yield_short: Decimal = D("0"),
                    days_held_short: int = 365, loss_harvesting_mode: bool = False,
                    seed: int | None = None) -> LongShortYear:
    random.Random(seed)  # stable extension point for security-level simulation
    value = D(value)
    economic = value * (D(market_return) * (D(gross_long) - D(gross_short)) + D(alpha))
    borrow = value * D(gross_short) * D(borrow_cost)
    in_lieu = value * D(gross_short) * D(dividend_yield_short)
    net = economic - borrow - in_lieu
    if loss_harvesting_mode:
        realized = -abs(value * D("0.02"))
        v = TaxCharacterVector(st_capital_gain=realized * D("0.7"),
                               lt_capital_gain=realized * D("0.3"),
                               deferred=net - realized)
    else:
        v = TaxCharacterVector(st_capital_gain=net * D("0.65"),
                               lt_capital_gain=net * D("0.20"),
                               deferred=net * D("0.15"))
    return LongShortYear(value + net, net / value if value else D("0"), v,
                         borrow + in_lieu)


@dataclass
class UBTITax:
    taxable_ubti: Decimal
    tax: Decimal


def ubti_tax(ubti: Decimal, tables_year: int = 2026) -> UBTITax:
    taxable = max(D("0"), D(ubti) - D("1000"))
    # Compressed trust brackets, sufficient for plan projection and kept
    # separately from individual schedules.
    tax = (min(taxable, D("3300")) * D("0.10") +
           min(max(D("0"), taxable - D("3300")), D("8400")) * D("0.24") +
           min(max(D("0"), taxable - D("11700")), D("4300")) * D("0.35") +
           max(D("0"), taxable - D("16000")) * D("0.37"))
    return UBTITax(taxable, tax)
