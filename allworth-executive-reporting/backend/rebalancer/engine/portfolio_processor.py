"""
Portfolio fetching, restriction processing, and exclusion handling.

Extracted from main_routes.py to isolate portfolio data preparation logic
from HTTP route handling.
"""

import asyncio
import logging
import os
import polars as pl

logger = logging.getLogger(__name__)

# Fixed income security types whose prices are quoted per $100 of par
_FI_SECURITY_TYPES = {"T-Bills", "CDs", "Fixed Income", "Mortgage-Backed"}


def model_assignment_debug_enabled() -> bool:
    """Return True when verbose model-assignment diagnostics are explicitly enabled."""
    return os.environ.get("TAX_TOOLS_MODEL_ASSIGNMENT_DEBUG", "").lower() in {"1", "true", "yes", "on"}


def _debug_logging_enabled() -> bool:
    return logger.isEnabledFor(logging.DEBUG) or model_assignment_debug_enabled()


def _rows_from_substitute_source(substitute_rows):
    if substitute_rows is None:
        return []
    if isinstance(substitute_rows, pl.DataFrame):
        if substitute_rows.is_empty():
            return []
        if {"Is Default", "Ranking"}.issubset(set(substitute_rows.columns)):
            substitute_rows = substitute_rows.sort(["Is Default", "Ranking"], descending=[True, False])
        elif "Ranking" in substitute_rows.columns:
            substitute_rows = substitute_rows.sort("Ranking")
        return list(substitute_rows.iter_rows(named=True))
    if isinstance(substitute_rows, dict):
        return [
            {"Ticker": proxy_symbol, "Substitute": blocked_symbol}
            for proxy_symbol, blocked_symbol in substitute_rows.items()
        ]
    return list(substitute_rows or [])


def build_wash_sale_proxy_substitutions(
    tax_data,
    wash_sale_substitute_rows,
    trading_exclusions=None,
    wash_sale_blocked_symbols=None,
):
    """Build {proxy_symbol_to_buy: wash_sale_symbol} from wash-sale substitute rows only."""
    debug_logging = _debug_logging_enabled()
    if debug_logging:
        substitute_preview = (
            wash_sale_substitute_rows.to_dicts()
            if isinstance(wash_sale_substitute_rows, pl.DataFrame) and not wash_sale_substitute_rows.is_empty()
            else wash_sale_substitute_rows or []
        )
        logger.debug(
            "[WASH_SALE_DEBUG] build_proxy_input "
            f"account_number={tax_data.get('account_number')!r} "
            f"enabled={tax_data.get('enable_wash_sale', True)} "
            f"wash_sale_substitute_rows={substitute_preview} "
            f"trading_exclusions={trading_exclusions or []} "
            f"restriction_type_securities={tax_data.get('restriction_type_securities', {}) or {}} "
            f"wash_sale_blocked_symbols={wash_sale_blocked_symbols or []}"
        )
    if not tax_data.get('enable_wash_sale', True):
        logger.debug("[WASH_SALE_DEBUG] build_proxy_result reason=wash_sale_disabled proxy_map={}")
        return {}

    restriction_type_securities = tax_data.get('restriction_type_securities', {}) or {}
    wash_sale_symbols = {
        str(symbol or '').strip().upper()
        for symbol in (restriction_type_securities.get('Wash Sale', []) or [])
        if str(symbol or '').strip()
    }
    wash_sale_symbols.update({
        str(symbol or '').strip().upper()
        for symbol in (wash_sale_blocked_symbols or [])
        if str(symbol or '').strip()
    })
    excluded_symbols = {
        str(symbol or '').strip().upper()
        for symbol in (trading_exclusions or [])
        if str(symbol or '').strip()
    }
    blocked_symbols = {
        str(symbol or '').strip().upper()
        for symbol in (wash_sale_blocked_symbols or [])
        if str(symbol or '').strip()
    }
    blocked_symbols.update(wash_sale_symbols)
    if not wash_sale_symbols:
        logger.debug(
            "[WASH_SALE_DEBUG] build_proxy_result "
            f"reason=missing_wash_sale_symbols wash_sale_symbols={sorted(wash_sale_symbols)} "
            f"excluded_symbols={sorted(excluded_symbols)} proxy_map={{}}"
        )
        return {}

    proxy_map = {}
    mapped_targets = set()
    skipped_rows = [] if debug_logging else None
    for row in _rows_from_substitute_source(wash_sale_substitute_rows):
        if not isinstance(row, dict):
            continue
        ticker = str(
            row.get("Ticker") or row.get("Symbol") or row.get("Target Symbol") or ""
        ).strip().upper()
        substitute = str(
            row.get("Substitute") or row.get("Substitute Symbol") or row.get("Proxy Symbol") or ""
        ).strip().upper()
        if not ticker or not substitute or ticker == substitute:
            if skipped_rows is not None:
                skipped_rows.append({**row, "_reason": "missing_or_same_symbol"})
            continue

        ticker_blocked = ticker in blocked_symbols or str(
            row.get("Ticker Wash Sale Blocked")
            or row.get("Target Wash Sale Blocked")
            or ""
        ).strip().lower() == "yes"
        substitute_blocked = substitute in blocked_symbols or str(
            row.get("Substitute Wash Sale Blocked")
            or row.get("Proxy Wash Sale Blocked")
            or ""
        ).strip().lower() == "yes"

        if ticker_blocked and substitute_blocked:
            if skipped_rows is not None:
                skipped_rows.append({**row, "_reason": "both_symbols_wash_sale_blocked"})
            continue
        if substitute in wash_sale_symbols and not ticker_blocked:
            if substitute not in mapped_targets:
                proxy_map[ticker] = substitute
                mapped_targets.add(substitute)
            continue
        if ticker in wash_sale_symbols and not substitute_blocked:
            if ticker not in mapped_targets:
                proxy_map[substitute] = ticker
                mapped_targets.add(ticker)
            continue
        if skipped_rows is not None:
            skipped_rows.append({**row, "_reason": "row_does_not_match_wash_sale_symbol"})
    if debug_logging:
        logger.debug(
            "[WASH_SALE_DEBUG] build_proxy_result "
            f"wash_sale_symbols={sorted(wash_sale_symbols)} "
            f"excluded_symbols={sorted(excluded_symbols)} "
            f"blocked_symbols={sorted(blocked_symbols)} "
            f"proxy_map={proxy_map} "
            f"skipped_rows={skipped_rows}"
        )
    return proxy_map


