from __future__ import annotations

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.core.tool_defs import TOOL_DEFINITIONS
from allworth_api.core.tool_runner import run_tool
from allworth_api.data.seed import performance_cash_flows_for
from allworth_api.financial_tools.data import get_default_rebalance_holdings
from allworth_api.financial_tools.performance import (
    modified_dietz_return,
    period_performance_from_values,
)
from allworth_api.financial_tools.compute import rebalance
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


def test_modified_dietz_adjusts_ending_for_outflows_and_beginning_for_inflows() -> None:
    result = modified_dietz_return(
        beginning_value=100_000,
        ending_value=111_000,
        cash_flows=[
            {"amount": 10_000, "date": "2026-01-16"},
            {"amount": -5_000, "date": "2026-01-22"},
        ],
        start_date="2026-01-01",
        end_date="2026-01-31",
    )

    assert result["method"] == "modified_dietz"
    assert result["inflow"] == 10_000
    assert result["outflow"] == 5_000
    assert result["net_cash_flow"] == 5_000
    assert result["adjusted_beginning_value"] == 110_000
    assert result["adjusted_ending_value"] == 106_000
    assert result["gain_loss"] == -4_000
    assert result["return"] == round((106_000 / 110_000) - 1, 6)
    assert result["ratio"] == round(106_000 / 110_000, 6)
    assert result["return_pct"] == -3.64
    assert result["calculation"]["formula"] == "(ending_value - outflow) / (beginning_value + inflow)"


def test_mock_performance_cash_flows_are_generated_from_seed_files() -> None:
    flows = performance_cash_flows_for()

    assert len(flows) == 12
    assert all("date" in flow and "amount" in flow for flow in flows)
    assert all(flow["amount"] < 0 for flow in flows)
    assert any(flow["source"] == "seed.transactions.transfer" for flow in flows)
    assert any(flow["source"] == "seed.plan.portfolioIncomeMonthly" for flow in flows)


def test_period_performance_from_values_uses_modified_dietz() -> None:
    result = period_performance_from_values(
        [{"month": "2026-01", "value": 100_000}, {"month": "2026-02", "value": 103_000}]
    )

    assert result is not None
    assert result["method"] == "modified_dietz"
    assert result["return_pct"] == 3.0


def test_rebalancer_defaults_to_mock_synapse_model_tables() -> None:
    result = client.post("/tools/rebalance", json={"model_id": "AWF - Core-Satellite - 60/40"}).json()

    assert result["model"]["source_table"] == "tho.model_list"
    assert result["allocation_source_table"] == "tho.Asset_Allocation_Security_Weights"
    assert result["model"]["model_set"] == "Core-Satellite"
    assert result["model"]["model_id"] == "AWF - Core-Satellite - 60/40"
    assert result["model"]["model_version"] == "mock-core-satellite-2026-06"
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
        "tax_calculation",
        "residual_drift",
        "budget_limited",
        "model",
        "allocation_source_table",
    }


def test_seed_contains_only_core_satellite_models_for_rebalancer() -> None:
    from allworth_api.data.seed import seed

    model_rows = seed["allocationModels"]["modelList"]
    weight_rows = seed["allocationModels"]["securityWeights"]
    model_names = {row["allocation_model_name"] for row in model_rows}

    assert len(model_rows) == 66
    assert len(weight_rows) == 1350
    assert {row["model_set"] for row in model_rows} == {"Core-Satellite"}
    assert {row["allocation_model_name"] for row in weight_rows} <= model_names
    assert "AWF - Core-Satellite - 60/40" in model_names
    assert "AWF - Core-Satellite Plus TE CA - 60/40" in model_names


