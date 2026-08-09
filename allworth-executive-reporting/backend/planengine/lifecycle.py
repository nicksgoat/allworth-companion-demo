"""Deterministic lifecycle advice model.

This module ports the Idzorek-Kaplan workbook at the architecture level first:
mortality, human capital, liabilities, bequest, consumption, and glide path are
separate deterministic calculations that can be validated against workbook
golden files as the VBA parity work continues.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from math import exp
from typing import Literal

from pydantic import BaseModel, Field

from .models import Facts


class InvestorParams(BaseModel):
    age: int = Field(ge=18, le=100)
    sex: Literal["M", "F"] = "M"
    longevity_adjustment: float = 0
    max_year_of_life: int = Field(default=100, ge=70, le=120)
    impatience_for_consumption: float = Field(default=0.015, ge=-0.05, le=0.2)
    pref_for_smooth_consumption: float = Field(default=0.5, ge=0.05, le=5)
    risk_tolerance: float = Field(default=0.55, ge=0, le=1)
    nondiscretionary_consumption: float = Field(default=0, ge=0)
    financial_wealth_dom_stocks: float = Field(default=0, ge=0)
    financial_wealth_global_stocks: float = Field(default=0, ge=0)
    financial_wealth_bonds: float = Field(default=0, ge=0)
    financial_wealth_cash: float = Field(default=0, ge=0)
    retirement_age: int = Field(default=65, ge=45, le=85)
    current_income: float = Field(default=0, ge=0)
    dc_contribution: float = Field(default=0, ge=0, le=1)
    dc_match_pct: float = Field(default=0, ge=0, le=1)
    annuitize_fraction: float = Field(default=0, ge=0, le=1)
    bequest_flexibility: float = Field(default=0.5, ge=0.01, le=5)
    bequest_strength: float = Field(default=0.2, ge=0, le=5)
    bequest_type: Literal["optimal", "fixed"] = "optimal"
    bequest_fixed_amount: float = Field(default=0, ge=0)
    education_level: Literal["no_hs", "hs", "college", "postgrad"] = "college"
    human_capital_equity_exposure: float = Field(default=0.25, ge=0, le=1)
    human_capital_global_exposure: float = Field(default=0.25, ge=0, le=1)
    liability_equity_exposure: float = Field(default=0.15, ge=0, le=1)
    liability_global_exposure: float = Field(default=0.15, ge=0, le=1)
    certainty_equiv_return: float = Field(default=0.025, ge=-0.05, le=0.2)
    current_year: int = Field(default_factory=lambda: date.today().year)


class SensitivityRequest(BaseModel):
    base: InvestorParams | None = None
    param: str
    values: list[float | int | str] = Field(min_length=1, max_length=8)


def _money(value: Decimal | int | float) -> float:
    return round(float(value), 2)


def _age(person, today: date) -> int:
    born = person.date_of_birth
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def _flow_amount(flows) -> Decimal:
    return sum((Decimal(str(flow.amount or 0)) for flow in flows), Decimal("0"))


def _classify_account(account) -> str:
    text = " ".join(
        str(value or "")
        for value in (account.kind, account.name, getattr(account, "asset_class", ""))
    ).lower()
    if "cash" in text or "money market" in text:
        return "cash"
    if "bond" in text or "fixed income" in text:
        return "bonds"
    if "international" in text or "global" in text or "foreign" in text or "emerging" in text:
        return "global_stocks"
    if "stock" in text or "equity" in text or account.kind in {"taxable", "roth", "qualified"}:
        return "dom_stocks"
    return "bonds"


def _asset_mix_from_facts(facts: Facts) -> dict[str, Decimal]:
    buckets = {
        "dom_stocks": Decimal("0"),
        "global_stocks": Decimal("0"),
        "bonds": Decimal("0"),
        "cash": Decimal("0"),
    }
    for account in facts.accounts:
        if account.exclude_from_planning:
            continue
        if account.holdings:
            for holding in account.holdings:
                value = Decimal(str(holding.market_value or 0))
                asset_class = str(holding.asset_class or "").lower()
                if "cash" in asset_class or "money market" in asset_class:
                    buckets["cash"] += value
                elif "bond" in asset_class or "fixed" in asset_class:
                    buckets["bonds"] += value
                elif "international" in asset_class or "global" in asset_class or "foreign" in asset_class:
                    buckets["global_stocks"] += value
                elif "stock" in asset_class or "equity" in asset_class:
                    buckets["dom_stocks"] += value
                else:
                    buckets[_classify_account(account)] += value
        else:
            buckets[_classify_account(account)] += Decimal(str(account.value or 0))
    return buckets


def investor_params_from_facts(facts: Facts) -> InvestorParams:
    today = date.today()
    client = next((person for person in facts.people if person.role == "client"), None)
    if client is None and facts.people:
        client = facts.people[0]
    buckets = _asset_mix_from_facts(facts)
    income = _flow_amount(facts.income)
    expenses = _flow_amount([flow for flow in facts.expenses if flow.required])
    total_assets = sum(buckets.values(), Decimal("0"))
    equity_assets = buckets["dom_stocks"] + buckets["global_stocks"]
    risk_tolerance = float(equity_assets / total_assets) if total_assets else 0.55
    metadata = facts.metadata or {}
    sex = str(metadata.get("client_sex") or metadata.get("sex") or "M").upper()[:1]
    if sex not in {"M", "F"}:
        sex = "M"
    return InvestorParams(
        age=_age(client, today) if client else 50,
        sex=sex,  # type: ignore[arg-type]
        max_year_of_life=max(
            int(facts.assumptions.plan_end_age or 100),
            int((client.assumed_age_of_death if client else 95) or 95),
        ),
        risk_tolerance=max(0.05, min(0.95, risk_tolerance)),
        nondiscretionary_consumption=_money(expenses),
        financial_wealth_dom_stocks=_money(buckets["dom_stocks"]),
        financial_wealth_global_stocks=_money(buckets["global_stocks"]),
        financial_wealth_bonds=_money(buckets["bonds"]),
        financial_wealth_cash=_money(buckets["cash"]),
        retirement_age=int((client.retirement_age if client else 65) or 65),
        current_income=_money(income),
        current_year=int(facts.assumptions.start_year or today.year),
    )


def _survival_probability(age: int, future_year: int, sex: str, longevity_adjustment: float) -> float:
    mode = (89 if sex == "M" else 92) + longevity_adjustment
    dispersion = 10.5 if sex == "M" else 9.5
    current = exp((age - mode) / dispersion)
    future = exp((age + future_year - mode) / dispersion)
    return max(0.0, min(1.0, exp(-(future - current))))


def run_lifecycle_plan(params: InvestorParams) -> dict:
    horizon = max(0, params.max_year_of_life - params.age)
    financial_wealth = (
        params.financial_wealth_dom_stocks
        + params.financial_wealth_global_stocks
        + params.financial_wealth_bonds
        + params.financial_wealth_cash
    )
    discount = 1 + params.certainty_equiv_return
    income_path = []
    human_capital = 0.0
    liabilities = 0.0
    survival_curve = []
    for t in range(horizon + 1):
        age = params.age + t
        year = params.current_year + t
        survival = _survival_probability(params.age, t, params.sex, params.longevity_adjustment)
        survival_curve.append({"year": year, "age": age, "survival_probability": round(survival, 6)})
        if age < params.retirement_age:
            education_growth = {
                "no_hs": 0.005,
                "hs": 0.008,
                "college": 0.012,
                "postgrad": 0.015,
            }[params.education_level]
            gross_income = params.current_income * ((1 + education_growth) ** t)
            dc_savings = gross_income * min(1, params.dc_contribution + params.dc_match_pct)
            spendable_income = max(0.0, gross_income - dc_savings)
        else:
            gross_income = params.current_income * 0.35 if params.current_income else 0
            dc_savings = 0.0
            spendable_income = gross_income
        pv_income = spendable_income * survival / (discount ** t)
        pv_liability = params.nondiscretionary_consumption * survival / (discount ** t)
        human_capital += pv_income
        liabilities += pv_liability
        income_path.append(
            {
                "year": year,
                "age": age,
                "gross_income": round(gross_income, 2),
                "dc_savings": round(dc_savings, 2),
                "present_value_income": round(pv_income, 2),
            }
        )
    economic_net_worth = financial_wealth + human_capital - liabilities
    if params.bequest_type == "fixed":
        bequest = min(params.bequest_fixed_amount, max(0.0, economic_net_worth))
    else:
        tradeoff = params.bequest_strength / (params.bequest_strength + params.bequest_flexibility + 1)
        bequest = max(0.0, economic_net_worth) * min(0.75, tradeoff)
    spendable_wealth = max(0.0, economic_net_worth - bequest)
    annuity_weight = sum(
        _survival_probability(params.age, t, params.sex, params.longevity_adjustment)
        / ((1 + params.impatience_for_consumption + params.certainty_equiv_return) ** t)
        for t in range(horizon + 1)
    )
    base_consumption = spendable_wealth / annuity_weight if annuity_weight else 0.0
    annuity_floor = financial_wealth * params.annuitize_fraction * 0.045
    consumption_path = []
    glide_path = []
    human_capital_remaining = human_capital
    liability_remaining = liabilities
    for index, row in enumerate(income_path):
        age = row["age"]
        survival = survival_curve[index]["survival_probability"]
        discretionary = base_consumption * (survival ** (1 / max(params.pref_for_smooth_consumption, 0.05)))
        total_consumption = params.nondiscretionary_consumption + discretionary + annuity_floor
        hc_ratio = human_capital_remaining / max(financial_wealth + human_capital_remaining, 1)
        unconstrained_equity = params.risk_tolerance + (hc_ratio * (params.risk_tolerance - params.human_capital_equity_exposure))
        liability_hedge = (liability_remaining / max(financial_wealth + liability_remaining, 1)) * params.liability_equity_exposure
        constrained_equity = max(0.0, min(1.0, unconstrained_equity - liability_hedge))
        global_equity = constrained_equity * max(params.human_capital_global_exposure, params.liability_global_exposure, 0.25)
        consumption_path.append(
            {
                "year": row["year"],
                "age": age,
                "nondiscretionary": round(params.nondiscretionary_consumption, 2),
                "discretionary": round(discretionary, 2),
                "annuity_floor": round(annuity_floor, 2),
                "total_consumption": round(total_consumption, 2),
            }
        )
        glide_path.append(
            {
                "year": row["year"],
                "age": age,
                "unconstrained_equity": round(unconstrained_equity, 4),
                "constrained_equity": round(constrained_equity, 4),
                "domestic_stock": round(max(0.0, constrained_equity - global_equity), 4),
                "global_stock": round(global_equity, 4),
                "bonds_cash": round(max(0.0, 1 - constrained_equity), 4),
            }
        )
        human_capital_remaining = max(0.0, human_capital_remaining - row["present_value_income"])
        liability_remaining = max(0.0, liability_remaining - (
            params.nondiscretionary_consumption * survival / (discount ** index)
        ))
    return {
        "inputs": params.model_dump(mode="json"),
        "economic_balance_sheet": {
            "financial_wealth": round(financial_wealth, 2),
            "human_capital": round(human_capital, 2),
            "liabilities": round(liabilities, 2),
            "economic_net_worth": round(economic_net_worth, 2),
        },
        "bequest": {
            "amount": round(bequest, 2),
            "type": params.bequest_type,
            "is_optimal": params.bequest_type == "optimal",
        },
        "human_capital_path": income_path,
        "consumption_path": consumption_path,
        "glide_path": glide_path,
        "survival_curve": survival_curve,
        "warnings": [
            "Lifecycle model is a deterministic Python port scaffold. Workbook golden-file parity remains a validation gate before client-facing advice.",
        ],
    }