def build_substitute_options_by_symbol(substitute_rows):
    """Build {held_symbol: [target_symbols]} from substitute query rows."""
    if substitute_rows is None:
        return {}
    if isinstance(substitute_rows, pl.DataFrame):
        if substitute_rows.is_empty():
            return {}
        if {"Is Default", "Ranking"}.issubset(set(substitute_rows.columns)):
            substitute_rows = substitute_rows.sort(["Is Default", "Ranking"], descending=[True, False])
        elif "Ranking" in substitute_rows.columns:
            substitute_rows = substitute_rows.sort("Ranking")
        rows = substitute_rows.iter_rows(named=True)
    elif isinstance(substitute_rows, dict):
        rows = (
            {"Substitute Symbol": held_symbol, "Symbol": target_symbol}
            for held_symbol, target_symbol in substitute_rows.items()
        )
    else:
        rows = substitute_rows

    options_by_symbol = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        held_symbol = str(
            row.get("Substitute Symbol") or row.get("Substitute") or ""
        ).strip().upper()
        target_symbol = str(
            row.get("Symbol") or row.get("Ticker") or ""
        ).strip().upper()
        if not held_symbol or not target_symbol or held_symbol == target_symbol:
            continue
        options = options_by_symbol.setdefault(held_symbol, [])
        if target_symbol not in options:
            options.append(target_symbol)
    return options_by_symbol


def build_default_substitutes_by_symbol(substitute_rows):
    """Build {held_symbol: target_symbol} for Security_Substitutes default rows."""
    if substitute_rows is None:
        return {}
    if isinstance(substitute_rows, pl.DataFrame):
        if substitute_rows.is_empty():
            return {}
        if {"Is Default", "Ranking"}.issubset(set(substitute_rows.columns)):
            substitute_rows = substitute_rows.sort(["Is Default", "Ranking"], descending=[True, False])
        elif "Ranking" in substitute_rows.columns:
            substitute_rows = substitute_rows.sort("Ranking")
        rows = substitute_rows.iter_rows(named=True)
    elif isinstance(substitute_rows, dict):
        rows = (
            {"Substitute Symbol": held_symbol, "Symbol": target_symbol, "Ranking": 1}
            for held_symbol, target_symbol in substitute_rows.items()
        )
    else:
        rows = substitute_rows

    default_substitutes = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            is_default = int(row.get("Is Default", 1 if int(row.get("Ranking", 1)) == 1 else 0))
        except (TypeError, ValueError):
            is_default = 0
        if is_default != 1:
            continue
        held_symbol = str(
            row.get("Substitute Symbol") or row.get("Substitute") or ""
        ).strip().upper()
        target_symbol = str(
            row.get("Symbol") or row.get("Ticker") or ""
        ).strip().upper()
        if not held_symbol or not target_symbol or held_symbol == target_symbol:
            continue
        default_substitutes.setdefault(held_symbol, target_symbol)
    return default_substitutes


