"""Planning tools — retirement projection, Roth conversion, portfolio drift.

Inspired by the analytics plugin's planning/ and portfolio/ engines, but
operating purely on local seed data (no Synapse, no numpy). Deterministic
Monte Carlo uses a fixed sequence so demo results are reproducible.
"""

from __future__ import annotations

import math
import random
from typing import Any

from allworth_api.core.formatting import fmt_usd, js_round
from allworth_api.data.seed import current_seed

# ── Retirement Projection (simplified Monte Carlo) ───────────────────────

# Fixed random seed for reproducible demo runs
_RNG = random.Random(42)

# Market assumptions (real returns, annual)
_EQUITY_MEAN = 0.07
_EQUITY_STD = 0.16
_BOND_MEAN = 0.03
_BOND_STD = 0.05
_CORRELATION = 0.2


def _generate_returns(equity_pct: float, n_years: int, n_sims: int) -> list[list[float]]:
    """Generate correlated annual portfolio returns for n_sims paths."""
    bond_pct = 1.0 - equity_pct
    paths = []
    for _ in range(n_sims):
        yearly = []
        for _ in range(n_years):
            z1 = _RNG.gauss(0, 1)
            z2 = _RNG.gauss(0, 1)
            z_corr = _CORRELATION * z1 + math.sqrt(1 - _CORRELATION**2) * z2
            eq_ret = _EQUITY_MEAN + _EQUITY_STD * z1
            bond_ret = _BOND_MEAN + _BOND_STD * z_corr
            port_ret = equity_pct * eq_ret + bond_pct * bond_ret
            yearly.append(port_ret)
        paths.append(yearly)
    return paths


def run_retirement_projection(
    *,
    current_age: int | None = None,
    retirement_age: int | None = None,
    end_age: int = 95,
    n_simulations: int = 500,
) -> dict[str, Any]:
    """Monte Carlo retirement projection using the client's plan data.

    Returns success rate, percentile paths (p5, p25, p50, p75, p95),
    and a year-by-year projection table.
    """
    seed = current_seed()
    plan = seed["plan"]
    accounts = seed["accounts"]

    client = seed["personas"]["clients"][0]
    age = current_age or client["age"]
    retire_age = retirement_age or age  # Maya is already semi-retired

    # Current portfolio value (exclude liabilities and cash for projection)
    invested = sum(a["balance"] for a in accounts if a["type"] not in ("cash", "liability"))

    # Parse equity allocation from risk target
    equity_pct = 0.60  # "60/40 growth & income"

    monthly_spend = plan["spendingAssumptionMonthly"]
    annual_spend = monthly_spend * 12
    other_income = plan["otherIncomeMonthly"] * 12
    # Net annual draw from portfolio
    annual_draw = max(0, annual_spend - other_income)

    n_years = end_age - age
    if n_years <= 0:
        return {"error": "end_age must be greater than current age"}

    # Reset RNG for reproducibility
    _RNG.seed(42)
    paths = _generate_returns(equity_pct, n_years, n_simulations)

    # Simulate each path
    final_balances: list[float] = []
    all_paths: list[list[float]] = []

    for sim_returns in paths:
        balance = float(invested)
        yearly_balances = [balance]
        for year_idx, ret in enumerate(sim_returns):
            current_year_age = age + year_idx + 1
            # Apply draw (inflation-adjusted at 3% annually)
            inflation_factor = 1.03 ** (year_idx + 1)
            draw = annual_draw * inflation_factor if current_year_age >= retire_age else 0
            balance = balance * (1 + ret) - draw
            balance = max(0, balance)
            yearly_balances.append(balance)
        all_paths.append(yearly_balances)
        final_balances.append(balance)

    # Success = didn't run out of money
    successes = sum(1 for b in final_balances if b > 0)
    success_rate = successes / n_simulations

    # Percentile paths
    def percentile_path(pct: float) -> list[float]:
        result = []
        for year_idx in range(n_years + 1):
            values = sorted(p[year_idx] for p in all_paths)
            idx = int(pct / 100 * (len(values) - 1))
            result.append(js_round(values[idx]))
        return result

    p5 = percentile_path(5)
    p25 = percentile_path(25)
    p50 = percentile_path(50)
    p75 = percentile_path(75)
    p95 = percentile_path(95)

    # Build year-by-year snapshot (every 5 years for readability)
    snapshots = []
    for i in range(0, n_years + 1, 5):
        snapshots.append({
            "age": age + i,
            "year": 2026 + i,
            "p5": p5[i],
            "p25": p25[i],
            "median": p50[i],
            "p75": p75[i],
            "p95": p95[i],
        })
    # Always include final year
    if (n_years) % 5 != 0:
        snapshots.append({
            "age": end_age,
            "year": 2026 + n_years,
            "p5": p5[-1],
            "p25": p25[-1],
            "median": p50[-1],
            "p75": p75[-1],
            "p95": p95[-1],
        })

    return {
        "successRate": js_round(success_rate * 100),
        "simulations": n_simulations,
        "assumptions": {
            "currentAge": age,
            "endAge": end_age,
            "equityAllocation": equity_pct,
            "annualSpending": annual_spend,
            "otherIncome": other_income,
            "annualDraw": annual_draw,
            "inflationRate": 0.03,
            "startingPortfolio": invested,
        },
        "interpretation": _interpret_success(success_rate),
        "pathSnapshots": snapshots,
    }


