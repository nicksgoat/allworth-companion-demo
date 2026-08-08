"""Reproducible bisection solve-fors for planning levers."""

from dataclasses import dataclass
from decimal import Decimal

from .engine import run_projection
from .models import Facts

D = Decimal


@dataclass(frozen=True)
class SolveResult:
    lever: str
    value: Decimal
    target: Decimal
    iterations: int
    achieved: bool


def solve_monthly_savings(facts: Facts | dict, target_ending_value: Decimal,
                          lower: Decimal = D("0"), upper: Decimal = D("50000"),
                          tolerance: Decimal = D("1")) -> SolveResult:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    target = D(target_ending_value)
    iterations = 0
    while upper - lower > tolerance and iterations < 60:
        iterations += 1; mid = (lower + upper) / 2
        trial = facts.model_copy(deep=True)
        if not trial.income:
            from .models import Flow, Indexing
            trial.income.append(Flow(name="Solve-for savings", amount=mid * 12,
                                     taxable=False, indexing=Indexing(mode="none")))
        else:
            trial.income[0].amount += mid * 12
        if run_projection(trial).ending_net_worth >= target: upper = mid
        else: lower = mid
    return SolveResult("monthly_savings", upper, target, iterations,
                       run_projection(trial).ending_net_worth >= target)