def fetch_and_process_portfolio(tax_data, account_number, data_fetcher):
    """Fetch portfolio data and process restriction types.

    Uses asyncio.gather() to fetch portfolio and security info in parallel.

    Returns:
        tuple: (portfolio_list, restriction_type_securities)
    """
    target_allocation = tax_data.get('target_allocation', '')

    async def _fetch_parallel():
        upload_account_id, current_strategy, total_account_value, cash_reserve, custodian, account_email, owner_id, _ = \
            await data_fetcher.get_upload_account_id(account_number)

        portfolio_df = await data_fetcher.get_portfolio_from_db(upload_account_id)
        portfolio_symbol_list = (
            portfolio_df.get_column("Symbol").to_list()
            if not portfolio_df.is_empty() and "Symbol" in portfolio_df.columns
            else []
        )

        security_info_task = data_fetcher.get_additional_security_info(upload_account_id, target_allocation)
        account_subs_task = data_fetcher.get_substitutes_per_symbol(
            upload_account_id,
            target_allocation,
        )
        account_sub_rows_task = data_fetcher.get_substitutes_per_account(
            upload_account_id,
            target_allocation,
        )
        wash_sale_sub_rows_task = data_fetcher.get_substitute_security_wash_sale(
            upload_account_id,
            target_allocation,
        )

        security_info_df, account_subs_map, account_sub_rows, wash_sale_sub_rows = await asyncio.gather(
            security_info_task, account_subs_task, account_sub_rows_task, wash_sale_sub_rows_task
        )

        return (upload_account_id, current_strategy, total_account_value, cash_reserve, custodian, owner_id,
                portfolio_df, security_info_df, account_subs_map, account_sub_rows, wash_sale_sub_rows)

    (upload_account_id, current_strategy, total_account_value, cash_reserve, custodian, owner_id,
     portfolio_df, security_info_df, account_substitutes, account_substitute_rows, wash_sale_substitute_rows) = asyncio.run(_fetch_parallel())
    substitute_options_by_symbol = build_substitute_options_by_symbol(account_substitute_rows)
    default_substitutes = build_default_substitutes_by_symbol(account_substitute_rows)

    tax_data.update({
        'current_strategy': current_strategy,
        'total_account_value': total_account_value,
        'cash_reserve': cash_reserve,
        'custodian': custodian,
        'owner_id': owner_id
    })

    portfolio = portfolio_df.to_dicts()

    # Build category lookup
    category_lookup = {}
    for row in security_info_df.iter_rows(named=True):
        symbol = row.get('Symbol')
        category = row.get('Category')
        if symbol and category:
            category_lookup[symbol] = category

    account_substitutes = account_substitutes or {}
    if account_substitutes:
        logger.info(f"🔄 Account-level substitutes: {account_substitutes}")

    # Process each holding
    wash_sale_enabled = tax_data.get('enable_wash_sale', True)
    excluded_securities = []
    restriction_type_securities = {}

    for holding in portfolio:
        symbol = holding.get('Symbol')
        if not symbol:
            continue

        # Normalize fixed income pricing
        security_type = str(holding.get('Security Type', '') or '').strip()
        current_price = float(holding.get('Current Price', 0) or 0)
        if security_type in _FI_SECURITY_TYPES and current_price > 1:
            shares = float(holding.get('Shares', 0) or 0)
            normalized_price = current_price / 100.0
            holding['Market Value'] = shares * normalized_price
            cost_basis = float(holding.get('Cost Basis', 0) or 0)
            holding['Unrealized Gain Loss'] = holding['Market Value'] - cost_basis

        # Add category information
        holding['Category'] = category_lookup.get(symbol, '')

        # Add account-level substitute info
        if symbol in account_substitutes:
            holding['account_substitute_target'] = account_substitutes[symbol]
            holding['default_substitute_target'] = default_substitutes.get(symbol, account_substitutes[symbol])
            use_legacy = tax_data.get('use_legacy_positions', False)
            if use_legacy:
                target_symbol = account_substitutes[symbol]
                target_category = category_lookup.get(target_symbol, target_symbol)
                holding['Category'] = target_category
                logger.debug(f"🏷️ Legacy category override: {symbol} → category '{target_category}' (from substitute target {target_symbol})")
        else:
            holding['account_substitute_target'] = ''
            holding['default_substitute_target'] = ''

        process_holding_restrictions(holding, wash_sale_enabled, excluded_securities, restriction_type_securities)

    # Build rebalance snapshot
    rebalance_snapshot = build_rebalance_category_snapshot(portfolio)

    tax_data['restriction_type_securities'] = restriction_type_securities
    tax_data['excluded_securities'] = excluded_securities
    tax_data['account_substitutes'] = account_substitutes
    tax_data['substitute_options_by_symbol'] = substitute_options_by_symbol
    tax_data['default_substitutes'] = default_substitutes
    tax_data['wash_sale_substitute_rows'] = (
        wash_sale_substitute_rows.to_dicts()
        if isinstance(wash_sale_substitute_rows, pl.DataFrame) and not wash_sale_substitute_rows.is_empty()
        else []
    )
    tax_data['wash_sale_blocked_symbols'] = (
        security_info_df
        .filter(pl.col("Wash Sale Blocked").cast(pl.Utf8).str.strip_chars().str.to_uppercase() == "YES")
        .get_column("Symbol")
        .to_list()
        if not security_info_df.is_empty()
        and {"Symbol", "Wash Sale Blocked"}.issubset(set(security_info_df.columns))
        else []
    )
    tax_data['force_liquidation_symbols'] = rebalance_snapshot.get('force_liquidation_symbols', [])
    tax_data['rebalance_category_current'] = {
        'equity_percent': rebalance_snapshot.get('equity_percent'),
        'fixed_income_percent': rebalance_snapshot.get('fixed_income_percent'),
    }

    logger.info(f"✅ Processed {len(portfolio)} holdings (parallel fetch), {len(restriction_type_securities)} restriction types, {len(account_substitutes)} account substitutes")
    return portfolio, restriction_type_securities


