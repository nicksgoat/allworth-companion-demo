"""Versioned capital-market assumptions used by stochastic planning.

This module is pure: it validates packaged assumptions and builds correlation
matrices without importing database or web dependencies. Warehouse adapters may
overlay governed observations such as current Allworth volatility.
"""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

D = Decimal
DEFAULT_CMA_TABLE = "2026.1"


def _decimalize(value: Any) -> Any:
    if isinstance(value, dict): return {key: _decimalize(item) for key, item in value.items()}
    if isinstance(value, list): return [_decimalize(item) for item in value]
    if isinstance(value, (int, float)): return D(str(value))
    return value


def load_capital_market_assumptions(version: str = DEFAULT_CMA_TABLE) -> dict[str, Any]:
    path = Path(__file__).with_name("cma_tables") / f"{version}.json"
    if not path.is_file(): raise ValueError(f"unsupported CMA table: {version}")
    table = _decimalize(json.loads(path.read_text(encoding="utf-8")))
    classes = table.get("asset_classes", {})
    if not classes or "Unclassified" not in classes:
        raise ValueError("CMA table requires asset classes and an Unclassified fallback")
    for name, values in classes.items():
        expected, volatility = values.get("expected_return"), values.get("std_dev")
        if expected is None or not D("-1") < expected < D("1"):
            raise ValueError(f"invalid expected return for {name}")
        if volatility is None or not D("0") <= volatility < D("2"):
            raise ValueError(f"invalid volatility for {name}")
        if not values.get("bucket"): raise ValueError(f"missing correlation bucket for {name}")
    for alias, target in table.get("aliases", {}).items():
        if not alias or target not in classes: raise ValueError(f"invalid CMA alias: {alias}")
    return deepcopy(table)


def match_asset_class(name: str | None, table: dict[str, Any]) -> str | None:
    cleaned = str(name or "").strip()
    if not cleaned: return None
    classes = table["asset_classes"]
    if cleaned in classes: return cleaned
    casefolded = {key.casefold(): key for key in classes}
    if cleaned.casefold() in casefolded: return casefolded[cleaned.casefold()]
    return table.get("aliases", {}).get(cleaned.casefold())


def canonical_asset_class(name: str | None, table: dict[str, Any]) -> str:
    return match_asset_class(name, table) or "Unclassified"


def build_correlation_matrix(classes: list[str], table: dict[str, Any]) -> list[list[float]]:
    policy = table["correlations"]
    matrix: list[list[float]] = []
    for left in classes:
        row: list[float] = []
        left_bucket = table["asset_classes"][left]["bucket"]
        for right in classes:
            if left == right:
                value = D("1")
            else:
                right_bucket = table["asset_classes"][right]["bucket"]
                buckets = {left_bucket, right_bucket}
                if left_bucket == right_bucket == "equity": value = policy["same_equity"]
                elif left_bucket == right_bucket == "bond": value = policy["same_bond"]
                elif left_bucket == right_bucket: value = policy["same_other"]
                elif buckets == {"equity", "bond"}: value = policy["equity_bond"]
                else: value = policy["cross_bucket"]
            row.append(float(value))
        matrix.append(row)
    return matrix
