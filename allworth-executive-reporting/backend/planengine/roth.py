"""Ledger-faithful multi-year Roth conversion analysis.

Every candidate strategy is evaluated by running the canonical projection
ledger with a ``Transfer(roth_conversion=True)`` — no side calculations that
could drift from engine tax math. Bracket-headroom candidates are discovered
by probing the ledger's own year-one tax function, so Social Security
phase-in, RMD interactions, and deduction effects are all captured.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .engine import run_projection
from .models import Facts, Timing, TimingKind, Transfer
from .rmd import rmd_start_age

D = Decimal
ZERO = D("0")

# Ordinary-rate targets a conversion ladder typically fills to.
DEFAULT_BRACKET_TARGETS = (D("0.12"), D("0.22"), D("0.24"))
_PROBE_STEP = D("1000")
_RATE_TOLERANCE = D("0.005")


class RothCandidate(BaseModel):
    label: str
    annual_conversion: Decimal
    window_years: int
    total_converted: Decimal
    lifetime_taxes: Decimal
    lifetime_tax_delta: Decimal
    ending_net_worth: Decimal
    ending_net_worth_delta: Decimal
    ending_after_tax_wealth: Decimal
    ending_after_tax_delta: Decimal
    breakeven_year: int | None = None
    first_shortfall_year: int | None = None


class RothConversionAnalysis(BaseModel):
    source_account_id: str | None = None
    source_account_name: str | None = None
    window_start_year: int
    window_years: int
    heir_tax_rate: Decimal
    baseline_lifetime_taxes: Decimal
    baseline_ending_net_worth: Decimal
    baseline_ending_after_tax_wealth: Decimal
    candidates: list[RothCandidate] = Field(default_factory=list)
    recommended: RothCandidate | None = None
    warnings: list[str] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)


def _source_account(facts: Facts):
    qualified = [a for a in facts.accounts
                 if a.kind in {"qualified", "ira"} and not a.exclude_from_planning]
    return max(qualified, key=lambda a: a.value, default=None)


def _ensure_destination(facts: Facts, source) -> str:
    for account in facts.accounts:
        if account.kind == "roth" and not account.exclude_from_planning:
            return str(account.id)
    roth = type(source).model_validate({
        "id": str(uuid4()), "kind": "roth", "name": "Roth IRA (conversion)",
        "value": 0, "growth_rate": str(source.growth_rate), "owner": source.owner,
        "apply_rmd": False, "liquidity": source.liquidity})
    facts.accounts.append(roth)
    return str(roth.id)


def _with_conversion(facts: Facts, amount: Decimal, window_years: int) -> tuple[Facts, str]:
    trial = facts.model_copy(deep=True)
    source = _source_account(trial)
    destination_id = _ensure_destination(trial, source)
    trial.transfers = [*trial.transfers, Transfer(
        name="Roth conversion ladder", annual_amount=amount,
        source_account=str(source.id), destination_account=destination_id,
        roth_conversion=True,
        starts=Timing(kind=TimingKind.IMMEDIATELY),
        ends=Timing(kind=TimingKind.DURATION_YEARS, value=window_years))]
    return trial, destination_id


def _qualified_ids(facts: Facts) -> set[str]:
    return {str(a.id) for a in facts.accounts
            if a.kind in {"qualified", "ira"} and not a.exclude_from_planning}


def _after_tax_series(projection, qualified_ids: set[str],
                      heir_tax_rate: Decimal) -> list[Decimal]:
    series = []
    for row in projection.rows:
        deferred = sum((balance for account_id, balance in row.account_balances.items()
                        if account_id in qualified_ids), ZERO)
        series.append(row.net_worth - deferred * heir_tax_rate)
    return series


def _bracket_headroom(facts: Facts, window_years: int, ceiling: Decimal,
                      target_rate: Decimal) -> Decimal:
    """Largest annual conversion whose ledger-measured incremental year-one tax
    rate stays at or below ``target_rate``. Bisection over the real engine."""
    tax_cache: dict[Decimal, Decimal] = {}

    def year_one_tax(amount: Decimal) -> Decimal:
        amount = max(ZERO, amount)
        if amount not in tax_cache:
            trial, _ = _with_conversion(facts, amount, window_years)
            tax_cache[amount] = run_projection(trial).rows[0].taxes
        return tax_cache[amount]

    def incremental_rate(amount: Decimal) -> Decimal:
        return (year_one_tax(amount) - year_one_tax(amount - _PROBE_STEP)) / _PROBE_STEP

    if ceiling < _PROBE_STEP or incremental_rate(_PROBE_STEP) > target_rate + _RATE_TOLERANCE:
        return ZERO
    low, high = _PROBE_STEP, ceiling
    if incremental_rate(high) <= target_rate + _RATE_TOLERANCE:
        return high
    while high - low > _PROBE_STEP:
        mid = ((low + high) / 2).quantize(_PROBE_STEP)
        if incremental_rate(mid) <= target_rate + _RATE_TOLERANCE:
            low = mid
        else:
            high = mid
    return low


def _default_window(facts: Facts) -> int:
    client = next((p for p in facts.people if p.role == "client"), facts.people[0])
    current_age = facts.assumptions.start_year - client.date_of_birth.year
    years_to_rmd = rmd_start_age(client.date_of_birth.year) - current_age
    return max(1, min(15, years_to_rmd if years_to_rmd > 0 else 5))


DEFAULT_HEIR_TAX_RATE = D("0.24")


def analyze_roth_conversions(facts: Facts | dict, *, window_years: int | None = None,
                             heir_tax_rate: Decimal = DEFAULT_HEIR_TAX_RATE,
                             bracket_targets: tuple[Decimal, ...] = DEFAULT_BRACKET_TARGETS,
                             ) -> RothConversionAnalysis:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    baseline = run_projection(facts)
    qualified_ids = _qualified_ids(facts)
    baseline_after_tax = _after_tax_series(baseline, qualified_ids, heir_tax_rate)
    source = _source_account(facts)
    window = int(window_years or _default_window(facts))
    analysis = RothConversionAnalysis(
        source_account_id=str(source.id) if source else None,
        source_account_name=source.name if source else None,
        window_start_year=facts.assumptions.start_year,
        window_years=window, heir_tax_rate=heir_tax_rate,
        baseline_lifetime_taxes=baseline.lifetime_taxes,
        baseline_ending_net_worth=baseline.ending_net_worth,
        baseline_ending_after_tax_wealth=baseline_after_tax[-1] if baseline_after_tax else ZERO,
        assumptions={"bracket_targets": [str(rate) for rate in bracket_targets],
                     "candidate_selection": "ledger-probed bracket headroom + balance fractions",
                     "after_tax_definition": "net worth minus heir_tax_rate on remaining tax-deferred balances"})
    if source is None or source.value <= 0:
        analysis.warnings.append("No tax-deferred account is available to convert")
        return analysis

    per_year_ceiling = D(source.value) / window
    amounts: dict[str, Decimal] = {}
    for rate in bracket_targets:
        headroom = _bracket_headroom(facts, window, per_year_ceiling, D(rate))
        if headroom > 0:
            amounts[f"Fill {D(rate) * 100:.0f}% bracket"] = headroom
    for fraction in (D("0.25"), D("0.50"), D("1.00")):
        amounts[f"Convert {fraction * 100:.0f}% over {window}y"] = (
            per_year_ceiling * fraction).quantize(_PROBE_STEP)
    seen: set[Decimal] = set()
    for label, amount in sorted(amounts.items(), key=lambda item: item[1]):
        if amount <= 0 or amount in seen:
            continue
        seen.add(amount)
        trial, _ = _with_conversion(facts, amount, window)
        projection = run_projection(trial)
        after_tax = _after_tax_series(projection, _qualified_ids(trial), heir_tax_rate)
        breakeven = next((row.year for row, candidate_value, base_value
                          in zip(projection.rows, after_tax, baseline_after_tax)
                          if candidate_value >= base_value), None)
        analysis.candidates.append(RothCandidate(
            label=label, annual_conversion=amount, window_years=window,
            total_converted=min(amount * window, D(source.value)),
            lifetime_taxes=projection.lifetime_taxes,
            lifetime_tax_delta=projection.lifetime_taxes - baseline.lifetime_taxes,
            ending_net_worth=projection.ending_net_worth,
            ending_net_worth_delta=projection.ending_net_worth - baseline.ending_net_worth,
            ending_after_tax_wealth=after_tax[-1] if after_tax else ZERO,
            ending_after_tax_delta=(after_tax[-1] - baseline_after_tax[-1])
            if after_tax and baseline_after_tax else ZERO,
            breakeven_year=breakeven,
            first_shortfall_year=projection.first_shortfall_year))
    def acceptable_liquidity(candidate: RothCandidate) -> bool:
        if candidate.first_shortfall_year is None:
            return True
        return (baseline.first_shortfall_year is not None and
                candidate.first_shortfall_year >= baseline.first_shortfall_year)

    improving = [c for c in analysis.candidates
                 if c.ending_after_tax_delta > 0 and acceptable_liquidity(c)]
    if improving:
        analysis.recommended = max(improving, key=lambda c: (c.ending_after_tax_delta,
                                                             -c.lifetime_tax_delta))
    else:
        analysis.warnings.append(
            "No conversion ladder improves after-tax wealth under current assumptions")
    return analysis