def _interpret_success(rate: float) -> str:
    if rate >= 0.90:
        return (
            f"Success rate of {rate*100:.0f}% is generally sufficient. "
            "Sequence-of-returns risk remains; consider a 1-2 year cash buffer."
        )
    if rate >= 0.70:
        return (
            f"Success rate of {rate*100:.0f}% is conditionally sufficient. "
            "Test spending flexibility or a delayed full-retirement date."
        )
    return (
        f"Success rate of {rate*100:.0f}% suggests a gap. "
        "Identify the highest-impact lever: reduce spending, extend income, or de-risk."
    )


# ── Portfolio Drift Analysis ─────────────────────────────────────────────

# Target allocation from plan's risk target "60/40 growth & income"
_TARGET_ALLOCATION = {
    "us_equity": 0.40,
    "intl_equity": 0.20,
    "muni_bond": 0.15,
    "corp_bond": 0.10,
    "intl_bond": 0.05,
    "cash": 0.05,
    "alternatives": 0.05,
}

_ASSET_CLASS_LABELS = {
    "us_equity": "US Equity",
    "intl_equity": "International Equity",
    "muni_bond": "Municipal Bonds",
    "corp_bond": "Corporate Bonds",
    "intl_bond": "International Bonds",
    "cash": "Cash & Equivalents",
    "alternatives": "Alternatives",
}

# Drift thresholds
_DRIFT_WARNING = 0.03   # 3% = yellow
_DRIFT_CRITICAL = 0.05  # 5% = red


def analyze_portfolio_drift(*, account_id: str | None = None) -> dict[str, Any]:
    """Compare current portfolio allocation to the 60/40 target.

    Returns per-asset-class drift, overall drift score, and rebalance actions.
    """
    seed = current_seed()
    positions = seed["positions"]
    if account_id:
        positions = [p for p in positions if p["accountId"] == account_id]

    if not positions:
        return {"error": "No positions found for the given filter."}

    total_value = sum(p["value"] for p in positions)
    if total_value == 0:
        return {"error": "Portfolio value is zero."}

    # Current allocation by asset class
    current: dict[str, float] = {}
    for p in positions:
        ac = p.get("assetClass", "other")
        current[ac] = current.get(ac, 0) + p["value"]

    # Normalize to percentages
    current_pct = {k: v / total_value for k, v in current.items()}

    # Compute drift per asset class
    drift_details = []
    total_abs_drift = 0.0
    for ac, target_pct in _TARGET_ALLOCATION.items():
        actual = current_pct.get(ac, 0.0)
        drift = actual - target_pct
        abs_drift = abs(drift)
        total_abs_drift += abs_drift

        status = "ok"
        if abs_drift >= _DRIFT_CRITICAL:
            status = "critical"
        elif abs_drift >= _DRIFT_WARNING:
            status = "warning"

        drift_details.append({
            "assetClass": ac,
            "label": _ASSET_CLASS_LABELS.get(ac, ac),
            "targetPct": js_round(target_pct * 100),
            "actualPct": js_round(actual * 100),
            "driftPct": js_round(drift * 100),
            "driftDollars": js_round(drift * total_value),
            "status": status,
        })

    # Overall drift score (half the sum of absolute drifts — a standard measure)
    drift_score = total_abs_drift / 2

    # Flag any unrecognized asset classes
    for ac, val in current_pct.items():
        if ac not in _TARGET_ALLOCATION and val > 0.001:
            drift_details.append({
                "assetClass": ac,
                "label": _ASSET_CLASS_LABELS.get(ac, ac.replace("_", " ").title()),
                "targetPct": 0,
                "actualPct": js_round(val * 100),
                "driftPct": js_round(val * 100),
                "driftDollars": js_round(val * total_value),
                "status": "unallocated",
            })

    # Generate rebalance suggestions
    rebalance_actions = []
    for d in drift_details:
        if d["status"] in ("critical", "warning"):
            if d["driftPct"] > 0:
                rebalance_actions.append(
                    f"Trim {d['label']} by ~{fmt_usd(abs(d['driftDollars']))}"
                )
            else:
                rebalance_actions.append(
                    f"Add ~{fmt_usd(abs(d['driftDollars']))} to {d['label']}"
                )

    return {
        "totalPortfolioValue": total_value,
        "driftScore": js_round(drift_score * 100),
        "needsRebalance": drift_score >= _DRIFT_WARNING,
        "allocation": drift_details,
        "suggestedActions": rebalance_actions,
        "riskTarget": seed["plan"]["riskTarget"],
    }