def process_holding_restrictions(holding, wash_sale_enabled, excluded_securities, restriction_type_securities):
    """Process restriction types for a single holding."""
    symbol = holding['Symbol']
    restriction_type = str(holding.get('Restriction Type') or '').strip()
    holding['restriction_type'] = restriction_type

    # Normalize sparse cash rows
    security_name = holding.get('Security Name')
    asset_class = holding.get('Asset Class')
    if symbol == 'CASH' and not security_name and not asset_class:
        holding['Security Name'] = 'Cash'
        holding['Asset Class'] = 'Cash'

    # Set database exclusion flags
    holding['db_billing_excluded'] = holding.get('Exclude From Billing', 'No') == 'Yes'
    holding['db_performance_excluded'] = holding.get('Exclude From Performance', 'No') == 'Yes'
    holding['db_exclusions'] = []
    if holding['db_billing_excluded']:
        holding['db_exclusions'].append('billing')
    if holding['db_performance_excluded']:
        holding['db_exclusions'].append('performance')

    if restriction_type == 'Unmanaged':
        holding.update({
            'is_unmanaged': True,
            'default_exclusions': ['trading'],
            'is_wash_sale': False,
            'has_restriction': True,
            'restriction_highlight': True
        })
        _add_to_restriction_type(restriction_type_securities, restriction_type, symbol)
        return

    if restriction_type == 'Wash Sale':
        holding.update({
            'is_unmanaged': False,
            'is_wash_sale': wash_sale_enabled,
            'default_exclusions': [],
            'has_restriction': True,
            'restriction_highlight': True
        })
        _add_to_restriction_type(restriction_type_securities, restriction_type, symbol)
        return

    if restriction_type in ['Buy', 'Sell', 'Hold']:
        holding.update({
            'is_unmanaged': False,
            'is_wash_sale': False,
            'default_exclusions': [],
            'has_restriction': True,
            'restriction_highlight': True
        })
        _add_to_restriction_type(restriction_type_securities, restriction_type, symbol)
        return

    holding.update({
        'is_unmanaged': False,
        'is_wash_sale': False,
        'has_restriction': False,
        'restriction_highlight': False
    })


def _add_to_restriction_type(restriction_type_securities, restriction_type, symbol):
    """Helper to add symbol to restriction type tracking."""
    if restriction_type not in restriction_type_securities:
        restriction_type_securities[restriction_type] = []
    if symbol not in restriction_type_securities[restriction_type]:
        restriction_type_securities[restriction_type].append(symbol)


