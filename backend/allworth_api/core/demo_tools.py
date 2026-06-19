"""Legacy demo tool implementations.

These tools power the original app screens and legacy demo flows. They are
kept separate from the composable financial tool registry so `tool_runner`
only has to orchestrate execution, diagnostics, and audit logging.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from allworth_api.core.formatting import fmt_usd
from allworth_api.core.memory import active_facts, add_facts, profile_as_context
from allworth_api.core.nudges import nudges_for
from allworth_api.core.tax import simulate_tax_impact
from allworth_api.data.seed import accounts_for, seed, spending_summary
from allworth_api.financial_tools.data import get_portfolio as get_layered_portfolio

ToolHandler = Callable[[dict[str, Any], str], dict[str, Any]]


def _strip_history(acct: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in acct.items() if k != "history"}


def _get_accounts(_tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    accounts = accounts_for()
    return {
        "netWorth": accounts["netWorth"],
        "allworthManagedTotal": accounts["allworthTotal"],
        "heldAwayTotal": accounts["heldAwayTotal"],
        "liabilitiesTotal": accounts["liabilitiesTotal"],
        "accounts": [_strip_history(acct) for acct in seed["accounts"]],
        "netWorthHistory": seed["netWorthHistory"],
    }


def _get_portfolio(_tool_input: dict[str, Any], client_id: str) -> dict[str, Any]:
    return get_layered_portfolio(client_id)


def _get_financial_plan(_tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    return {"plan": seed["plan"], "liquidityEvent": seed["liquidityEvent"]}


def _get_spending(tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    spending = spending_summary(tool_input.get("months") or 3)
    return {
        "recentMonths": spending["months"],
        "avg3mo": spending["avg3mo"],
        "plannedMonthly": spending["plan"],
        "overPlanPct": spending["overPlanPct"],
        "note": (
            f"Spending is averaging {fmt_usd(spending['avg3mo'])}/mo against a "
            f"{fmt_usd(spending['plan'])}/mo plan ({spending['overPlanPct']}% over). "
            "Travel and Gifts/Family drive most of the difference."
        ),
    }


def _get_client_profile(_tool_input: dict[str, Any], client_id: str) -> dict[str, Any]:
    return {
        "clientId": client_id,
        "facts": active_facts(client_id),
        "summary": profile_as_context(client_id),
    }


def _update_client_profile(tool_input: dict[str, Any], client_id: str) -> dict[str, Any]:
    added = add_facts(client_id, [tool_input], None)
    if added:
        return {"saved": True, "fact": added[0]}
    return {"saved": False, "reason": "Similar fact already on file."}


def _simulate_tax_impact(tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    return simulate_tax_impact(
        tool_input.get("amount"),
        tool_input.get("accountId"),
        tool_input.get("symbol"),
        positions=seed["positions"],
        tax_lots=seed["taxLots"],
    )


def _get_advisor_brief(_tool_input: dict[str, Any], client_id: str) -> dict[str, Any]:
    accounts = accounts_for()
    return {
        "client": next((c for c in seed["personas"]["clients"] if c["id"] == client_id), None),
        "managedTotal": accounts["allworthTotal"],
        "heldAwayDetected": accounts["heldAwayTotal"],
        "heldAwayAccounts": [_strip_history(x) for x in accounts["outside"] if x["type"] != "liability"],
        "liabilities": [_strip_history(x) for x in accounts["outside"] if x["type"] == "liability"],
        "openNudges": nudges_for(client_id),
        "profile": active_facts(client_id),
        "liquidityEvent": seed["liquidityEvent"],
    }


def _run_retirement_projection(tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    from allworth_api.core.planning import run_retirement_projection

    return run_retirement_projection(
        end_age=tool_input.get("end_age", 95),
        n_simulations=tool_input.get("n_simulations", 500),
    )


def _analyze_portfolio_drift(tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    from allworth_api.core.planning import analyze_portfolio_drift

    return analyze_portfolio_drift(account_id=tool_input.get("accountId"))


def _run_roth_conversion_analysis(tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    from allworth_api.core.planning import run_roth_conversion_analysis

    return run_roth_conversion_analysis(
        conversion_amount=tool_input.get("conversion_amount"),
        current_income=tool_input.get("current_income"),
    )


def _analyze_goal_funding(tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    from allworth_api.core.planning import analyze_goal_funding

    return analyze_goal_funding(growth_rate=tool_input.get("growth_rate", 0.06))


def _analyze_income_sustainability(tool_input: dict[str, Any], _client_id: str) -> dict[str, Any]:
    from allworth_api.core.planning import analyze_income_sustainability

    return analyze_income_sustainability(inflation_rate=tool_input.get("inflation_rate", 0.03))


DEMO_TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_accounts": _get_accounts,
    "get_portfolio": _get_portfolio,
    "get_financial_plan": _get_financial_plan,
    "get_spending": _get_spending,
    "get_client_profile": _get_client_profile,
    "update_client_profile": _update_client_profile,
    "simulate_tax_impact": _simulate_tax_impact,
    "get_advisor_brief": _get_advisor_brief,
    "run_retirement_projection": _run_retirement_projection,
    "analyze_portfolio_drift": _analyze_portfolio_drift,
    "run_roth_conversion_analysis": _run_roth_conversion_analysis,
    "analyze_goal_funding": _analyze_goal_funding,
    "analyze_income_sustainability": _analyze_income_sustainability,
}

DEMO_TOOL_NAMES = set(DEMO_TOOL_HANDLERS)


def is_demo_tool(name: str) -> bool:
    return name in DEMO_TOOL_HANDLERS


def run_demo_tool(name: str, tool_input: dict[str, Any] | None, client_id: str) -> dict[str, Any]:
    handler = DEMO_TOOL_HANDLERS.get(name)
    if not handler:
        return {"error": f"Unknown demo tool: {name}"}
    return handler(tool_input or {}, client_id)