def test_seed_positions_include_average_basis_and_term_gain_scenarios() -> None:
    from allworth_api.data.seed import seed

    assert "taxLots" not in seed

    gain_terms = set()
    loss_terms = set()
    for position in seed["positions"]:
        if "costBasis" not in position:
            continue
        assert position["averageCostBasis"] == round(position["costBasis"] / position["qty"], 2)
        assert position["unrealizedGain"] == position["value"] - position["costBasis"]
        assert position["longTermUnrealizedGain"] == (
            position["longTermValue"] - position["longTermCostBasis"]
        )
        assert position["shortTermUnrealizedGain"] == (
            position["shortTermValue"] - position["shortTermCostBasis"]
        )
        if position["longTermUnrealizedGain"] > 0:
            gain_terms.add("long")
        if position["longTermUnrealizedGain"] < 0:
            loss_terms.add("long")
        if position["shortTermUnrealizedGain"] > 0:
            gain_terms.add("short")
        if position["shortTermUnrealizedGain"] < 0:
            loss_terms.add("short")

    assert gain_terms == {"long", "short"}
    assert loss_terms == {"long", "short"}


def test_default_rebalance_holdings_are_rolled_up_without_lots() -> None:
    holdings = get_default_rebalance_holdings("maya")

    tickers = [holding["ticker"] for holding in holdings]
    assert len(tickers) == len(set(tickers))
    assert all("lots" not in holding for holding in holdings)
    vti = next(holding for holding in holdings if holding["ticker"] == "VTI")
    assert vti["value"] == 1_068_195
    assert vti["cost_basis"] > 0
    assert 0 < vti["cost_basis_ratio"] < 1
    assert vti["short_term_value"] > 0
    assert vti["short_term_unrealized_gain"] > 0
    assert vti["long_term_value"] > 0


def test_rebalancer_uses_aggregate_short_and_long_gain_buckets() -> None:
    result = rebalance(
        get_default_rebalance_holdings("maya"),
        {"BND": 1.0},
        tax_budget={"max_tax": 999_999, "long_term_rate": 0.188, "short_term_rate": 0.35},
    )

    assert result["realized_gains"]["long_term"] > 0
    assert result["realized_gains"]["short_term"] > 0
    assert result["estimated_tax"]["long_term"] > 0
    assert result["estimated_tax"]["short_term"] > 0
    assert any(
        bucket["bucket_id"] == "VTI_short_term"
        for bucket in result["tax_calculation"]["buckets"]
    )
    assert all(bucket["source"] == "aggregate" for bucket in result["tax_calculation"]["buckets"])


def test_rebalancer_can_accept_future_lot_level_extension() -> None:
    result = rebalance(
        [
            {
                "ticker": "AAPL",
                "value": 100_000,
                "tax_lots": [
                    {
                        "id": "future_long_lot",
                        "value": 60_000,
                        "cost_basis": 30_000,
                        "gain_term": "long",
                    },
                    {
                        "id": "future_short_lot",
                        "value": 40_000,
                        "cost_basis": 35_000,
                        "gain_term": "short",
                    },
                ],
            },
            {"ticker": "BND", "value": 100_000, "cost_basis": 100_000, "gain_term": "long"},
        ],
        {"AAPL": 0.0, "BND": 1.0},
        tax_budget={"max_tax": 999_999, "long_term_rate": 0.188, "short_term_rate": 0.35},
    )

    assert result["realized_gains"]["long_term"] > 0
    assert result["realized_gains"]["short_term"] > 0
    assert {
        bucket["bucket_id"] for bucket in result["tax_calculation"]["buckets"]
    } >= {"future_long_lot", "future_short_lot"}
    assert any(bucket["source"] == "lot" for bucket in result["tax_calculation"]["buckets"])


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
    assert result["tax_calculation"]["method"].startswith("For each aggregate tax bucket")
    assert result["tax_calculation"]["buckets"]
    assert result["tax_calculation"]["buckets"][0]["calculation"]["realized_gain"] == (
        "actual_sell_amount * gain_ratio"
    )
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
    bucket_calc = result["tax_calculation"]["buckets"][0]
    assert bucket_calc["tax_rate"] == 0.15
    assert bucket_calc["estimated_tax"] <= 1_500.01
    assert "tax_budget" in bucket_calc["constraints_applied"]