def process_portfolio_exclusions(portfolio, tax_data, form_data):
    """Process form submissions and return exclusion lists.

    Returns:
        tuple: (trading_exclusions, performance_exclusions, billing_exclusions, restriction_type_securities)
    """
    trading_exclusions = []
    performance_exclusions = []
    billing_exclusions = []
    restriction_type_securities = {}
    wash_sale_enabled = tax_data.get('enable_wash_sale', True)

    portfolio_dict = {holding['Symbol']: holding for holding in portfolio if holding.get('Symbol')}
    disabled_wash_sale_symbols = {
        key.replace('wash_sale_rule_', '').strip().upper()
        for key, value in form_data.items()
        if key.startswith('wash_sale_rule_') and str(value or '').strip().lower() == 'off'
    }

    # Track restriction types
    for symbol, holding_data in portfolio_dict.items():
        restriction_type = str(holding_data.get('restriction_type', '')).strip()
        if restriction_type in ['Unmanaged', 'Buy', 'Sell', 'Hold']:
            _add_to_restriction_type(restriction_type_securities, restriction_type, symbol)
        elif (
            restriction_type == 'Wash Sale'
            and wash_sale_enabled
            and str(symbol or '').strip().upper() not in disabled_wash_sale_symbols
        ):
            _add_to_restriction_type(restriction_type_securities, restriction_type, symbol)

    # Track exclusion changes
    exclusion_changes = []

    for key, exclusion_types in form_data.items():
        if not key.startswith('exclusion_'):
            continue

        symbol = key.replace('exclusion_', '')
        holding_data = portfolio_dict.get(symbol, {})
        restriction_type = str(holding_data.get('restriction_type', '')).strip()

        if restriction_type in ['Buy', 'Sell', 'Hold']:
            _add_to_restriction_type(restriction_type_securities, restriction_type, symbol)

        user_exclusions = []
        if exclusion_types:
            user_exclusions = [e.strip() for e in exclusion_types.split(',')]

        # Detect DB exclusion changes
        db_billing = holding_data.get('db_billing_excluded', False)
        db_performance = holding_data.get('db_performance_excluded', False)

        if db_billing and 'billing' not in user_exclusions:
            exclusion_changes.append({'symbol': symbol, 'exclusion_type': 'Billing', 'change': 'removed', 'detail': 'DB Billing Exclusion → Removed'})
            logger.info(f"🔄 Exclusion change: {symbol} - Billing exclusion REMOVED (was in DB)")

        if db_performance and 'performance' not in user_exclusions:
            exclusion_changes.append({'symbol': symbol, 'exclusion_type': 'Performance', 'change': 'removed', 'detail': 'DB Performance Exclusion → Removed'})
            logger.info(f"🔄 Exclusion change: {symbol} - Performance exclusion REMOVED (was in DB)")

        if not db_billing and 'billing' in user_exclusions:
            exclusion_changes.append({'symbol': symbol, 'exclusion_type': 'Billing', 'change': 'added', 'detail': 'Billing Exclusion → Added'})
            logger.info(f"🔄 Exclusion change: {symbol} - Billing exclusion ADDED (not in DB)")

        if not db_performance and 'performance' in user_exclusions:
            exclusion_changes.append({'symbol': symbol, 'exclusion_type': 'Performance', 'change': 'added', 'detail': 'Performance Exclusion → Added'})
            logger.info(f"🔄 Exclusion change: {symbol} - Performance exclusion ADDED (not in DB)")

        if 'trading' in user_exclusions:
            exclusion_changes.append({'symbol': symbol, 'exclusion_type': 'Trading', 'change': 'added', 'detail': 'Trading Exclusion → Added'})

        # Add DB exclusions only if user kept them
        if db_billing and 'billing' in user_exclusions:
            billing_exclusions.append(symbol)
        if db_performance and 'performance' in user_exclusions:
            performance_exclusions.append(symbol)

        # Add user-selected exclusions
        if 'trading' in user_exclusions:
            trading_exclusions.append(symbol)
        if 'performance' in user_exclusions and not db_performance:
            performance_exclusions.append(symbol)
        if 'billing' in user_exclusions and not db_billing:
            billing_exclusions.append(symbol)

    if exclusion_changes:
        tax_data['exclusion_changes'] = exclusion_changes
        logger.info(f"📝 Tracked {len(exclusion_changes)} exclusion change(s)")
    else:
        tax_data['exclusion_changes'] = []
    tax_data['wash_sale_disabled_symbols'] = sorted(disabled_wash_sale_symbols)

    logger.debug(
        "[WASH_SALE_DEBUG] process_portfolio_exclusions_result "
        f"account_number={tax_data.get('account_number')!r} "
        f"wash_sale_enabled={wash_sale_enabled} "
        f"wash_sale_disabled_symbols={sorted(disabled_wash_sale_symbols)} "
        f"wash_sale_symbols={restriction_type_securities.get('Wash Sale', []) or []} "
        f"trading_exclusions={trading_exclusions} "
        f"restriction_type_securities={restriction_type_securities}"
    )

    return trading_exclusions, performance_exclusions, billing_exclusions, restriction_type_securities


