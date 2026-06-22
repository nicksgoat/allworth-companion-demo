"""Financial tool registry and dispatcher.

This module is the single source of truth for financial tool metadata and
execution. Chat tool-calling, HTTP routes, and MCP can all use the same tool
contracts without duplicating schemas or business logic.
"""

from __future__ import annotations

from typing import Any

from allworth_api.financial_tools.compute import rebalance, simulate
from allworth_api.financial_tools.data import (
    DEFAULT_MODEL_ID,
    get_default_rebalance_holdings,
    get_model_allocation,
)

FINANCIAL_TOOL_LABELS = {
    "simulate": "Running simulation…",
    "rebalance": "Calculating rebalance trades…",
}

FINANCIAL_TOOL_DEFINITIONS = [
    {
        "name": "simulate",
        "description": "Deterministic-seed Monte Carlo simulator for baseline and decision scenarios. "
        "For a one-time purchase or windfall, change initial_value. For an ongoing saving or "
        "spending change, change annual_contribution.",
        "input_schema": {
            "type": "object",
            "properties": {
                "initial_value": {"type": "number"},
                "annual_contribution": {"type": "number", "default": 0},
                "expected_annual_return": {"type": "number", "default": 0.07},
                "annual_volatility": {"type": "number", "default": 0.15},
                "years": {"type": "integer", "default": 20},
                "n_simulations": {"type": "integer", "default": 10000},
                "goal_amount": {"type": "number"},
            },
            "required": ["initial_value"],
        },
    },
    {
        "name": "rebalance",
        "description": "Deterministic mock rebalancer. Uses target_allocation directly or resolves "
        "model_id from mock tho.model_list and tho.Asset_Allocation_Security_Weights data. "
        "Can cap realized gains or estimated tax by long-term and short-term gain buckets.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model_id": {
                    "type": "string",
                    "default": "AWF - Core-Satellite - 60/40",
                    "description": "Mock model ID from tho.model_list.",
                },
                "current_holdings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string"},
                            "value": {"type": "number"},
                            "cost_basis": {"type": "number"},
                            "average_cost_basis": {"type": "number"},
                            "cost_basis_ratio": {"type": "number"},
                            "gain_term": {"type": "string", "enum": ["long", "short"]},
                            "long_term_value": {"type": "number"},
                            "long_term_cost_basis": {"type": "number"},
                            "long_term_unrealized_gain": {"type": "number"},
                            "short_term_value": {"type": "number"},
                            "short_term_cost_basis": {"type": "number"},
                            "short_term_unrealized_gain": {"type": "number"},
                            "tax_lots": {
                                "type": "array",
                                "description": "Optional future extension. Current app data is aggregate-only.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "id": {"type": "string"},
                                        "value": {"type": "number"},
                                        "cost_basis": {"type": "number"},
                                        "unrealized_gain": {"type": "number"},
                                        "gain_term": {"type": "string", "enum": ["long", "short"]},
                                    },
                                    "required": ["value"],
                                },
                            },
                        },
                        "required": ["ticker", "value"],
                    },
                },
                "target_allocation": {
                    "type": "object",
                    "additionalProperties": {"type": "number"},
                },
                "realized_gains_budget": {
                    "type": "object",
                    "properties": {
                        "long_term": {"type": "number"},
                        "short_term": {"type": "number"},
                    },
                    "description": "Optional realized gains caps by term.",
                },
                "tax_budget": {
                    "type": "object",
                    "properties": {
                        "max_tax": {"type": "number"},
                        "long_term_rate": {"type": "number"},
                        "short_term_rate": {"type": "number"},
                    },
                    "description": "Optional tax cap and rates for realized gains.",
                },
            },
            "required": [],
        },
    },
]

FINANCIAL_TOOL_NAMES = {tool["name"] for tool in FINANCIAL_TOOL_DEFINITIONS}


def is_financial_tool(name: str) -> bool:
    return name in FINANCIAL_TOOL_NAMES


def run_financial_tool(name: str, tool_input: dict[str, Any] | None, client_id: str) -> dict[str, Any]:
    """Execute a financial tool by name."""
    tool_input = tool_input or {}

    if name == "simulate":
        return simulate(
            initial_value=tool_input["initial_value"],
            annual_contribution=tool_input.get("annual_contribution", 0.0),
            expected_annual_return=tool_input.get("expected_annual_return", 0.07),
            annual_volatility=tool_input.get("annual_volatility", 0.15),
            years=tool_input.get("years", 20),
            n_simulations=tool_input.get("n_simulations", 10_000),
            goal_amount=tool_input.get("goal_amount"),
        )
    if name == "rebalance":
        model_id = tool_input.get("model_id") or tool_input.get("modelId") or DEFAULT_MODEL_ID
        model_data = get_model_allocation(model_id)
        if "error" in model_data:
            return model_data
        target_allocation = tool_input.get("target_allocation") or tool_input.get("targetAllocation")
        holdings = tool_input.get("current_holdings") or tool_input.get("currentHoldings")
        if target_allocation is None:
            target_allocation = model_data["target_allocation"]
        if holdings is None:
            holdings = get_default_rebalance_holdings(client_id, tool_input.get("account_id"))
        result = rebalance(
            current_holdings=holdings,
            target_allocation=target_allocation,
            realized_gains_budget=tool_input.get("realized_gains_budget")
            or tool_input.get("realizedGainsBudget"),
            tax_budget=tool_input.get("tax_budget") or tool_input.get("taxBudget"),
        )
        if "error" not in result:
            result["model"] = model_data["model"]
            result["allocation_source_table"] = model_data["allocation_source_table"]
        return result

    return {"error": f"Unknown financial tool: {name}"}
