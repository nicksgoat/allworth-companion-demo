"""Layer 1: data tools.

These functions fetch current state with no simulation logic. In the demo they
read from the deterministic seed store; in production they can be backed by
Synapse or another authenticated data source.
"""

from __future__ import annotations

from typing import Any

from allworth_api.data.seed import seed

DEFAULT_MODEL_ID = "AWF - Core-Satellite - 60/40"
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
    """Return mock taxable holdings with lot-level gain metadata for rebalancing.

    Production should back this with current holdings plus lot/cost-basis data.
    The target model metadata mirrors `tho.model_list`, and model weights mirror
    `tho.Asset_Allocation_Security_Weights`.
    """
    if not _current_user_is_demo(user_id):
        return []

    positions = [
        position
        for position in seed["positions"]
        if position["symbol"] != "CASH"
        and (account_id is None or position.get("accountId") == account_id)
    ]
    lots_by_position: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for lot in seed["taxLots"]:
        if account_id is not None and lot.get("accountId") != account_id:
            continue
        lots_by_position.setdefault((lot["accountId"], lot["symbol"]), []).append(lot)

    holdings = []
    for position in positions:
        lots = lots_by_position.get((position["accountId"], position["symbol"]), [])
        if lots:
            holdings.append(
                {
                    "ticker": position["symbol"],
                    "account_id": position["accountId"],
                    "value": float(position["value"]),
                    "lots": [
                        {
                            "lot_id": lot["id"],
                            "value": round(float(lot["qty"]) * float(position["price"]), 2),
                            "cost_basis": round(float(lot["qty"]) * float(lot["costPerShare"]), 2),
                            "gain_term": lot.get("term", "long"),
                        }
                        for lot in lots
                    ],
                }
            )
            continue
        holdings.append(
            {
                "ticker": position["symbol"],
                "account_id": position["accountId"],
                "value": float(position["value"]),
                "cost_basis": float(position["value"]),
                "gain_term": "long",
            }
        )
    return holdings


def get_model_allocation(model_id: str) -> dict[str, Any]:
    """Return a mock model allocation shaped after Synapse model tables."""
    allocation_models = seed.get("allocationModels", {})
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
            "source_table": source_tables.get("modelList", "tho.model_list"),
        },
        "target_allocation": target_allocation,
        "allocation_source_table": source_tables.get(
            "securityWeights", "tho.Asset_Allocation_Security_Weights"
        ),
    }
