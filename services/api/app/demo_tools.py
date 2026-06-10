from __future__ import annotations

from math import pow

from .models import AdvisorAction, HouseholdProfile, MetricCard, PortfolioPosition, ToolResult


DISCLOSURE = (
    "Planning outputs are estimates for discussion with a qualified advisor and are not tax, "
    "legal, or investment advice."
)


def _currency(value: float) -> str:
    return f"${value:,.0f}"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def retirement_readiness(household: HouseholdProfile) -> ToolResult:
    years_to_retirement = max(household.retirement_age - household.primary_age, 0)
    projected = household.portfolio_value * pow(1.052, years_to_retirement)
    projected += household.annual_savings * ((pow(1.052, years_to_retirement) - 1) / 0.052) if years_to_retirement else 0
    first_year_need = max(household.annual_expenses - household.annual_income * 0.18, 0)
    target = first_year_need * 25
    success_score = min(projected / target, 1.35) if target else 1.35
    success_rate = min(max(0.42 + success_score * 0.42, 0.05), 0.96)
    tone = "good" if success_rate >= 0.8 else "warning" if success_rate >= 0.65 else "danger"
    summary = (
        f"Estimated retirement readiness is {_percent(success_rate)}. "
        f"At age {household.retirement_age}, projected portfolio value is about {_currency(projected)} "
        f"against an estimated target of {_currency(target)}."
    )
    return ToolResult(
        tool="retirement_readiness",
        summary=summary,
        cards=[
            MetricCard(label="Readiness", value=_percent(success_rate), tone=tone, detail="Modeled success estimate"),
            MetricCard(label="Projected assets", value=_currency(projected), tone="neutral"),
            MetricCard(label="Estimated target", value=_currency(target), tone="neutral"),
        ],
        actions=[
            AdvisorAction(
                title="Review retirement age and spending goal",
                priority="high" if tone == "danger" else "medium",
                rationale="These two assumptions drive most of the gap or surplus.",
            ),
            AdvisorAction(
                title="Run a downside market stress case",
                priority="medium",
                rationale="Stress testing helps separate acceptable risk from fragile confidence.",
            ),
        ],
        data={"success_rate": success_rate, "projected_assets": projected, "target_assets": target},
        disclaimers=[DISCLOSURE],
    )


def roth_conversion(household: HouseholdProfile) -> ToolResult:
    bracket_room = max(383900 - household.annual_income, 0) if household.filing_status == "married_filing_jointly" else max(191950 - household.annual_income, 0)
    suggested = min(bracket_room, household.portfolio_value * 0.04)
    tax_cost = suggested * household.effective_tax_rate
    summary = (
        f"A Roth conversion up to about {_currency(suggested)} may be worth testing, "
        f"with an estimated current-year tax cost near {_currency(tax_cost)}."
    )
    return ToolResult(
        tool="roth_conversion",
        summary=summary,
        cards=[
            MetricCard(label="Candidate conversion", value=_currency(suggested), tone="neutral"),
            MetricCard(label="Estimated tax cost", value=_currency(tax_cost), tone="warning"),
            MetricCard(label="Bracket room", value=_currency(bracket_room), tone="neutral"),
        ],
        actions=[
            AdvisorAction(
                title="Confirm taxable income before year-end",
                priority="high",
                rationale="Conversion room changes when bonuses, capital gains, or deductions change.",
            )
        ],
        data={"suggested_conversion": suggested, "estimated_tax_cost": tax_cost},
        disclaimers=[DISCLOSURE],
    )


def social_security(household: HouseholdProfile) -> ToolResult:
    full_retirement_age = 67
    early = 0.70
    delayed = 1.24
    summary = (
        "Delaying Social Security can materially raise lifetime inflation-linked income, "
        "but the best choice depends on health, survivor needs, and bridge portfolio risk."
    )
    return ToolResult(
        tool="social_security",
        summary=summary,
        cards=[
            MetricCard(label="Claim at 62", value=_percent(early), tone="warning", detail="Approximate FRA benefit share"),
            MetricCard(label="Claim at 67", value="100.0%", tone="neutral", detail="Full retirement age assumption"),
            MetricCard(label="Claim at 70", value=_percent(delayed), tone="good", detail="Delayed retirement credit estimate"),
        ],
        actions=[
            AdvisorAction(
                title="Compare claiming ages with spouse survivor impact",
                priority="medium",
                rationale="The household answer can differ from the highest individual benefit.",
            )
        ],
        data={"full_retirement_age": full_retirement_age},
        disclaimers=[DISCLOSURE],
    )


