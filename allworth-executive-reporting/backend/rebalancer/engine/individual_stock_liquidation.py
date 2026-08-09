"""
Rules for forced liquidation of off-model individual stock holdings.

This module is intentionally small and data-driven so future changes to the
definition or exclusions for this policy stay out of the optimizer internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

import polars as pl


INDIVIDUAL_STOCK_SUBSECTOR = "Stock"
INDIVIDUAL_STOCK_ASSET_CLASSES = frozenset(
    {
        "Equities",
        "International Equity",
        "U.S. Equity",
    }
)


@dataclass(frozen=True)
class ForcedLiquidationRuleResult:
    """Result of evaluating a forced-liquidation rule against optimizer lots."""

    lot_indices: tuple[int, ...]
    symbols: tuple[str, ...]
    skipped_symbols: tuple[str, ...] = ()


def _normalize_text(value) -> str:
    return str(value or "").strip()


def _normalize_key(value) -> str:
    return _normalize_text(value).upper()


def is_individual_stock_holding(asset_class, subsector) -> bool:
    """Return True when metadata matches the individual-stock policy."""
    return (
        _normalize_text(subsector).casefold() == INDIVIDUAL_STOCK_SUBSECTOR.casefold()
        and _normalize_text(asset_class).casefold()
        in {asset_class.casefold() for asset_class in INDIVIDUAL_STOCK_ASSET_CLASSES}
    )


def find_off_model_individual_stock_lots(
    *,
    symbols: Sequence[str],
    quantities: Sequence[float],
    asset_classes: Sequence[object],
    subsectors: Sequence[object],
    original_target_symbols: Iterable[str],
    excluded_symbols: Iterable[str] = (),
    sell_blocked_symbols: Iterable[str] = (),
) -> ForcedLiquidationRuleResult:
    """
    Identify held individual-stock lots that should be fully sold.

    A position is off-model only when it was absent from the original target
    allocation. Synthetic zero-weight target rows added by the optimizer do not
    count as target-portfolio membership.
    """
    target_set = {_normalize_key(sym) for sym in original_target_symbols if _normalize_text(sym)}
    excluded_set = {_normalize_key(sym) for sym in excluded_symbols if _normalize_text(sym)}
    sell_blocked_set = {_normalize_key(sym) for sym in sell_blocked_symbols if _normalize_text(sym)}

    lot_indices = []
    forced_symbols = set()
    skipped_symbols = set()

    for idx, (symbol, quantity, asset_class, subsector) in enumerate(
        zip(symbols, quantities, asset_classes, subsectors)
    ):
        normalized_symbol = _normalize_text(symbol)
        symbol_key = _normalize_key(symbol)
        if not normalized_symbol or symbol_key == "CASH":
            continue
        if float(quantity or 0.0) <= 1e-9:
            continue
        if symbol_key in target_set:
            continue
        if not is_individual_stock_holding(asset_class, subsector):
            continue

        if symbol_key in excluded_set or symbol_key in sell_blocked_set:
            skipped_symbols.add(normalized_symbol)
            continue

        lot_indices.append(idx)
        forced_symbols.add(normalized_symbol)

    return ForcedLiquidationRuleResult(
        lot_indices=tuple(lot_indices),
        symbols=tuple(sorted(forced_symbols)),
        skipped_symbols=tuple(sorted(skipped_symbols)),
    )


def find_off_category_legacy_lots(
    *,
    symbols: Sequence[str],
    quantities: Sequence[float],
    categories: Sequence[object],
    allowed_categories: Iterable[str],
    substitutions: Sequence[object] | None = None,
    target_symbols: Iterable[str] = (),
    excluded_symbols: Iterable[str] = (),
    sell_blocked_symbols: Iterable[str] = (),
) -> ForcedLiquidationRuleResult:
    """
    Identify held legacy (non-model) lots whose asset category is not one the
    target model allocates to, so they should be fully sold.

    This implements the legacy-bucket rule: a non-model fund or ETF may only be
    held when it belongs to an asset category the model targets. A holding in a
    different asset category (for example a utilities ETF against an equity /
    fixed-income model) is recommended for sale unless the user applies a
    Trading exclusion.

    A lot is force-liquidated only when ALL of the following hold:
    - it has a positive quantity and is not CASH,
    - its symbol is not part of the target allocation,
    - it is not a substitute for a target security,
    - its category is known (not the symbol-fallback sentinel) and NOT in
      ``allowed_categories``,
    - it is not Trading-excluded and not sell-blocked (Hold/Buy).
    """
    allowed = {_normalize_key(cat) for cat in allowed_categories if _normalize_text(cat)}
    target_set = {_normalize_key(sym) for sym in target_symbols if _normalize_text(sym)}
    excluded_set = {_normalize_key(sym) for sym in excluded_symbols if _normalize_text(sym)}
    sell_blocked_set = {_normalize_key(sym) for sym in sell_blocked_symbols if _normalize_text(sym)}
    subs = list(substitutions) if substitutions is not None else [None] * len(symbols)

    lot_indices = []
    forced_symbols = set()
    skipped_symbols = set()

    for idx, (symbol, quantity, category) in enumerate(zip(symbols, quantities, categories)):
        normalized_symbol = _normalize_text(symbol)
        symbol_key = normalized_symbol.upper()
        if not normalized_symbol or symbol_key == "CASH":
            continue
        if float(quantity or 0.0) <= 1e-9:
            continue
        if symbol_key in target_set:
            continue

        # Substitutes proxy a target security by design — never force their sale.
        sub_value = _normalize_text(subs[idx] if idx < len(subs) else None)
        if sub_value and sub_value.upper() != symbol_key:
            continue

        category_text = _normalize_text(category)
        category_key = category_text.upper()
        # An unknown category falls back to the symbol; without a reliable
        # category we cannot say the fund is in a "different" asset category,
        # so we leave the existing behavior untouched.
        if not category_text or category_key == symbol_key:
            continue
        if category_key in allowed:
            continue

        if symbol_key in excluded_set or symbol_key in sell_blocked_set:
            skipped_symbols.add(normalized_symbol)
            continue

        lot_indices.append(idx)
        forced_symbols.add(normalized_symbol)

    return ForcedLiquidationRuleResult(
        lot_indices=tuple(lot_indices),
        symbols=tuple(sorted(forced_symbols)),
        skipped_symbols=tuple(sorted(skipped_symbols)),
    )


def _positive_quantity(row: dict) -> bool:
    for column in ("Lot Quantity", "Shares", "Quantity"):
        if column in row:
            return float(row.get(column) or 0.0) > 1e-9
    return False


def find_off_model_individual_stock_symbols(
    *,
    portfolio: pl.DataFrame,
    target_allocation: pl.DataFrame,
    portfolio_info: pl.DataFrame | None = None,
    excluded_symbols: Iterable[str] = (),
) -> tuple[str, ...]:
    """Return symbols that should be force-liquidated by the individual-stock rule."""
    if portfolio is None or portfolio.is_empty() or "Symbol" not in portfolio.columns:
        return tuple()

    target_symbols = (
        _target_symbols_from_frame(target_allocation)
        if target_allocation is not None
        else set()
    )
    target_symbol_keys = {_normalize_key(symbol) for symbol in target_symbols}
    excluded_set = {_normalize_key(sym) for sym in excluded_symbols if _normalize_text(sym)}
    metadata_by_symbol = _metadata_by_symbol(portfolio_info)
    forced_symbols = set()

    for row in portfolio.iter_rows(named=True):
        symbol = _normalize_text(row.get("Symbol"))
        symbol_key = symbol.upper()
        if not symbol or symbol_key == "CASH" or symbol_key in excluded_set:
            continue
        if not _positive_quantity(row):
            continue
        if symbol_key in target_symbol_keys:
            continue

        metadata = metadata_by_symbol.get(symbol_key, {})
        asset_class = row.get("Asset Class") or metadata.get("Asset Class")
        subsector = row.get("Subsector") or metadata.get("Subsector")
        if is_individual_stock_holding(asset_class, subsector):
            forced_symbols.add(symbol)

    return tuple(sorted(forced_symbols))


def _target_symbols_from_frame(target_allocation: pl.DataFrame) -> set[str]:
    if target_allocation is None or target_allocation.is_empty() or "Symbol" not in target_allocation.columns:
        return set()
    return {
        _normalize_text(symbol)
        for symbol in target_allocation.get_column("Symbol").to_list()
        if _normalize_text(symbol)
    }


def _metadata_by_symbol(frame: pl.DataFrame | None) -> dict[str, dict]:
    if frame is None or frame.is_empty() or "Symbol" not in frame.columns:
        return {}

    metadata = {}
    cols = [col for col in ("Symbol", "Asset Class", "Subsector") if col in frame.columns]
    for row in frame.select(cols).iter_rows(named=True):
        symbol_key = _normalize_key(row.get("Symbol"))
        if symbol_key and symbol_key not in metadata:
            metadata[symbol_key] = row
    return metadata
