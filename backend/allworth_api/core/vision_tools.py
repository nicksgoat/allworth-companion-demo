"""Canonical product tools from docs/ALLWORTH_AI_APP_CANONICAL.md.

These are facade tools: they expose the product vision's five-tool architecture
while reusing the existing data, Monte Carlo, rebalancer, and memory layers.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from allworth_api.core.memory import active_facts
from allworth_api.data.advisors import advisor_for_client
from allworth_api.data.seed import accounts_for, portfolio_for, seed
from allworth_api.financial_tools.compute import simulate
from allworth_api.financial_tools.data import DEFAULT_MODEL_ID
from allworth_api.financial_tools.tools import run_financial_tool

VISION_TOOL_LABELS = {
    "get_client_context": "Reading client context...",
    "get_portfolio_analytics": "Analyzing portfolio...",
    "run_monte_carlo": "Running Monte Carlo...",
    "run_mock_rebalance": "Calculating rebalance...",
    "get_document": "Reading planning notes...",
}

VISION_TOOL_DEFINITIONS = [
    {
        "name": "get_client_context",
        "description": "Foundation data tool. Fetch the client's profile, goals, accounts, tax profile, "
        "planning assumptions, advisor, and remembered facts. Call first for substantive questions.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}},
            "required": [],
        },
    },
    {
        "name": "get_portfolio_analytics",
        "description": "Portfolio state tool. Returns current allocation, target allocation, drift, "
        "concentration flags, holdings, tax lots, and broad factor exposure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "account_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": [],
        },
    },
    {
        "name": "run_monte_carlo",
        "description": "Vision-compatible Monte Carlo planning tool. Use for retirement timing, "
        "runway, goal probability, and affordability questions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "portfolio_value": {"type": "number"},
                "monthly_contribution": {"type": "number", "default": 0},
                "monthly_withdrawal_needed": {"type": "number"},
                "time_horizon_years": {"type": "integer", "default": 25},
                "n_simulations": {"type": "integer", "default": 1000},
                "goal_amount": {"type": "number"},
            },
            "required": [],
        },
    },
    {
        "name": "run_mock_rebalance",
        "description": "Vision-compatible rebalance tool. Proposes deterministic mock trades, tax impact, "
        "tax-loss harvesting flags, and allocation after rebalance. Nothing executes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "account_ids": {"type": "array", "items": {"type": "string"}},
                "model_id": {"type": "string", "default": DEFAULT_MODEL_ID},
                "target_allocation": {"type": "object", "additionalProperties": {"type": "number"}},
                "tlh_enabled": {"type": "boolean", "default": True},
                "tax_bracket": {"type": "number"},
                "loss_carryforward": {"type": "number"},
                "tax_budget": {"type": "object"},
            },
            "required": [],
        },
    },
    {
        "name": "get_document",
        "description": "Planning document retrieval tool. Returns synthetic IPS, financial plan, "
        "meeting-note, or proposal extracts so answers can reflect qualitative intent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "document_type": {
                    "type": "string",
                    "enum": ["IPS", "financial_plan", "meeting_notes", "proposal"],
                    "default": "financial_plan",
                },
                "max_tokens": {"type": "integer", "default": 2000},
            },
            "required": [],
        },
    },
]

VISION_TOOL_NAMES = {tool["name"] for tool in VISION_TOOL_DEFINITIONS}


def is_vision_tool(name: str) -> bool:
    return name in VISION_TOOL_NAMES


def run_vision_tool(name: str, tool_input: dict[str, Any] | None, client_id: str) -> dict[str, Any]:
    tool_input = tool_input or {}
    if name == "get_client_context":
        return get_client_context(client_id)
    if name == "get_portfolio_analytics":
        account_ids = tool_input.get("account_ids") or tool_input.get("accountIds")
        return get_portfolio_analytics(client_id, account_ids)
    if name == "run_monte_carlo":
        return run_monte_carlo(client_id, tool_input)
    if name == "run_mock_rebalance":
        return run_mock_rebalance(client_id, tool_input)
    if name == "get_document":
        return get_document(client_id, tool_input.get("document_type", "financial_plan"))
    return {"error": f"Unknown vision tool: {name}"}


def get_client_context(client_id: str) -> dict[str, Any]:
    client = next((c for c in seed["personas"]["clients"] if c["id"] == client_id), None)
    accounts = accounts_for()
    plan = seed["plan"]
    return {
        "client_id": client_id,
        "name": (client or {}).get("name", client_id),
        "age": (client or {}).get("age"),
        "retirement_date_target": "2027-01",
        "risk_tolerance": "moderate",
        "time_horizon_years": 25,
        "tax_bracket": plan.get("taxProfile", {}).get("marginalRate", 0.32),
        "filing_status": plan.get("taxProfile", {}).get("filingStatus", "married_joint"),
        "state": "TX",
        "loss_carryforward": plan.get("taxProfile", {}).get("lossCarryforward", 0),
        "rmd_applicable": False,
        "goals": plan.get("goals", []),
        "accounts": [
            {"account_id": acct["id"], "type": acct["type"], "balance": acct["balance"]}
            for acct in accounts["allworth"] + accounts["outside"]
        ],
        "advisor": advisor_for_client(client_id),
        "remembered_facts": active_facts(client_id),
        "source": "seed_or_synapse_shaped_context",
    }


def get_portfolio_analytics(client_id: str, account_ids: list[str] | None = None) -> dict[str, Any]:
    portfolio = portfolio_for()
    account_filter = set(account_ids or [])
    positions = [
        p for p in portfolio["positions"] if not account_filter or p.get("accountId") in account_filter
    ]
    total_value = sum(float(p["value"]) for p in positions)
    by_class: dict[str, float] = defaultdict(float)
    for position in positions:
        by_class[_broad_asset_class(position.get("assetClass", ""))] += float(position["value"])
    current_allocation = {
        asset_class: round(value / total_value, 4)
        for asset_class, value in sorted(by_class.items())
        if total_value
    }
    target_allocation = {"equity": 0.65, "fixed_income": 0.30, "cash": 0.05}
    drift = {
        key: round(current_allocation.get(key, 0.0) - target_allocation.get(key, 0.0), 4)
        for key in sorted(set(current_allocation) | set(target_allocation))
    }
    drift_score = round(sum(abs(value) for value in drift.values()) / 2, 4)
    holdings = _holdings_with_aggregate_basis(positions)
    return {
        "total_value": round(total_value, 2),
        "current_allocation": current_allocation,
        "target_allocation": target_allocation,
        "drift": drift,
        "drift_score": drift_score,
        "rebalance_needed": drift_score >= 0.05,
        "holdings": holdings,
        "concentration_flags": _concentration_flags(positions, total_value),
        "factor_exposures": {
            "beta": 1.08 if current_allocation.get("equity", 0) > 0.65 else 0.92,
            "us_equity_tilt": "large_growth",
        },
        "source": "portfolio_positions_with_aggregate_basis",
    }


def run_monte_carlo(client_id: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    accounts = accounts_for()
    plan = seed["plan"]
    portfolio_value = float(tool_input.get("portfolio_value") or accounts["allworthTotal"])
    monthly_contribution = float(tool_input.get("monthly_contribution", 0))
    monthly_withdrawal = float(
        tool_input.get("monthly_withdrawal_needed") or plan.get("spendingAssumptionMonthly", 0)
    )
    years = int(tool_input.get("time_horizon_years", 25))
    annual_net_flow = (monthly_contribution - monthly_withdrawal) * 12
    simulation = simulate(
        initial_value=portfolio_value,
        annual_contribution=annual_net_flow,
        expected_annual_return=0.06,
        annual_volatility=0.12,
        years=years,
        n_simulations=int(tool_input.get("n_simulations", 1000)),
        goal_amount=tool_input.get("goal_amount"),
    )
    terminal = simulation["terminal_value"]
    success_probability = round(1 - simulation["prob_of_ruin"], 4)
    return {
        "client_id": client_id,
        "probability_of_success": success_probability,
        "median_ending_value": terminal["p50"],
        "percentiles": {
            "p10": terminal["p10"],
            "p25": terminal["p25"],
            "p50": terminal["p50"],
            "p75": terminal["p75"],
            "p90": terminal["p90"],
        },
        "median_depletion_age": None,
        "p10_depletion_age": None if terminal["p10"] > 0 else 84,
        "shortfall_risk": {
            "probability": simulation["prob_of_ruin"],
            "median_shortfall_amount": 0 if terminal["p50"] > 0 else abs(terminal["p50"]),
        },
        "years_of_runway_at_p10": years if terminal["p10"] > 0 else max(0, years - 7),
        "assumptions": {
            "portfolio_value": portfolio_value,
            "annual_net_flow": annual_net_flow,
            "time_horizon_years": years,
            "expected_annual_return": 0.06,
            "annual_volatility": 0.12,
        },
    }


def run_mock_rebalance(client_id: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    tax_bracket = tool_input.get("tax_bracket")
    tax_budget = tool_input.get("tax_budget")
    if not tax_budget and tax_bracket:
        tax_budget = {
            "max_tax": tool_input.get("max_tax", 25_000),
            "long_term_rate": min(float(tax_bracket), 0.20),
            "short_term_rate": float(tax_bracket),
        }
    result = run_financial_tool(
        "rebalance",
        {
            "model_id": tool_input.get("model_id") or DEFAULT_MODEL_ID,
            "account_id": (tool_input.get("account_ids") or [None])[0],
            "target_allocation": tool_input.get("target_allocation"),
            "tax_budget": tax_budget,
        },
        client_id,
    )
    if "error" in result:
        return result
    proposed_trades = []
    net_tlh_harvested = 0.0
    for trade in result["trades"]:
        realized_gain = float(trade.get("realized_gain", 0))
        tlh_flag = bool(realized_gain < 0 and tool_input.get("tlh_enabled", True))
        if tlh_flag:
            net_tlh_harvested += abs(realized_gain)
        proposed_trades.append(
            {
                "ticker": trade["ticker"],
                "action": trade["action"].lower(),
                "estimated_proceeds": trade["amount"] if trade["action"] == "SELL" else 0,
                "amount": trade["amount"],
                "realized_gain": realized_gain,
                "tax_impact": trade.get("estimated_tax", 0),
                "holding_period": trade.get("gain_term"),
                "tlh_flag": tlh_flag,
                "tlh_replacement": "IXUS" if tlh_flag and trade["ticker"] == "VXUS" else None,
            }
        )
    loss_carryforward = float(tool_input.get("loss_carryforward", 0) or 0)
    net_tax = float(result["estimated_tax"]["total"])
    return {
        "proposed_trades": proposed_trades,
        "net_tax_impact": round(net_tax, 2),
        "net_tlh_harvested": round(net_tlh_harvested, 2),
        "net_after_carryforward": round(max(net_tax - loss_carryforward, 0), 2),
        "allocation_after_rebalance": result["post_trade_allocation"],
        "estimated_transition_cost": round(net_tax, 2),
        "tax_calculation": result.get("tax_calculation"),
        "underlying_rebalance": result,
    }


def get_document(client_id: str, document_type: str = "financial_plan") -> dict[str, Any]:
    profile_facts = active_facts(client_id)
    extracts = {
        "stated_goals": [fact["fact"] for fact in profile_facts if fact.get("category") == "goals"],
        "advisor_notes": (
            "Client prefers plain-English explanations, is tax-sensitive around concentrated "
            "stock sales, and wants advisor review before any trade."
        ),
        "last_review_date": "2026-06-10",
    }
    content_by_type = {
        "IPS": "Moderate risk target with diversified Core-Satellite allocation and advisor review.",
        "financial_plan": (
            "Plan emphasizes retirement income, lake house funding, 529 gifts, tax-aware liquidity, "
            "and avoiding surprise capital gains."
        ),
        "meeting_notes": (
            "Recent conversations focused on liquidity, spending above plan, held-away assets, "
            "and whether a tax-aware rebalance could lower portfolio risk."
        ),
        "proposal": "No trade is executed by the assistant. Any proposal is advisor-reviewed first.",
    }
    return {
        "client_id": client_id,
        "document_type": document_type,
        "last_updated": "2026-06-10",
        "content": content_by_type.get(document_type, content_by_type["financial_plan"]),
        "key_extracts": extracts,
        "source": "synthetic_planning_documents",
    }


def _broad_asset_class(asset_class: str) -> str:
    lower = asset_class.lower()
    if "cash" in lower:
        return "cash"
    if "bond" in lower:
        return "fixed_income"
    return "equity"


def _holdings_with_aggregate_basis(positions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    holdings = []
    for position in positions:
        market_value = float(position["value"])
        cost_basis = float(position.get("costBasis", market_value) or market_value)
        holdings.append(
            {
                "ticker": position["symbol"],
                "shares": position.get("qty"),
                "market_value": round(market_value, 2),
                "average_cost_basis": position.get("averageCostBasis"),
                "cost_basis": round(cost_basis, 2),
                "unrealized_gain": round(market_value - cost_basis, 2),
                "long_term_unrealized_gain": position.get("longTermUnrealizedGain", 0),
                "short_term_unrealized_gain": position.get("shortTermUnrealizedGain", 0),
            }
        )
    return holdings


def _concentration_flags(positions: list[dict[str, Any]], total_value: float) -> list[str]:
    if total_value <= 0:
        return []
    return [
        f"{position['symbol']} > 8% of portfolio"
        for position in positions
        if float(position["value"]) / total_value > 0.08 and position["symbol"] != "CASH"
    ]