def tax_optimization(household: HouseholdProfile) -> ToolResult:
    estimated_tax = household.annual_income * household.effective_tax_rate
    savings_range = estimated_tax * 0.04
    return ToolResult(
        tool="tax_optimization",
        summary=f"Estimated annual tax exposure is {_currency(estimated_tax)}. A focused review may find {_currency(savings_range)} in planning opportunities.",
        cards=[
            MetricCard(label="Estimated tax", value=_currency(estimated_tax), tone="neutral"),
            MetricCard(label="Opportunity range", value=_currency(savings_range), tone="good"),
        ],
        actions=[
            AdvisorAction(title="Review Roth conversion room", priority="high", rationale="Conversions are time-sensitive by tax year."),
            AdvisorAction(title="Check taxable losses and gains", priority="medium", rationale="Harvesting and gain realization should be coordinated."),
        ],
        data={"estimated_tax": estimated_tax, "opportunity_range": savings_range},
        disclaimers=[DISCLOSURE],
    )


def default_portfolio() -> list[PortfolioPosition]:
    return [
        PortfolioPosition(symbol="VTI", name="US Total Market", asset_class="US Equity", value=520000, cost_basis=430000, target_weight=0.45),
        PortfolioPosition(symbol="VXUS", name="International Equity", asset_class="International Equity", value=210000, cost_basis=235000, target_weight=0.20),
        PortfolioPosition(symbol="BND", name="Core Bonds", asset_class="Fixed Income", value=310000, cost_basis=315000, target_weight=0.30),
        PortfolioPosition(symbol="CASH", name="Cash", asset_class="Cash", value=60000, cost_basis=60000, target_weight=0.05),
    ]


def portfolio_review(portfolio: list[PortfolioPosition] | None = None) -> ToolResult:
    positions = portfolio or default_portfolio()
    total = sum(p.value for p in positions) or 1
    drift_rows = []
    max_drift = 0.0
    for p in positions:
        actual = p.value / total
        drift = actual - p.target_weight
        max_drift = max(max_drift, abs(drift))
        drift_rows.append({"symbol": p.symbol, "actual": actual, "target": p.target_weight, "drift": drift})
    tone = "good" if max_drift < 0.04 else "warning" if max_drift < 0.08 else "danger"
    return ToolResult(
        tool="portfolio_review",
        summary=f"Portfolio value is {_currency(total)}. Largest model drift is {_percent(max_drift)}.",
        cards=[
            MetricCard(label="Portfolio value", value=_currency(total), tone="neutral"),
            MetricCard(label="Largest drift", value=_percent(max_drift), tone=tone),
            MetricCard(label="Positions", value=str(len(positions)), tone="neutral"),
        ],
        actions=[
            AdvisorAction(title="Review model drift", priority="high" if tone == "danger" else "medium", rationale="Large drift may change risk exposure."),
            AdvisorAction(title="Coordinate rebalancing with taxes", priority="medium", rationale="Selling appreciated positions can create tax cost."),
        ],
        data={"drift": drift_rows},
        disclaimers=[DISCLOSURE],
    )


def tax_loss_harvesting(portfolio: list[PortfolioPosition] | None = None) -> ToolResult:
    positions = portfolio or default_portfolio()
    losses = [{"symbol": p.symbol, "loss": p.cost_basis - p.value} for p in positions if p.cost_basis > p.value]
    total_loss = sum(row["loss"] for row in losses)
    return ToolResult(
        tool="tax_loss_harvesting",
        summary=f"Potential unrealized losses total {_currency(total_loss)} across {len(losses)} position(s).",
        cards=[
            MetricCard(label="Harvestable losses", value=_currency(total_loss), tone="good" if total_loss > 0 else "neutral"),
            MetricCard(label="Candidates", value=str(len(losses)), tone="neutral"),
        ],
        actions=[
            AdvisorAction(title="Run wash sale review before trading", priority="high", rationale="A replacement trade can accidentally disallow the tax loss."),
        ],
        data={"candidates": losses},
        disclaimers=[DISCLOSURE],
    )


def wash_sale_check() -> ToolResult:
    return ToolResult(
        tool="wash_sale_check",
        summary="No live trade history is connected in demo mode, so this is a process reminder rather than a clearance.",
        cards=[MetricCard(label="Status", value="Needs live data", tone="warning")],
        actions=[
            AdvisorAction(title="Connect trade lots and recent transactions", priority="high", rationale="Wash sale checks require recent buys, sells, and replacement securities."),
        ],
        data={"requires_live_lots": True},
        disclaimers=[DISCLOSURE],
    )