# ── Roth Conversion Analysis ────────────────────────────────────────────

_FEDERAL_BRACKETS_2026 = [
    (11925, 0.10),
    (48475, 0.12),
    (103350, 0.22),
    (197300, 0.24),
    (250525, 0.32),
    (626350, 0.35),
    (float("inf"), 0.37),
]


def run_roth_conversion_analysis(
    *,
    conversion_amount: float | None = None,
    current_income: float | None = None,
) -> dict[str, Any]:
    """Estimate the tax impact of converting IRA → Roth in the current year.

    Uses the client's tax profile from the plan. Shows marginal bracket impact,
    estimated tax cost, and break-even horizon.
    """
    seed = current_seed()
    plan = seed["plan"]
    accounts = seed["accounts"]

    ira_balance = next(
        (a["balance"] for a in accounts if a["type"] == "ira"), 0
    )
    if ira_balance == 0:
        return {"error": "No IRA balance found for conversion."}

    amount = conversion_amount or min(50000, ira_balance)
    amount = min(amount, ira_balance)

    # Current taxable income estimate
    income = current_income or (plan["portfolioIncomeMonthly"] + plan["otherIncomeMonthly"]) * 12

    # Calculate tax on income vs income + conversion
    tax_before = _calc_federal_tax(income)
    tax_after = _calc_federal_tax(income + amount)
    conversion_tax = tax_after - tax_before
    effective_rate = conversion_tax / amount if amount > 0 else 0

    # Marginal bracket analysis
    bracket_before = _marginal_bracket(income)
    bracket_after = _marginal_bracket(income + amount)

    # NIIT check (applies over $200K single / $250K married)
    niit_threshold = 200000 if plan["filingStatus"] == "single" else 250000
    niit_applies = (income + amount) > niit_threshold
    niit_cost = amount * 0.038 if niit_applies and plan.get("niitApplies") else 0

    total_tax = conversion_tax + niit_cost

    # Break-even: years until tax-free Roth growth exceeds upfront tax cost
    # Assumes 6% annual growth
    growth_rate = 0.06
    break_even_years = None
    if total_tax > 0 and amount > 0:
        # Tax-free growth advantage = amount * ((1+r)^n - 1) * future_tax_rate - total_tax = 0
        future_tax_rate = bracket_after  # conservative: same bracket
        for n in range(1, 40):
            roth_advantage = amount * ((1 + growth_rate) ** n - 1) * future_tax_rate
            if roth_advantage >= total_tax:
                break_even_years = n
                break

    return {
        "conversionAmount": amount,
        "iraBalanceBefore": ira_balance,
        "iraBalanceAfter": ira_balance - amount,
        "taxAnalysis": {
            "estimatedTax": js_round(total_tax),
            "federalTax": js_round(conversion_tax),
            "niitSurcharge": js_round(niit_cost),
            "effectiveRate": js_round(effective_rate * 100),
            "marginalBracketBefore": f"{bracket_before*100:.0f}%",
            "marginalBracketAfter": f"{bracket_after*100:.0f}%",
            "bracketJump": bracket_after > bracket_before,
        },
        "breakEvenYears": break_even_years,
        "interpretation": _interpret_roth(effective_rate, bracket_before, bracket_after, break_even_years),
        "currentIncome": income,
        "filingStatus": plan["filingStatus"],
    }


