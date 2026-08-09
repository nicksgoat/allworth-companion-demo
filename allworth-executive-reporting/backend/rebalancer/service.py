"""Synchronous service facade over the vendored rebalancer engine.

Wraps the async DataFetcher (read-only [tho]/[tav] warehouse queries) and the
CVXPY PortfolioOptimizer behind plain functions the Flask routes can call.
Connection settings reuse the planning module's DW_* environment variables.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import polars as pl

from rebalancer.engine.data_fetcher import DataFetcher
from rebalancer.engine.optimizer import PortfolioOptimizer
from rebalancer.engine.portfolio_processor import build_wash_sale_proxy_substitutions

logger = logging.getLogger(__name__)

# CVXPY releases the GIL during solves; a small shared pool bounds concurrent
# optimizations and lets us enforce a hard timeout per run.
_OPTIMIZE_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="rebalancer")
OPTIMIZE_TIMEOUT_SECONDS = 120

MINIMUM_ACCOUNT_VALUE = 2000.0


def _connection_string() -> str:
    """Build the ODBC connection string from the app's DW_* env vars."""
    server = os.environ.get("DW_SERVER", "")
    database = os.environ.get("DW_DATABASE", "")
    username = os.environ.get("DW_USER", "")
    password = os.environ.get("DW_PW", "")
    port = os.environ.get("DW_PORT", "1433")
    return (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER=tcp:{server},{port};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )


def _fetcher() -> DataFetcher:
    return DataFetcher(connection_string=_connection_string())


# ── Account / model lookups ──────────────────────────────────────────────────

def resolve_account(account_number: str) -> dict[str, Any]:
    """Resolve an account number to its upload id + rebalance metadata."""
    fetcher = _fetcher()
    (upload_id, current_strategy, total_account_value, cash_reserve,
     custodian, account_email, owner_id, is_taxable) = asyncio.run(
        fetcher.get_upload_account_id(account_number)
    )
    return {
        "account_number": account_number,
        "upload_account_id": upload_id,
        "current_strategy": current_strategy,
        "total_account_value": total_account_value,
        "cash_reserve": cash_reserve,
        "custodian": custodian,
        "is_taxable": bool(is_taxable) if is_taxable is not None else None,
        "below_minimum": (
            total_account_value is not None
            and float(total_account_value) < MINIMUM_ACCOUNT_VALUE
        ),
    }


def list_models() -> dict[str, Any]:
    """Available target models ([tho].[Model_List]).

    Returns {"model_names": [...], "allocations_by_model": {model: [allocations]}}.
    """
    fetcher = _fetcher()
    return asyncio.run(fetcher.get_target_allocations())


def resolve_target_name(model: str, allocation: str) -> str | None:
    """Full [Allocation Model Name] for a model + equity/fixed split."""
    fetcher = _fetcher()
    return asyncio.run(fetcher.get_target_name(model, allocation))


def get_model_details(model_name: str) -> dict[str, Any]:
    """Securities + asset-class breakdown for a target model."""
    fetcher = _fetcher()
    return asyncio.run(fetcher.get_target_allocation_details(model_name))


def get_portfolio(upload_account_id: str) -> list[dict[str, Any]]:
    """Current lot-level holdings (sweep cash rolled up to CASH)."""
    fetcher = _fetcher()
    df = asyncio.run(fetcher.get_portfolio_from_db(upload_account_id))
    return df.to_dicts() if df is not None and not df.is_empty() else []


# ── Synthetic tax lots ───────────────────────────────────────────────────────
#
# ProposalGen's production flow pulls true tax lots from the Tamarac API. We
# only have position-level warehouse data, but [tho].[Account_Daily_Holdings]
# carries the short/long-term unrealized gain split per position — enough to
# synthesize up to two lots per position whose realized-gain characteristics
# exactly match the warehouse totals. This is an approximation (documented in
# every response as lot_source="synthetic_st_lt_split") and is acceptable for
# a mock rebalancer that never submits trades.

_ST_LOT_AGE_DAYS = 180   # < 1 year → short-term treatment
_LT_LOT_AGE_DAYS = 500   # > 1 year → long-term treatment


