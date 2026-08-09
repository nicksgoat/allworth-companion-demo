"""Shared target allocation normalization helpers."""

from __future__ import annotations

import logging
from typing import Any, Iterable, Mapping, Optional, Tuple

import polars as pl

logger = logging.getLogger(__name__)


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_effective_target_allocation_with_cash(
    target_allocation: pl.DataFrame,
    budget_value: float,
    cash_reserve: Optional[float] = None,
    carve_out: float = 0.0,
    minimum_cash_percent: float = 0.02,
) -> Tuple[pl.DataFrame, float]:
    """
    Calculate target allocation adjusted for cash reserves and carve-outs.

    The returned DataFrame has decimal weights and includes an explicit CASH row.
    Non-cash targets are shrunk proportionally to preserve the requested cash
    floor.
    """
    budget_value = _coerce_float(budget_value)
    base = target_allocation.select([
        pl.col("Symbol").cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias("Symbol"),
        pl.col("Target Weight"),
    ])

    non_cash = base.filter(pl.col("Symbol") != "CASH")
    non_cash_weight_sum = float(non_cash["Target Weight"].sum()) or 1.0

    if budget_value > 0:
        requested_reserve = _coerce_float(cash_reserve)

        if requested_reserve > 0:
            reserve = max(0.0, requested_reserve)
            max_reasonable_reserve = 0.20 * budget_value
            if reserve > max_reasonable_reserve:
                logger.warning(
                    f"Cash reserve ${reserve:,.2f} ({reserve / budget_value:.1%} of portfolio) "
                    f"exceeds 20% cap. Capping at ${max_reasonable_reserve:,.2f}. "
                    f"Check [Total Cash Reserve Goal Dollar] in DB."
                )
                reserve = max_reasonable_reserve
        else:
            reserve = minimum_cash_percent * budget_value

        carve = max(0.0, _coerce_float(carve_out))
        cash_floor_dollars = min(budget_value, reserve + carve)
        cash_weight = cash_floor_dollars / budget_value
    else:
        cash_floor_dollars = 0.0
        cash_weight = 0.0

    alpha = (1.0 - cash_weight) / non_cash_weight_sum if non_cash_weight_sum > 1e-12 else 0.0

    eff_rows = [
        (symbol, float(weight) * alpha)
        for symbol, weight in non_cash.iter_rows()
    ]
    eff = pl.DataFrame(eff_rows, schema=["Symbol", "Target Weight"], orient="row")

    non_cash_sum = float(eff["Target Weight"].sum()) or 1.0
    target_non_cash_sum = 1.0 - cash_weight
    if non_cash_sum > 0 and abs(non_cash_sum - target_non_cash_sum) > 0.0001:
        logger.info(
            f"Adjusting non-cash weights: sum={non_cash_sum:.6f}, "
            f"target={target_non_cash_sum:.6f}"
        )
        eff = eff.with_columns(
            (pl.col("Target Weight") * target_non_cash_sum / non_cash_sum).alias("Target Weight")
        )

    cash_row = pl.DataFrame([("CASH", cash_weight)], schema=["Symbol", "Target Weight"], orient="row")
    eff = pl.concat([eff, cash_row], how="vertical")

    final_sum = float(eff["Target Weight"].sum())
    if abs(final_sum - 1.0) > 0.001:
        logger.warning(f"Weight sum after adjustment: {final_sum:.6f} (expected 1.0)")

    return eff, cash_floor_dollars


def normalize_asset_class_weights(weights: Mapping[str, Any] | None) -> dict[str, float]:
    """Canonicalize asset-class names and combine duplicate weights."""
    normalized: dict[str, float] = {}
    for raw_name, raw_weight in (weights or {}).items():
        name = str(raw_name or "").strip()
        if not name:
            continue
        canonical_name = "Cash" if name.lower() == "cash" else name
        try:
            weight = float(raw_weight or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        normalized[canonical_name] = normalized.get(canonical_name, 0.0) + weight
    return normalized


def current_cash_weight_from_portfolio(portfolio: Iterable[Mapping[str, Any]] | None) -> float:
    """Return current portfolio cash weight as a percent."""
    total_value = 0.0
    cash_value = 0.0

    for holding in portfolio or []:
        try:
            market_value = float(holding.get("Market Value") or holding.get("market_value") or 0.0)
        except (TypeError, ValueError):
            market_value = 0.0
        total_value += market_value

        symbol = str(holding.get("Symbol") or holding.get("symbol") or "").strip().upper()
        asset_class = str(holding.get("Asset Class") or holding.get("asset_class") or "").strip().lower()
        security_type = str(holding.get("Security Type") or holding.get("security_type") or "").strip().lower()
        if symbol == "CASH" or asset_class == "cash" or security_type == "cash":
            cash_value += market_value

    return (cash_value / total_value) * 100.0 if total_value > 0 else 0.0


def normalize_target_data_with_cash(
    target_data: Mapping[str, Any] | None,
    cash_weight_percent: Any,
) -> dict[str, Any] | Mapping[str, Any] | None:
    """Normalize target securities and asset classes so Cash is included once."""
    if not target_data:
        return target_data

    try:
        cash_weight = max(0.0, min(100.0, float(cash_weight_percent or 0.0)))
    except (TypeError, ValueError):
        cash_weight = 0.0

    if cash_weight <= 0:
        return dict(target_data)

    normalized = dict(target_data)
    non_cash_target_total = max(0.0, 100.0 - cash_weight)

    asset_classes = normalize_asset_class_weights(target_data.get("assetClasses") or {})
    non_cash_asset_total = sum(
        weight for name, weight in asset_classes.items() if name != "Cash"
    )
    if non_cash_asset_total > 0:
        asset_classes = {
            name: (
                cash_weight
                if name == "Cash"
                else (weight / non_cash_asset_total) * non_cash_target_total
            )
            for name, weight in asset_classes.items()
        }
    asset_classes["Cash"] = cash_weight
    normalized["assetClasses"] = asset_classes
    normalized["cashWeight"] = cash_weight

    securities = list(target_data.get("securities") or [])
    non_cash_security_total = 0.0
    for security in securities:
        if str(security.get("symbol") or "").strip().upper() == "CASH":
            continue
        try:
            non_cash_security_total += float(security.get("weight") or 0.0)
        except (TypeError, ValueError):
            continue

    adjusted_securities = []
    seen_cash = False
    for security in securities:
        adjusted = dict(security)
        symbol = str(adjusted.get("symbol") or "").strip().upper()
        if symbol == "CASH":
            adjusted.update({
                "symbol": "CASH",
                "name": adjusted.get("name") or "Cash",
                "weight": cash_weight,
                "assetClass": "Cash",
                "category": "Cash",
            })
            seen_cash = True
        elif non_cash_security_total > 0:
            adjusted["weight"] = (
                float(adjusted.get("weight") or 0.0) / non_cash_security_total
            ) * non_cash_target_total
        adjusted_securities.append(adjusted)

    if not seen_cash:
        adjusted_securities.append({
            "symbol": "CASH",
            "name": "Cash",
            "weight": cash_weight,
            "assetClass": "Cash",
            "category": "Cash",
        })

    normalized["securities"] = adjusted_securities
    return normalized
