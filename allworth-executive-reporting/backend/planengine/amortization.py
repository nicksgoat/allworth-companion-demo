"""Liability amortization schedules aggregated to plan years."""

from dataclasses import dataclass
from decimal import Decimal, getcontext

getcontext().prec = 32
D = Decimal


@dataclass(frozen=True)
class AmortizationYear:
    year: int
    payment: Decimal
    interest: Decimal
    principal: Decimal
    ending_balance: Decimal


@dataclass(frozen=True)
class AmortizationSchedule:
    annual_payment: Decimal
    years: list[AmortizationYear]


def annual_amortization(principal: Decimal, rate: Decimal, term_years: int,
                        frequency: str = "monthly", repayment_type: str = "p_and_i",
                        balloon_period_years: int | None = None) -> AmortizationSchedule:
    principal, rate = D(principal), D(rate)
    periods_per_year = {"monthly": 12, "quarterly": 4, "semiannual": 2, "annual": 1}.get(frequency)
    if not periods_per_year or term_years <= 0 or principal < 0:
        raise ValueError("invalid amortization inputs")
    n = term_years * periods_per_year
    periodic_rate = rate / periods_per_year
    if repayment_type == "interest_only":
        payment = principal * periodic_rate
    elif periodic_rate == 0:
        payment = principal / n
    else:
        payment = principal * periodic_rate / (D("1") - (D("1") + periodic_rate) ** -n)
    balance = principal
    rows: list[AmortizationYear] = []
    balloon_at = balloon_period_years or term_years
    for year in range(1, min(term_years, balloon_at) + 1):
        interest_total = principal_total = payment_total = D("0")
        for _ in range(periods_per_year):
            interest = balance * periodic_rate
            if repayment_type == "interest_only":
                principal_paid = D("0")
            else:
                principal_paid = min(balance, payment - interest)
            paid = interest + principal_paid
            balance -= principal_paid
            interest_total += interest
            principal_total += principal_paid
            payment_total += paid
        if year == balloon_at and balance > 0:
            principal_total += balance
            payment_total += balance
            balance = D("0")
        if abs(balance) < D("0.000001"):
            balance = D("0")
        rows.append(AmortizationYear(year, payment_total, interest_total,
                                     principal_total, balance))
    return AmortizationSchedule(payment * periods_per_year, rows)