async def _fetch_position_frame(upload_account_id: str) -> pl.DataFrame:
    """Position-level holdings including the ST/LT unrealized gain split."""
    from rebalancer.engine.data_fetcher import _roll_up_sweep_cash_holdings

    account_key = int(upload_account_id)  # bigint in the warehouse; also blocks injection
    query = f"""
        SELECT
            [Symbol] AS [Symbol],
            CAST([Quantity] AS FLOAT) AS [Quantity],
            CAST([Total_Account_Value] AS FLOAT) AS [Market Value],
            CAST([Cost_Basis] AS FLOAT) AS [Cost Basis],
            CAST([Current_Price] AS FLOAT) AS [Current Price],
            CAST(ISNULL([Short_Term_Unrealized_Gain_Loss], 0) AS FLOAT) AS [ST Gain],
            CAST(ISNULL([Long_Term_Unrealized_Gain_Loss], 0) AS FLOAT) AS [LT Gain],
            [Security_Type] AS [Security Type],
            [Asset_Class] AS [Asset Class],
            [Subsector] AS [Subsector],
            [Restriction_Type] AS [Restriction Type],
            [Wash_Sale] AS [Wash Sale Blocked]
        FROM [tho].[Account_Daily_Holdings]
        WHERE [avaccountuploadid] = '{account_key}' AND [Total_Account_Value] > 0
        ORDER BY [Symbol]
    """
    fetcher = _fetcher()
    df = await fetcher.sql_query(query)
    return _roll_up_sweep_cash_holdings(df)


def _synthesize_lots(positions: pl.DataFrame) -> pl.DataFrame:
    """Split each position into ST/LT lots matching the warehouse gain split."""
    from datetime import date, timedelta

    today = date.today()
    st_date = today - timedelta(days=_ST_LOT_AGE_DAYS)
    lt_date = today - timedelta(days=_LT_LOT_AGE_DAYS)

    rows: list[dict[str, Any]] = []
    for pos in positions.iter_rows(named=True):
        symbol = pos["Symbol"]
        quantity = float(pos.get("Quantity") or 0.0)
        cost = float(pos.get("Cost Basis") or 0.0)
        value = float(pos.get("Market Value") or 0.0)
        st_gain = float(pos.get("ST Gain") or 0.0)
        lt_gain = float(pos.get("LT Gain") or 0.0)
        if quantity <= 0:
            continue

        base = {
            "Symbol": symbol,
            "Wash Sale Blocked": pos.get("Wash Sale Blocked") or "No",
            "Asset Class": pos.get("Asset Class"),
            "Subsector": pos.get("Subsector"),
            "Security Type": pos.get("Security Type"),
            "Restriction Type": pos.get("Restriction Type"),
        }

        if symbol == "CASH":
            rows.append({**base, "Lot Quantity": quantity, "Lot Cost Basis": cost or quantity,
                         "Date": today})
            continue

        total_abs = abs(st_gain) + abs(lt_gain)
        if total_abs < 1e-9:
            # No gain information — treat the whole position as one long-term lot.
            rows.append({**base, "Lot Quantity": quantity, "Lot Cost Basis": cost, "Date": lt_date})
            continue

        st_fraction = abs(st_gain) / total_abs
        st_qty = quantity * st_fraction
        lt_qty = quantity - st_qty
        st_value = value * st_fraction
        lt_value = value - st_value
        # Cost per lot chosen so each lot's unrealized gain equals the warehouse split.
        if st_qty > 1e-9:
            rows.append({**base, "Lot Quantity": st_qty,
                         "Lot Cost Basis": st_value - st_gain, "Date": st_date})
        if lt_qty > 1e-9:
            rows.append({**base, "Lot Quantity": lt_qty,
                         "Lot Cost Basis": lt_value - lt_gain, "Date": lt_date})

    return pl.DataFrame(rows)


def get_lot_portfolio(upload_account_id: str) -> pl.DataFrame:
    positions = asyncio.run(_fetch_position_frame(upload_account_id))
    if positions is None or positions.is_empty():
        return pl.DataFrame()
    return _synthesize_lots(positions)


# ── Optimization ─────────────────────────────────────────────────────────────

async def _fetch_optimization_data(upload_account_id: str, target_allocation: str):
    """Fetch positions, target weights, security info, and wash-sale subs in parallel."""
    fetcher = _fetcher()
    return await asyncio.gather(
        _fetch_position_frame(upload_account_id),
        fetcher.get_target_allocation(target_allocation),
        fetcher.get_additional_security_info(upload_account_id, target_allocation),
        fetcher.get_substitute_security_wash_sale(upload_account_id, target_allocation),
    )


def _build_restriction_type_map(portfolio_df: pl.DataFrame) -> dict[str, list[str]]:
    """Derive symbol lists by restriction type from the portfolio data."""
    if "Restriction Type" not in portfolio_df.columns or "Symbol" not in portfolio_df.columns:
        return {}
    restriction_map: dict[str, list[str]] = {}
    for symbol, restriction_type in portfolio_df.select(["Symbol", "Restriction Type"]).iter_rows():
        restriction = str(restriction_type or "").strip()
        if not restriction:
            continue
        restriction_map.setdefault(restriction, [])
        if symbol not in restriction_map[restriction]:
            restriction_map[restriction].append(symbol)
    return restriction_map