def build_rebalance_category_snapshot(portfolio_rows, trading_exclusions=None, excluded_unmanaged_positions=None):
    """Build current Equity/Fixed Income percentages from Rebalance Category holdings."""
    equity_value = 0.0
    fixed_income_value = 0.0
    force_liquidation_symbols = set()
    excluded_set = {
        str(s or '').strip().upper()
        for s in (trading_exclusions or [])
        if str(s or '').strip()
    }
    unmanaged_excluded_set = {
        str(p.get('symbol') or '').strip().upper()
        for p in (excluded_unmanaged_positions or [])
        if isinstance(p, dict) and str(p.get('symbol') or '').strip()
    }

    for row in portfolio_rows or []:
        symbol = str(row.get('Symbol') or '').strip()
        if not symbol:
            continue

        restriction_type = str(row.get('Restriction Type') or row.get('restriction_type') or '').strip().lower()
        unmanaged_flag = str(row.get('Unmanaged') or '').strip().lower()
        normalized_symbol = symbol.upper()
        if (
            normalized_symbol in excluded_set
            or normalized_symbol in unmanaged_excluded_set
            or restriction_type == 'unmanaged'
            or unmanaged_flag == 'yes'
        ):
            continue

        rebalance_category = str(row.get('Rebalance Category') or '').strip().lower()
        market_value = float(row.get('Market Value') or 0.0)

        if rebalance_category == 'equity':
            equity_value += market_value
        elif rebalance_category in {'fixed', 'fixed income'}:
            fixed_income_value += market_value
        elif symbol.upper() != 'CASH' and restriction_type != 'unmanaged':
            force_liquidation_symbols.add(symbol)

    managed_total = equity_value + fixed_income_value
    if managed_total > 0:
        equity_percent = (equity_value / managed_total) * 100.0
        fixed_income_percent = (fixed_income_value / managed_total) * 100.0
    else:
        equity_percent = None
        fixed_income_percent = None

    return {
        'equity_percent': equity_percent,
        'fixed_income_percent': fixed_income_percent,
        'equity_value': equity_value,
        'fixed_income_value': fixed_income_value,
        'managed_total_value': managed_total,
        'force_liquidation_symbols': sorted(force_liquidation_symbols),
    }


def _normalize_rebalance_category(value) -> str:
    """Normalize Rebalance Category values to the tolerance buckets."""
    category = str(value or '').strip().lower()
    if category == 'equity':
        return 'equity'
    if category in {'fixed', 'fixed income'}:
        return 'fixed income'
    return ''


def normalize_optimizer_buy_lot_metadata(optimized_portfolio_df, excluded_symbols=None):
    """Normalize optimizer-created target buy-lot metadata before tolerance checks.

    Zero-quantity target buy lots can inherit an account-level ``Unmanaged`` flag
    even when the user did not keep that symbol excluded. Clear only that false
    unmanaged flag for non-excluded buy lots.

    Rebalance Category is intentionally not inferred from broad Category here.
    Model-assignment tolerance uses only the explicit ``Rebalance Category`` value
    returned by ``get_additional_security_info``; blank values remain blank and
    are excluded from the tolerance denominator.
    """
    if optimized_portfolio_df is None:
        return optimized_portfolio_df
    try:
        if optimized_portfolio_df.is_empty():
            return optimized_portfolio_df
    except Exception:
        return optimized_portfolio_df

    required_cols = {'Symbol', 'Lot Quantity'}
    if not required_cols.issubset(set(optimized_portfolio_df.columns)):
        return optimized_portfolio_df
    if 'Unmanaged' not in optimized_portfolio_df.columns:
        return optimized_portfolio_df

    excluded_set = {
        str(symbol or '').strip().upper()
        for symbol in (excluded_symbols or [])
        if str(symbol or '').strip()
    }
    buy_lot_expr = pl.col('Lot Quantity').cast(pl.Float64, strict=False).fill_null(0.0) == 0.0
    symbol_not_excluded = ~pl.col('Symbol').cast(pl.Utf8).str.strip_chars().str.to_uppercase().is_in(list(excluded_set))

    return optimized_portfolio_df.with_columns(
        pl.when(buy_lot_expr & symbol_not_excluded)
        .then(pl.lit('No'))
        .otherwise(pl.col('Unmanaged'))
        .alias('Unmanaged')
    )


