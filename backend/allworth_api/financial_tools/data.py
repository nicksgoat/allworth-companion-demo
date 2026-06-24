"""Layer 1: data tools.

These functions fetch current state with no simulation logic. In the demo they
read from the deterministic seed store; in production they can be backed by
Synapse or another authenticated data source.
"""

from __future__ import annotations

from typing import Any

from allworth_api.data.seed import DEFAULT_CLIENT, current_seed, seed_for

DEFAULT_MODEL_ID = "AWF - Core-Satellite - 60/40"
DEFAULT_MODEL_VERSION = "mock-core-satellite-2026-06"
MODEL_ALIASES = {
    "growth_income_60_40": DEFAULT_MODEL_ID,
    "core_satellite_60_40": DEFAULT_MODEL_ID,
}


def _current_user_is_demo(user_id: str) -> bool:
    return bool(user_id)


def get_portfolio(user_id: str) -> dict[str, Any]:
    """Fetch current holdings, total value, and allocation breakdown."""
    if not _current_user_is_demo(user_id):
        return {"error": "user_id required"}

    seed = current_seed()
    total_value = sum(p["value"] for p in seed["positions"])
    holdings_by_ticker: dict[str, dict[str, Any]] = {}

    for position in seed["positions"]:
        ticker = position["symbol"]
        entry = holdings_by_ticker.setdefault(
            ticker,
            {"ticker": ticker, "value": 0.0, "asset_class": position.get("assetClass", "other")},
        )
        entry["value"] += float(position["value"])

    holdings = []
    for ticker, entry in sorted(holdings_by_ticker.items()):
        allocation = entry["value"] / total_value if total_value else 0.0
        holdings.append(
            {
                "ticker": ticker,
                "value": round(entry["value"], 2),
                "allocation": round(allocation, 4),
            }
        )

    return {
        "total_value": round(total_value, 2),
        "holdings": holdings,
        "allocation_summary": {h["ticker"]: round(h["allocation"] * 100, 1) for h in holdings},
    }


def get_default_rebalance_holdings(user_id: str, account_id: str | None = None) -> list[dict[str, Any]]:
    """Return rolled-up mock holdings with aggregate gain metadata.

    Production should back this with current holdings plus aggregate cost-basis
    and long/short unrealized gain buckets. The rebalancer does not require
    lot-level data. If lot-level data becomes available later, `compute.rebalance`
    already has an optional adapter that normalizes `tax_lots` into tax buckets.
    The target model metadata mirrors `tho.model_list`, and model weights mirror
    `tho.Asset_Allocation_Security_Weights`.
    """
    if not _current_user_is_demo(user_id):
        return []

    seed = current_seed()
    positions = [
        position
        for position in seed["positions"]
        if position["symbol"] != "CASH"
        and (account_id is None or position.get("accountId") == account_id)
    ]
    holdings_by_ticker: dict[str, dict[str, Any]] = {}
    for position in positions:
        ticker = position["symbol"]
        holding = holdings_by_ticker.setdefault(
            ticker,
            {
                "ticker": ticker,
                "value": 0.0,
                "cost_basis": 0.0,
                "cost_basis_ratio": 0.0,
                "long_term_value": 0.0,
                "long_term_cost_basis": 0.0,
                "long_term_unrealized_gain": 0.0,
                "short_term_value": 0.0,
                "short_term_cost_basis": 0.0,
                "short_term_unrealized_gain": 0.0,
            },
        )
        holding["value"] += float(position["value"])
        cost_basis = position.get("costBasis")
        if cost_basis is not None:
            holding["cost_basis"] += float(cost_basis)
            holding["long_term_value"] += float(position.get("longTermValue", 0) or 0)
            holding["long_term_cost_basis"] += float(position.get("longTermCostBasis", 0) or 0)
            holding["long_term_unrealized_gain"] += float(
                position.get("longTermUnrealizedGain", 0) or 0
            )
            holding["short_term_value"] += float(position.get("shortTermValue", 0) or 0)
            holding["short_term_cost_basis"] += float(position.get("shortTermCostBasis", 0) or 0)
            holding["short_term_unrealized_gain"] += float(
                position.get("shortTermUnrealizedGain", 0) or 0
            )
            continue
        holding["cost_basis"] += float(position["value"])
        holding["long_term_value"] += float(position["value"])
        holding["long_term_cost_basis"] += float(position["value"])

    for holding in holdings_by_ticker.values():
        if holding["value"]:
            holding["cost_basis_ratio"] = holding["cost_basis"] / holding["value"]

    return [
        {key: round(value, 2) if isinstance(value, float) else value for key, value in holding.items()}
        for holding in sorted(holdings_by_ticker.values(), key=lambda h: h["ticker"])
    ]


def get_model_allocation(model_id: str) -> dict[str, Any]:
    """Return a mock model allocation shaped after Synapse model tables."""
    # House models are shared across clients; fall back to the default seed so
    # a leaner per-client seed doesn't need to duplicate them.
    allocation_models = current_seed().get("allocationModels") or seed_for(DEFAULT_CLIENT).get(
        "allocationModels", {}
    )
    source_tables = allocation_models.get("sourceTables", {})
    resolved_model_id = MODEL_ALIASES.get(model_id, model_id)
    model_rows = allocation_models.get("modelList", [])
    weight_rows = allocation_models.get("securityWeights", [])
    model = next(
        (row for row in model_rows if row["allocation_model_name"] == resolved_model_id),
        None,
    )
    if not model:
        return {
            "error": f"Model '{model_id}' not found",
            "available_models": [row["allocation_model_name"] for row in model_rows],
        }
    matching_weights = [
        row for row in weight_rows if row["allocation_model_name"] == resolved_model_id
    ]
    target_allocation = {row["ticker"]: float(row["weight"]) for row in matching_weights}
    return {
        "model": {
            "model_id": model["allocation_model_name"],
            "model_name": model["model_name"],
            "model_set": model["model_set"],
            "model_type": model["model_type"],
            "portfolio_allocation": model["portfolio_allocation"],
            "allocation": model["allocation"],
            "model_version": model.get("model_version", DEFAULT_MODEL_VERSION),
            "source_table": source_tables.get("modelList", "tho.model_list"),
        },
        "target_allocation": target_allocation,
        "allocation_source_table": source_tables.get(
            "securityWeights", "tho.Asset_Allocation_Security_Weights"
        ),
    }
