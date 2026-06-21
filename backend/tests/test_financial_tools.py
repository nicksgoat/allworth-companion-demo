from __future__ import annotations

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.core.tool_defs import TOOL_DEFINITIONS
from allworth_api.core.tool_runner import run_tool
from allworth_api.financial_tools.tools import FINANCIAL_TOOL_DEFINITIONS, FINANCIAL_TOOL_NAMES

client = TestClient(app)


def test_financial_tool_surface_is_monte_carlo_and_rebalancer_only() -> None:
    global_tool_names = {tool["name"] for tool in TOOL_DEFINITIONS}
    financial_tool_names = {tool["name"] for tool in FINANCIAL_TOOL_DEFINITIONS}

    assert financial_tool_names == {"simulate", "rebalance"}
    assert financial_tool_names == FINANCIAL_TOOL_NAMES
    assert financial_tool_names <= global_tool_names


def test_monte_carlo_is_deterministic() -> None:
    payload = {
        "initial_value": 100_000,
        "annual_contribution": 5_000,
        "years": 10,
        "n_simulations": 500,
        "goal_amount": 200_000,
    }

    first = client.post("/tools/simulate", json=payload).json()
    second = client.post("/tools/simulate", json=payload).json()

    assert first == second
    assert set(first) == {
        "terminal_value",
        "prob_of_ruin",
        "prob_of_reaching_goal",
        "prob_of_reaching_goal_pct",
    }
    assert set(first["terminal_value"]) == {"p10", "p25", "p50", "p75", "p90", "mean"}


def test_rebalancer_defaults_to_mock_synapse_model_tables() -> None:
    result = client.post("/tools/rebalance", json={"model_id": "AWF - Core-Satellite - 60/40"}).json()

    assert result["model"]["source_table"] == "tho.model_list"
    assert result["allocation_source_table"] == "tho.Asset_Allocation_Security_Weights"
    assert result["model"]["model_set"] == "Core-Satellite"
    assert result["model"]["model_id"] == "AWF - Core-Satellite - 60/40"
    assert round(sum(result["target_allocation"].values()), 6) == 1.0
    assert {"BND", "VTI", "SPDW"} <= set(result["target_allocation"])
    assert result["trades"]
    assert set(result) == {
        "total_portfolio_value",
        "target_allocation",
        "post_trade_allocation",
        "trades",
        "realized_gains",
        "estimated_tax",
        "residual_drift",
        "budget_limited",
        "model",
        "allocation_source_table",
    }


def test_seed_contains_only_core_satellite_models_for_rebalancer() -> None:
    from allworth_api.data.seed import seed_for

    seed = seed_for("maya")
    model_rows = seed["allocationModels"]["modelList"]
    weight_rows = seed["allocationModels"]["securityWeights"]
    model_names = {row["allocation_model_name"] for row in model_rows}

    assert len(model_rows) == 66
    assert len(weight_rows) == 1350
    assert {row["model_set"] for row in model_rows} == {"Core-Satellite"}
    assert {row["allocation_model_name"] for row in weight_rows} <= model_names
    assert "AWF - Core-Satellite - 60/40" in model_names
    assert "AWF - Core-Satellite Plus TE CA - 60/40" in model_names


def test_rebalancer_honors_long_and_short_realized_gains_budget() -> None:
    result = client.post(
        "/tools/rebalance",
        json={
            "current_holdings": [
                {"ticker": "AAPL", "value": 100_000, "cost_basis": 50_000, "gain_term": "long"},
                {"ticker": "NVDA", "value": 100_000, "cost_basis": 90_000, "gain_term": "short"},
                {"ticker": "BND", "value": 100_000, "cost_basis": 100_000, "gain_term": "long"},
            ],
            "target_allocation": {"AAPL": 0.1, "NVDA": 0.1, "BND": 0.8},
            "realized_gains_budget": {"long_term": 10_000, "short_term": 1_000},
        },
    ).json()

    assert result["budget_limited"] is True
    assert result["realized_gains"]["long_term"] <= 10_000.01
    assert result["realized_gains"]["short_term"] <= 1_000.01
    assert any(trade["action"] == "BUY" and trade["ticker"] == "BND" for trade in result["trades"])


def test_rebalancer_honors_tax_budget() -> None:
    result = run_tool(
        "rebalance",
        {
            "current_holdings": [
                {"ticker": "AAPL", "value": 100_000, "cost_basis": 20_000, "gain_term": "long"},
                {"ticker": "BND", "value": 100_000, "cost_basis": 100_000, "gain_term": "long"},
            ],
            "target_allocation": {"AAPL": 0.1, "BND": 0.9},
            "tax_budget": {"max_tax": 1_500, "long_term_rate": 0.15, "short_term_rate": 0.35},
        },
        "maya",
    )

    assert "_diagnostics" not in result
    assert result["budget_limited"] is True
    assert result["estimated_tax"]["total"] <= 1_500.01
    assert result["realized_gains"]["long_term"] <= 10_000.01