def run_optimization(params: dict[str, Any]) -> dict[str, Any]:
    """Run a mock rebalance. Mirrors ProposalGen's /api/optimize contract.

    Required params: upload_account_id, target_allocation,
    short_term_tax_rate, long_term_tax_rate.
    Optional: tax_budget, realized_gains_limit, cash_reserve, carve_out,
    enable_wash_sale (default True), use_legacy_positions (default False),
    constraint_type ('none' | 'tax_budget' | 'realized_gains').
    """
    upload_account_id = str(params["upload_account_id"])
    target_allocation = str(params["target_allocation"])

    positions_df, target_df, security_info, wash_sale_substitute_rows = asyncio.run(
        _fetch_optimization_data(upload_account_id, target_allocation)
    )
    if positions_df is None or positions_df.is_empty():
        raise ValueError(f"No holdings found for account {upload_account_id}")
    if target_df is None or target_df.is_empty():
        raise ValueError(f"No target weights found for model '{target_allocation}'")

    portfolio_df = _synthesize_lots(positions_df)

    # Category comes from security info (matches upstream's category_lookup).
    if security_info is not None and not security_info.is_empty():
        category_map = {
            row["Symbol"]: row.get("Category") or ""
            for row in security_info.iter_rows(named=True)
            if row.get("Symbol")
        }
        portfolio_df = portfolio_df.with_columns(
            pl.col("Symbol").map_elements(
                lambda s: category_map.get(s, ""), return_dtype=pl.Utf8
            ).alias("Category")
        )

    restriction_type_securities = (
        params.get("restriction_type_securities") or _build_restriction_type_map(portfolio_df)
    )
    excluded_securities = params.get("excluded_securities")
    if excluded_securities is None:
        excluded_securities = list(restriction_type_securities.get("Unmanaged", []))

    tax_budget = params.get("tax_budget")
    realized_gains_limit = params.get("realized_gains_limit")
    constraint_type = params.get("constraint_type")
    if not constraint_type:
        if tax_budget is not None:
            constraint_type = "tax_budget"
        elif realized_gains_limit is not None:
            constraint_type = "realized_gains"
        else:
            constraint_type = "none"

    enable_wash_sale = bool(params.get("enable_wash_sale", True))
    wash_sale_symbols = (
        portfolio_df.filter(pl.col("Wash Sale Blocked") == "Yes")["Symbol"].to_list()
        if "Wash Sale Blocked" in portfolio_df.columns
        else []
    )

    cash_rows = portfolio_df.filter(pl.col("Symbol") == "CASH")
    total_cash = float(cash_rows["Lot Quantity"].sum()) if not cash_rows.is_empty() else 0.0

    optimizer = PortfolioOptimizer(
        portfolio=portfolio_df,
        target_allocation=target_df,
        portfolio_info=security_info,
        total_cash=total_cash,
        carve_out=float(params.get("carve_out") or 0),
        cash_reserve=float(params.get("cash_reserve") or 0),
    )
    optimizer._wash_sale_proxy_substitutions = build_wash_sale_proxy_substitutions(
        {
            **params,
            "restriction_type_securities": restriction_type_securities,
            "enable_wash_sale": enable_wash_sale,
        },
        wash_sale_substitute_rows,
        excluded_securities,
        wash_sale_symbols,
    )

    future = _OPTIMIZE_EXECUTOR.submit(
        optimizer.optimize_portfolio,
        short_term_rate=float(params["short_term_tax_rate"]),
        long_term_rate=float(params["long_term_tax_rate"]),
        max_tax_bill=float(tax_budget) if tax_budget is not None else 1e12,
        realized_gains_constraint=(
            float(realized_gains_limit) if realized_gains_limit is not None else None
        ),
        legacy_mode=bool(params.get("use_legacy_positions", False)),
        wash_sale=enable_wash_sale,
        exclude_securities=excluded_securities,
        trade_restrictions=restriction_type_securities,
        constraint_type=constraint_type,
    )
    (optimized_portfolio, max_tax_bill_out, total_tax, realized_gains_short_val,
     realized_gains_long_val, total_realize_gain, tracking_error, adjusted_allocation) = (
        future.result(timeout=OPTIMIZE_TIMEOUT_SECONDS)
    )

    return {
        "upload_account_id": upload_account_id,
        "target_allocation": target_allocation,
        "constraint_type": constraint_type,
        "lot_source": "synthetic_st_lt_split",
        "optimized_portfolio": optimized_portfolio.to_dicts(),
        "max_tax_bill": max_tax_bill_out,
        "total_tax": total_tax,
        "realized_gains_short": realized_gains_short_val,
        "realized_gains_long": realized_gains_long_val,
        "total_realized_gains": total_realize_gain,
        "tracking_error": tracking_error,
        "adjusted_allocation": (
            adjusted_allocation.to_dicts() if adjusted_allocation is not None else []
        ),
    }