def _calc_federal_tax(taxable_income: float) -> float:
    """Calculate federal income tax using 2026 brackets."""
    tax = 0.0
    prev_ceiling = 0.0
    for ceiling, rate in _FEDERAL_BRACKETS_2026:
        bracket_income = min(taxable_income, ceiling) - prev_ceiling
        if bracket_income <= 0:
            break
        tax += bracket_income * rate
        prev_ceiling = ceiling
    return tax


def _marginal_bracket(income: float) -> float:
    for ceiling, rate in _FEDERAL_BRACKETS_2026:
        if income <= ceiling:
            return rate
    return 0.37


def _interpret_roth(
    eff_rate: float,
    bracket_before: float,
    bracket_after: float,
    break_even: int | None,
) -> str:
    parts = []
    if bracket_after > bracket_before:
        parts.append(
            f"Conversion pushes into the {bracket_after*100:.0f}% bracket "
            f"(from {bracket_before*100:.0f}%). Consider a smaller amount to stay within bracket."
        )
    else:
        parts.append(
            f"Conversion stays within the {bracket_after*100:.0f}% bracket — tax-efficient."
        )

    if break_even:
        parts.append(f"Break-even in ~{break_even} years of tax-free growth.")
    else:
        parts.append("Break-even analysis unavailable (conversion may not be advantageous).")

    if eff_rate < 0.20:
        parts.append("Effective rate below 20% — generally favorable for Roth conversion.")
    elif eff_rate < 0.30:
        parts.append("Effective rate 20-30% — conditionally favorable depending on time horizon.")
    else:
        parts.append("Effective rate above 30% — consider deferring or splitting across years.")

    return " ".join(parts)


# ── Goal Funding Analysis ────────────────────────────────────────────────


def analyze_goal_funding(*, growth_rate: float = 0.06) -> dict[str, Any]:
    """Assess funding status of each goal in the client's plan.

    For goals with a target and horizon, projects whether current funding
    plus expected growth will reach the target on time, and calculates
    the monthly contribution needed to close any gap.
    """
    from allworth_api.core.client_store import load_goal_plans

    seed = current_seed()
    plan = seed["plan"]
    goals = plan.get("goals", [])
    accounts = seed["accounts"]
    total_invested = sum(a["balance"] for a in accounts if a["type"] not in ("cash", "liability"))
    # Client-saved "live goal" funding plans (GoalsSheet / chat widget dials).
    saved_plans = load_goal_plans(plan.get("clientId", seed.get("clientId", "")))

    results = []
    for goal in goals:
        target = goal.get("target")
        if target is None:
            # Income goal — handled differently
            results.append({
                "id": goal["id"],
                "label": goal["label"],
                "type": "income",
                "detail": goal.get("detail", ""),
                "status": "on_track" if plan["portfolioIncomeMonthly"] >= 9000 else "at_risk",
            })
            continue

        funded_pct = goal.get("funded", 0)
        current_value = target * funded_pct
        horizon = goal.get("horizonYears", 1)

        # Project current funded amount forward
        projected = current_value * (1 + growth_rate) ** horizon
        gap = max(0, target - projected)
        on_track = projected >= target

        # Monthly contribution needed to close gap (future value of annuity)
        monthly_needed = 0.0
        if gap > 0 and horizon > 0:
            r_monthly = growth_rate / 12
            n_months = horizon * 12
            if r_monthly > 0:
                monthly_needed = gap * r_monthly / ((1 + r_monthly) ** n_months - 1)
            else:
                monthly_needed = gap / n_months

        entry = {
            "id": goal["id"],
            "label": goal["label"],
            "type": "lump_sum",
            "target": target,
            "currentFunded": js_round(current_value),
            "fundedPct": js_round(funded_pct * 100),
            "projectedAtHorizon": js_round(projected),
            "gap": js_round(gap),
            "horizonYears": horizon,
            "onTrack": on_track,
            "monthlyContributionToClose": js_round(monthly_needed),
            "status": "on_track" if on_track else "needs_attention",
        }

        # Merge the client's committed funding plan, if they saved one: project
        # again with their monthly contribution over their chosen timeline so
        # chat answers and the advisor brief reflect the live goal.
        committed = saved_plans.get(goal["id"])
        if committed:
            c_monthly = float(committed.get("monthly", 0) or 0)
            c_years = int(committed.get("years", horizon) or horizon)
            r_monthly = growth_rate / 12
            n_months = max(1, c_years * 12)
            fv_contrib = (
                c_monthly * (((1 + r_monthly) ** n_months - 1) / r_monthly)
                if r_monthly > 0
                else c_monthly * n_months
            )
            projected_with = current_value * (1 + growth_rate) ** c_years + fv_contrib
            entry.update({
                "committedMonthly": c_monthly,
                "committedYears": c_years,
                "projectedWithPlan": js_round(projected_with),
                "onTrackWithPlan": projected_with >= target,
                "status": "on_track" if projected_with >= target else "needs_attention",
            })

        results.append(entry)

    on_track_count = sum(1 for r in results if r["status"] == "on_track")
    return {
        "goals": results,
        "summary": f"{on_track_count}/{len(results)} goals on track",
        "totalInvestedAssets": total_invested,
        "assumedGrowthRate": growth_rate,
    }