def build_rebalance_category_from_optimized_portfolio(optimized_portfolio_df, trading_exclusions=None, excluded_unmanaged_positions=None):
    """Compute Equity/Fixed Income percentages from the optimizer output DataFrame.

    Uses the ``Rebalance Category`` column directly (values: "Equity", "Fixed").
    Securities without a Rebalance Category value (Cash, Alternatives, etc.) are
    excluded from the managed total.

    The tolerance check evaluates only the MANAGED portion of the account —
    unmanaged and trading-excluded securities are carved out of the model sleeve
    and should not count toward the model-assignment tolerance.

    Args:
        optimized_portfolio_df: Polars DataFrame produced by the optimizer,
            containing at minimum ``Symbol``, ``Rebalance Category``, and
            ``Final Market Value`` columns.
        trading_exclusions: List of symbol strings excluded from trading.
        excluded_unmanaged_positions: Excluded unmanaged rows captured outside the
            optimized frame; accepted for API compatibility.

    Returns:
        dict with the same keys as ``build_rebalance_category_snapshot``.
    """
    equity_value = 0.0
    fixed_income_value = 0.0

    empty = {
        'equity_percent': None,
        'fixed_income_percent': None,
        'equity_value': 0.0,
        'fixed_income_value': 0.0,
        'managed_total_value': 0.0,
        'force_liquidation_symbols': [],
    }

    if optimized_portfolio_df is None:
        return empty

    try:
        if optimized_portfolio_df.is_empty():
            return empty
    except Exception:
        return empty

    required_cols = {'Symbol', 'Final Market Value', 'Rebalance Category'}
    if not required_cols.issubset(set(optimized_portfolio_df.columns)):
        return empty

    debug_enabled = model_assignment_debug_enabled()
    has_unmanaged_col = 'Unmanaged' in optimized_portfolio_df.columns
    excluded_set = {
        str(s or '').strip().upper()
        for s in (trading_exclusions or [])
        if str(s or '').strip()
    }
    unmanaged_excluded_set = {
        str(p.get('symbol') or '').strip().upper()
        for p in (excluded_unmanaged_positions or [])
        if isinstance(p, dict) and str(p.get('symbol') or '').strip()
    }

    if debug_enabled:
        logger.info(
            "[MODEL_ASSIGNMENT_DEBUG] build_rebalance_category_from_optimized_portfolio "
            f"shape={getattr(optimized_portfolio_df, 'shape', None)} "
            f"columns={list(getattr(optimized_portfolio_df, 'columns', []))} "
            f"has_rebalance_col=True has_unmanaged_col={has_unmanaged_col} "
            f"trading_exclusions={sorted(excluded_set)} "
            f"excluded_unmanaged_positions={sorted(unmanaged_excluded_set)}"
        )
    logger.debug(
        "[MODEL_ASSIGNMENT_DEBUG] build_rebalance_category_from_optimized_portfolio "
        f"shape={getattr(optimized_portfolio_df, 'shape', None)} "
        f"columns={list(getattr(optimized_portfolio_df, 'columns', []))} "
        f"has_rebalance_col=True has_unmanaged_col={has_unmanaged_col} "
        f"trading_exclusions={sorted(excluded_set)} "
        f"excluded_unmanaged_positions={sorted(unmanaged_excluded_set)}"
    )

    try:
        unmanaged_expr = (
            pl.col('Unmanaged').cast(pl.Utf8).str.strip_chars().str.to_lowercase()
            if has_unmanaged_col
            else pl.lit('')
        )
        normalized = (
            optimized_portfolio_df
            .with_columns([
                pl.col('Symbol').cast(pl.Utf8).str.strip_chars().alias('_symbol'),
                pl.col('Symbol').cast(pl.Utf8).str.strip_chars().str.to_uppercase().alias('_symbol_upper'),
                pl.col('Final Market Value').cast(pl.Float64, strict=False).fill_null(0.0).alias('_final_market_value'),
                unmanaged_expr.fill_null('').alias('_unmanaged_norm'),
                pl.col('Rebalance Category').cast(pl.Utf8).str.strip_chars().str.to_lowercase().fill_null('').alias('_rebalance_raw'),
            ])
            .with_columns(
                pl.when(pl.col('_rebalance_raw') == 'equity')
                .then(pl.lit('equity'))
                .when(pl.col('_rebalance_raw').is_in(['fixed', 'fixed income']))
                .then(pl.lit('fixed income'))
                .otherwise(pl.lit(''))
                .alias('_rebalance_norm')
            )
        )

        decisions = (
            normalized
            .with_columns(
                pl.when(pl.col('_symbol') == '')
                .then(pl.lit('missing_symbol'))
                .when(pl.col('_symbol_upper').is_in(list(excluded_set)))
                .then(pl.lit('trading_or_unmanaged_exclusion_symbol'))
                .when(pl.col('_symbol_upper').is_in(list(unmanaged_excluded_set)))
                .then(pl.lit('excluded_unmanaged_position'))
                .when(pl.col('_unmanaged_norm') == 'yes')
                .then(pl.lit('unmanaged_flag_yes'))
                .when(pl.col('_rebalance_norm') == '')
                .then(pl.lit('missing_or_unrecognized_rebalance_category'))
                .otherwise(pl.lit('included'))
                .alias('_decision')
            )
        )
        debug_cols = [
            col for col in [
                'Symbol', 'Security Description', 'Final Market Value',
                'Category', 'Asset Class', 'Security Type', 'Rebalance Category',
                'Account Rebalance Category', 'Target Rebalance Category',
                'Security Info Rebalance Category', 'Metadata Source',
                'Unmanaged', '_rebalance_norm', '_decision',
            ] if col in decisions.columns
        ]
        filtered = decisions.filter(pl.col('_decision') == 'included')
        skipped = decisions.filter(pl.col('_decision') != 'included')

        if debug_enabled or logger.isEnabledFor(logging.DEBUG):
            skipped_by_reason = (
                skipped
                .group_by('_decision')
                .agg([
                    pl.len().alias('_count'),
                    pl.sum('_final_market_value').alias('_market_value'),
                ])
                .sort('_market_value', descending=True)
                .to_dicts()
                if skipped.height
                else []
            )
            included_by_symbol = (
                filtered
                .group_by(['_rebalance_norm', 'Symbol'])
                .agg(pl.sum('_final_market_value').alias('_market_value'))
                .sort(['_rebalance_norm', '_market_value'], descending=[False, True])
                .to_dicts()
            )
            logger.debug(
                "[MODEL_ASSIGNMENT_DEBUG] optimized_rebalance_category_rows "
                f"row_decisions={decisions.select(debug_cols).to_dicts()} "
                f"skipped_rows={skipped.select(debug_cols).to_dicts() if skipped.height else []} "
                f"skipped_totals_by_reason={skipped_by_reason} "
                f"included_totals_by_symbol={included_by_symbol}"
            )

        totals = {
            row['_rebalance_norm']: float(row['_market_value'] or 0.0)
            for row in filtered.group_by('_rebalance_norm')
            .agg(pl.sum('_final_market_value').alias('_market_value'))
            .iter_rows(named=True)
        }
        equity_value = totals.get('equity', 0.0)
        fixed_income_value = totals.get('fixed income', 0.0)

        if debug_enabled:
            logger.info(
                "[MODEL_ASSIGNMENT_DEBUG] row_decision_counts "
                f"included={filtered.height} skipped={optimized_portfolio_df.height - filtered.height}"
            )
        logger.debug(
            "[MODEL_ASSIGNMENT_DEBUG] row_decision_counts "
            f"included={filtered.height} skipped={optimized_portfolio_df.height - filtered.height}"
        )
    except Exception as exc:
        logger.warning(f"Failed to build optimized rebalance-category snapshot: {exc}")
        if debug_enabled:
            logger.warning(f"[MODEL_ASSIGNMENT_DEBUG] failed_to_build_snapshot error={exc}")
        logger.debug(f"[MODEL_ASSIGNMENT_DEBUG] failed_to_build_snapshot error={exc}")
        return empty

    managed_total = equity_value + fixed_income_value
    if managed_total > 0:
        equity_percent = (equity_value / managed_total) * 100.0
        fixed_income_percent = (fixed_income_value / managed_total) * 100.0
    else:
        equity_percent = None
        fixed_income_percent = None

    if debug_enabled:
        logger.info(
            "[MODEL_ASSIGNMENT_DEBUG] computed_snapshot "
            f"equity_value={equity_value:.2f} fixed_income_value={fixed_income_value:.2f} "
            f"managed_total={managed_total:.2f} equity_percent={equity_percent} "
            f"fixed_income_percent={fixed_income_percent}"
        )
    logger.debug(
        "[MODEL_ASSIGNMENT_DEBUG] computed_snapshot "
        f"equity_value={equity_value:.2f} fixed_income_value={fixed_income_value:.2f} "
        f"managed_total={managed_total:.2f} equity_percent={equity_percent} "
        f"fixed_income_percent={fixed_income_percent}"
    )

    return {
        'equity_percent': equity_percent,
        'fixed_income_percent': fixed_income_percent,
        'equity_value': equity_value,
        'fixed_income_value': fixed_income_value,
        'managed_total_value': managed_total,
        'force_liquidation_symbols': [],
    }


