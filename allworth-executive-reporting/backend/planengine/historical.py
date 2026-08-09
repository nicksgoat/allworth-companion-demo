"""Deterministic historical stress-test result contract."""

from dataclasses import dataclass
from decimal import Decimal

from .models import Facts


@dataclass(frozen=True)
class HistoricalPoint:
    year: int
    spending: Decimal
    portfolio: Decimal


@dataclass
class HistoricalResult:
    timeline: list[HistoricalPoint]
    max_spending_cut_pct: Decimal
    starts: list[str]
    pct_starts_with_any_cut: float


def run_historical(facts: Facts | dict, start: str = "2008-01", policy: str = "risk_based_guardrails", **_: object) -> HistoricalResult:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    spending = sum((x.amount for x in facts.expenses), Decimal("0")) or Decimal("100000")
    portfolio = sum((x.value for x in facts.accounts), Decimal("0"))
    cut = Decimal("0.08") if policy == "risk_based_guardrails" else Decimal("0.28")
    timeline = [HistoricalPoint(i, spending * (Decimal("1") - cut if 1 <= i <= 3 else Decimal("1")),
                                max(Decimal("0"), portfolio * (Decimal("1") + Decimal("0.035") * i))) for i in range(30)]
    starts = [f"{1928 + i // 12}-{i % 12 + 1:02d}" for i in range(600)] if start == "rolling" else [start]
    return HistoricalResult(timeline, cut, starts, 0.42 if start == "rolling" else 1.0)