# ── Income Sustainability Analysis ──────────────────────────────────────


def analyze_income_sustainability(*, inflation_rate: float = 0.03) -> dict[str, Any]:
    """Evaluate whether current income sources sustain planned spending.

    Projects income vs. spending over 5/10/20 year horizons with inflation,
    identifies the gap and which year spending overtakes income.
    """
    seed = current_seed()
    plan = seed["plan"]
    accounts = seed["accounts"]

    monthly_spend = plan["spendingAssumptionMonthly"]
    portfolio_income = plan["portfolioIncomeMonthly"]
    other_income = plan["otherIncomeMonthly"]
    total_income = portfolio_income + other_income

    annual_spend = monthly_spend * 12
    annual_income = total_income * 12

    # Cash reserves
    cash = sum(a["balance"] for a in accounts if a["type"] == "cash")

    # Project forward with inflation on spending, income flat (conservative)
    projections = []
    crossover_year = None
    for year in range(1, 21):
        inflated_spend = annual_spend * (1 + inflation_rate) ** year
        gap = annual_income - inflated_spend
        surplus = gap >= 0
        if not surplus and crossover_year is None:
            crossover_year = year
        projections.append({
            "year": year,
            "annualIncome": js_round(annual_income),
            "annualSpending": js_round(inflated_spend),
            "annualGap": js_round(gap),
            "surplus": surplus,
        })

    # Current monthly surplus/deficit
    monthly_gap = total_income - monthly_spend

    # Years of cash runway if spending exceeds income
    cash_runway_years = None
    if monthly_gap < 0:
        cash_runway_years = js_round(cash / (abs(monthly_gap) * 12))

    # Sustainable spending (income-only, no portfolio drawdown)
    sustainable_monthly = total_income

    return {
        "currentMonthly": {
            "income": total_income,
            "spending": monthly_spend,
            "gap": monthly_gap,
            "surplus": monthly_gap >= 0,
        },
        "sustainableMonthlySpend": sustainable_monthly,
        "overSpendPct": js_round((monthly_spend - total_income) / total_income * 100)
        if monthly_spend > total_income
        else 0,
        "cashReserves": cash,
        "cashRunwayYears": cash_runway_years,
        "crossoverYear": crossover_year,
        "projections": [p for p in projections if p["year"] in (1, 3, 5, 10, 15, 20)],
        "interpretation": _interpret_income(monthly_gap, crossover_year, cash_runway_years),
    }


def _interpret_income(gap: float, crossover: int | None, runway: float | None) -> str:
    if gap >= 0:
        return (
            f"Income exceeds spending by {fmt_usd(gap)}/mo. "
            "Plan is self-sustaining without portfolio drawdown."
        )
    parts = [f"Spending exceeds income by {fmt_usd(abs(gap))}/mo — drawing from portfolio."]
    if crossover and crossover <= 5:
        parts.append(f"With inflation, gap widens significantly within {crossover} years.")
    if runway is not None:
        parts.append(f"Cash reserves cover ~{runway:.1f} years at current draw rate.")
    return " ".join(parts)