def validate_target_portfolio_trading_restrictions(tax_data, trading_exclusions, data_fetcher):
    """Validate that no target portfolio securities have trading restrictions.

    Returns:
        dict: {'valid': bool, 'message': str, 'restricted_securities': list}
    """
    target_allocation = tax_data.get('target_allocation')
    if not target_allocation:
        return {'valid': True, 'message': '', 'restricted_securities': []}

    try:
        target_allocation_df = asyncio.run(data_fetcher.get_target_allocation(target_allocation))

        target_securities = []
        for row in target_allocation_df.iter_rows(named=True):
            if row.get('Target Weight', 0) > 0:
                target_securities.append(row['Symbol'])

        restricted_target_securities = []
        restriction_type_securities = tax_data.get('restriction_type_securities', {})
        wash_sale_securities = restriction_type_securities.get('Wash Sale', [])

        for symbol in trading_exclusions:
            if symbol in target_securities and symbol not in wash_sale_securities:
                restricted_target_securities.append(symbol)

        if restricted_target_securities:
            message = f"Cannot run optimization: {len(restricted_target_securities)} target portfolio security(ies) have trading restrictions"
            return {
                'valid': False,
                'message': message,
                'restricted_securities': restricted_target_securities,
                'target_securities': target_securities,
                'total_restricted': len(restricted_target_securities)
            }

        return {'valid': True, 'message': '', 'restricted_securities': []}

    except Exception as e:
        logger.error(f"❌ Error validating target portfolio restrictions: {e}")
        return {'valid': False, 'message': f"Validation error: {str(e)}", 'restricted_securities': []}
