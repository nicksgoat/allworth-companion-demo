"""Risk-based retirement paycheck and guardrail calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .models import Facts

D = Decimal


def _horizon(facts: Facts, year: int) -> int:
    latest = max((p.date_of_birth.year + p.assumed_age_of_death for p in facts.people), default=year + 30)
    return max(1, latest - year + 1)


def spending_capacity(facts: Facts | dict, year: int, portfolio_value: Decimal | None = None,
                      percentile: int = 20, seed: int = 42, **_: object) -> Decimal:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    pv = D(portfolio_value if portfolio_value is not None else sum((a.value for a in facts.accounts), D("0")))
    years = _horizon(facts, year)
    # Conservative real return scales smoothly with risk percentile. This is
    # the closed-form starting point used by the MC-backed bisection service.
    real_rate = max(D("0.005"), D("0.025") + (D(percentile) - D("20")) / D("4000"))
    annuity = pv * real_rate / (D("1") - (D("1") + real_rate) ** -years)
    guaranteed = sum((flow.amount for flow in facts.income if flow.kind in {"social_security", "pension", "annuity"}), D("0"))
    return max(D("0"), annuity + guaranteed)


@dataclass(frozen=True)
class GuardrailEvaluation:
    status: str
    recommended_monthly: Decimal


@dataclass
class GuardrailPlan:
    as_of: int
    spending_target_monthly: Decimal
    floor_monthly: Decimal
    lower_guardrail_value: Decimal
    cut_to: Decimal
    upper_guardrail_value: Decimal
    raise_to: Decimal
    capacity_curve: list[tuple[Decimal, Decimal]]
    min_change_pct: Decimal

    def capacity_at(self, portfolio_value: Decimal) -> Decimal:
        pv = D(portfolio_value); points = sorted(self.capacity_curve)
        if pv <= points[0][0]: return points[0][1]
        if pv >= points[-1][0]: return points[-1][1]
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            if x1 <= pv <= x2:
                return y1 + (y2 - y1) * (pv - x1) / (x2 - x1)
        return points[-1][1]

    def evaluate(self, portfolio_value: Decimal, current_spending: Decimal) -> GuardrailEvaluation:
        pv, current = D(portfolio_value), D(current_spending)
        recommended = self.cut_to if pv < self.lower_guardrail_value else self.raise_to if pv > self.upper_guardrail_value else self.spending_target_monthly
        change = abs(recommended - current) / current if current else D("1")
        if change < self.min_change_pct: return GuardrailEvaluation("on_track", current)
        status = "cut_recommended" if recommended < current else "raise_available" if recommended > current else "on_track"
        return GuardrailEvaluation(status, recommended)


def build_guardrails(facts: Facts | dict, year: int, target_pct: int = 20, seed: int = 42,
                     min_change_pct: Decimal = D("0.05"), **_: object) -> GuardrailPlan:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    pv = sum((a.value for a in facts.accounts), D("0")) or D("1000000")
    grid_values = [pv * (D("0.4") + D(i) * D("0.1")) for i in range(13)]
    curve = [(x, spending_capacity(facts, year, x, target_pct, seed)) for x in grid_values]
    target = spending_capacity(facts, year, pv, target_pct, seed) / 12
    required = sum((x.amount for x in facts.expenses if x.required), D("0")) / 12
    return GuardrailPlan(year, target, min(required, target * D("0.8")), pv * D("0.75"),
                         target * D("0.9"), pv * D("1.35"), target * D("1.1"), curve,
                         D(min_change_pct))
