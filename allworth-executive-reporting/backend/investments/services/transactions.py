"""Warehouse-backed transaction history.

Reads activity from the Tamarac transaction staging tables and returns flat,
Tamarac-style rows for the Account Lookup → Transactions tab, plus a helper that
surfaces bonds *called* (redeemed) in a trailing window for the Bond Ladder
monitor.

Two source tables are unioned when present:

* ``tav.transactions_staging``          — recent activity
* ``tav.transactions_sells_over_30``    — sells older than 30 days

Column names are discovered at runtime (mirroring :mod:`app.services.db_analyzer`)
so the query self-adapts to whatever the real warehouse schema exposes.  A
"called" bond is one whose transaction notes contain ``REDEMP`` and do **not**
contain ``MATURED``.
"""

from __future__ import annotations

from datetime import date, timedelta
import threading
import time

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from investments.services.db_analyzer import (
    _build_select_clause_aliased,
    _first_existing_column,
    _get_table_columns,
    _to_date,
    _to_float,
)
from investments.services.bond_ladder import get_bond_ladder_account_numbers

# Both tables are unioned together (they are complementary, not alternatives).
TRANSACTION_TABLES: list[tuple[str, str]] = [
    ("tav", "transactions_staging"),
    ("tav", "transactions_sells_over_30"),
]

# The warehouse currently publishes this external table without "staging" in
# its name. Keep the requested name as a fallback for compatible environments.
CALLED_BONDS_TABLES = [
    ("tav", "transactions_sells_over_30"),
    ("tav", "transactions_staging_sells_over_30"),
]
CALLED_REPORT_CACHE_TTL_SECONDS = 15 * 60
CASH_MINIMUM_PERCENT = 3.0

_called_report_cache: dict[tuple[str, str], tuple[float, dict]] = {}
_called_report_cache_lock = threading.Lock()

TRANSACTION_COLUMN_CANDIDATES: dict[str, list[str]] = {
    "Transaction_ID": ["Transaction_ID", "Transaction ID", "TransactionID", "ID"],
    "Account_Number": ["Account_Number", "Account Number", "Account", "AccountNumber"],
    "Account_Name": ["Account_Name", "Account Name"],
    "Trade_Date": [
        "Trade_Date", "Trade Date", "Transaction_Date", "Transaction Date",
        "Settlement_Date", "Settle_Date", "Post_Date", "Posted_Date",
        "Activity_Date", "As_Of_Date", "Date",
    ],
    "Transaction_Type": [
        "Activity_Type", "Activity Type", "Transaction_Type", "Transaction Type", "Type",
        "Action", "Transaction_Code", "Trans_Type", "Category",
    ],
    "Notes": [
        "Notes", "Note", "Transaction_Notes", "Memo", "Comment", "Comments",
        "Detail", "Details", "Description", "Security_Description",
    ],
    "Symbol": ["Symbol", "Ticker"],
    "CUSIP": ["CUSIP"],
    "Security_Description": [
        "Security_Description", "Security Description", "Description", "Name",
    ],
    "Quantity": ["Quantity", "Shares", "Units", "Face", "Par", "Amount_Shares"],
    "Price": ["Price", "Unit_Price", "Trade_Price", "Unit Price"],
    "Amount": [
        "Amount", "Net_Amount", "Net Amount", "Total_Amount", "Transaction_Amount",
        "Gross_Amount", "Principal", "Total", "Cash_Amount",
    ],
}


def _table_ref(schema: str, table: str) -> str:
    return f"[{schema}].[{table}]"


def _query_one_table(
    session: Session,
    schema: str,
    table: str,
    account_numbers: list[str],
    *,
    since: date | None,
    redemptions_only: bool,
) -> list[dict]:
    """Return normalized rows from a single transaction table, or [] if absent."""
    columns = _get_table_columns(session, schema=schema, table=table)
    if not columns:
        return []

    account_col = _first_existing_column(columns, TRANSACTION_COLUMN_CANDIDATES["Account_Number"])
    if not account_col:
        # Without an account column we cannot scope safely; skip this table.
        return []

    select_clause = _build_select_clause_aliased(TRANSACTION_COLUMN_CANDIDATES, columns, "t")

    notes_col = _first_existing_column(columns, TRANSACTION_COLUMN_CANDIDATES["Notes"])
    date_col = _first_existing_column(columns, TRANSACTION_COLUMN_CANDIDATES["Trade_Date"])

    where = [f"t.[{account_col}] IN :account_numbers"]
    params: dict = {"account_numbers": account_numbers}

    if redemptions_only and notes_col:
        where.append(
            f"UPPER(CAST(t.[{notes_col}] AS NVARCHAR(MAX))) LIKE '%REDEMP%' "
            f"AND UPPER(CAST(t.[{notes_col}] AS NVARCHAR(MAX))) NOT LIKE '%MATURED%'"
        )
    if since and date_col:
        where.append(f"t.[{date_col}] >= :since")
        params["since"] = since.isoformat()

    stmt = text(
        f"SELECT {select_clause} FROM {_table_ref(schema, table)} AS t "
        f"WHERE {' AND '.join(where)}"
    ).bindparams(bindparam("account_numbers", expanding=True))

    rows = session.execute(stmt, params).mappings().all()
    return [dict(r) for r in rows]


def _normalize_row(raw: dict, source: str) -> dict:
    trade_date = _to_date(raw.get("Trade_Date"))
    return {
        "transaction_id": str(raw.get("Transaction_ID") or "").strip() or None,
        "account_number": str(raw.get("Account_Number") or "").strip(),
        "account_name": str(raw.get("Account_Name") or "").strip(),
        "trade_date": trade_date.isoformat() if trade_date else None,
        "transaction_type": str(raw.get("Transaction_Type") or "").strip() or None,
        "symbol": str(raw.get("Symbol") or "").strip() or None,
        "cusip": str(raw.get("CUSIP") or "").strip() or None,
        "description": str(raw.get("Security_Description") or "").strip() or None,
        "quantity": _to_float(raw.get("Quantity")),
        "price": _to_float(raw.get("Price")),
        "amount": _to_float(raw.get("Amount")),
        "notes": str(raw.get("Notes") or "").strip() or None,
        "source": source,
    }


def get_transactions(
    session: Session,
    account_numbers: list[str],
    *,
    since: date | None = None,
    redemptions_only: bool = False,
) -> list[dict]:
    """Return unioned, normalized transaction rows sorted by trade date desc."""
    normalized = list(dict.fromkeys(str(a).strip() for a in account_numbers if str(a).strip()))
    if not normalized:
        return []

    rows: list[dict] = []
    seen: set[tuple] = set()
    for schema, table in TRANSACTION_TABLES:
        try:
            raw_rows = _query_one_table(
                session, schema, table, normalized,
                since=since, redemptions_only=redemptions_only,
            )
        except Exception:
            # A missing table or column shape mismatch should not break the tab.
            continue
        for raw_row in raw_rows:
            row = _normalize_row(raw_row, f"{schema}.{table}")
            identity = (
                ("id", row["account_number"], row["transaction_id"])
                if row["transaction_id"]
                else (
                    "fields",
                    row["account_number"],
                    row["trade_date"],
                    row["transaction_type"],
                    row["symbol"],
                    row["cusip"],
                    row["description"],
                    row["quantity"],
                    row["price"],
                    row["amount"],
                    row["notes"],
                )
            )
            if identity in seen:
                continue
            seen.add(identity)
            rows.append(row)

    rows.sort(key=lambda r: r["trade_date"] or "", reverse=True)
    return rows


def get_recent_redemptions(
    session: Session,
    account_numbers: list[str],
    *,
    days: int = 30,
) -> list[dict]:
    """Return bonds redeemed (called) in the trailing ``days`` window.

    Identified by transaction notes containing ``REDEMP`` and not ``MATURED``.
    """
    since = date.today() - timedelta(days=days)
    return get_transactions(
        session, account_numbers, since=since, redemptions_only=True,
    )


def invalidate_called_report_cache() -> None:
    with _called_report_cache_lock:
        _called_report_cache.clear()


def _activity_filter(column: str, activity: str, alias: str = "t") -> str:
    return (
        f"UPPER(LTRIM(RTRIM(CAST([{alias}].[{column}] AS NVARCHAR(50))))) "
        f"= '{activity.upper()}'"
    )


def _load_called_transactions(
    session: Session,
    *,
    start_date: date,
    end_date: date,
) -> list[dict]:
    """Read only recent called-bond sells from the requested external table."""
    schema = table = ""
    columns: set[str] = set()
    for candidate_schema, candidate_table in CALLED_BONDS_TABLES:
        candidate_columns = _get_table_columns(
            session, schema=candidate_schema, table=candidate_table
        )
        if candidate_columns:
            schema, table, columns = candidate_schema, candidate_table, candidate_columns
            break
    if not columns:
        checked = ", ".join(f"{s}.{t}" for s, t in CALLED_BONDS_TABLES)
        raise RuntimeError(f"Could not find a called-bond transaction table. Checked: {checked}.")

    activity_col = _first_existing_column(
        columns, TRANSACTION_COLUMN_CANDIDATES["Transaction_Type"]
    )
    notes_col = _first_existing_column(columns, TRANSACTION_COLUMN_CANDIDATES["Notes"])
    date_col = _first_existing_column(columns, TRANSACTION_COLUMN_CANDIDATES["Trade_Date"])
    account_col = _first_existing_column(
        columns, TRANSACTION_COLUMN_CANDIDATES["Account_Number"]
    )
    missing = [
        name
        for name, value in {
            "Account_Number": account_col,
            "Activity_Type": activity_col,
            "Notes": notes_col,
            "Trade_Date": date_col,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"{schema}.{table} is missing required columns: {', '.join(missing)}."
        )

    select_clause = _build_select_clause_aliased(
        TRANSACTION_COLUMN_CANDIDATES, columns, "t"
    )
    stmt = text(
        f"SELECT {select_clause} "
        f"FROM {_table_ref(schema, table)} AS t "
        f"WHERE t.[{date_col}] >= :start_date "
        f"AND t.[{date_col}] <= :end_date "
        f"AND {_activity_filter(activity_col, 'Sell')} "
        f"AND UPPER(CAST(t.[{notes_col}] AS NVARCHAR(MAX))) LIKE '%REDEMP%' "
        f"AND UPPER(CAST(t.[{notes_col}] AS NVARCHAR(MAX))) NOT LIKE '%MATURED%'"
    )
    rows = session.execute(
        stmt,
        {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
    ).mappings().all()
    return [_normalize_row(dict(row), f"{schema}.{table}") for row in rows]


def _load_account_cash(
    session: Session,
    account_numbers: list[str],
) -> dict[str, dict[str, float | str]]:
    """Load only holdings for affected accounts and aggregate their cash."""
    if not account_numbers:
        return {}

    schema, table = ("tav", "Account_Daily_Holdings")
    columns = _get_table_columns(session, schema=schema, table=table)
    account_col = _first_existing_column(
        columns, TRANSACTION_COLUMN_CANDIDATES["Account_Number"]
    )
    value_col = _first_existing_column(
        columns,
        ["Holdings_Current_Value", "Market_Value", "Market Value", "Total_Account_Value"],
    )
    account_name_col = _first_existing_column(
        columns, TRANSACTION_COLUMN_CANDIDATES["Account_Name"]
    )
    if not columns or not account_col or not value_col:
        return {}

    cash_markers = []
    for candidates in (
        ["Asset_Class", "Asset Class", "Primary_Asset_Class", "Primary Asset Class"],
        ["Subsector"],
        ["Security_Type", "Security Type"],
        ["Symbol"],
        ["Security_Description", "Security Description", "Description"],
    ):
        column = _first_existing_column(columns, candidates)
        if column:
            cash_markers.append(
                f"UPPER(COALESCE(CAST(h.[{column}] AS NVARCHAR(255)), '')) LIKE '%CASH%'"
            )
    cash_expression = " OR ".join(cash_markers) or "1 = 0"
    name_expression = (
        f"MAX(CAST(h.[{account_name_col}] AS NVARCHAR(255)))"
        if account_name_col
        else "NULL"
    )
    stmt = (
        text(
            f"SELECT CAST(h.[{account_col}] AS NVARCHAR(255)) AS [Account_Number], "
            f"{name_expression} AS [Account_Name], "
            f"SUM(ABS(COALESCE(TRY_CAST(h.[{value_col}] AS FLOAT), 0))) AS [Account_Value], "
            f"SUM(CASE WHEN {cash_expression} "
            f"THEN ABS(COALESCE(TRY_CAST(h.[{value_col}] AS FLOAT), 0)) ELSE 0 END) "
            f"AS [Cash_Value] "
            f"FROM [{schema}].[{table}] AS h "
            f"WHERE h.[{account_col}] IN :account_numbers "
            f"GROUP BY h.[{account_col}]"
        )
        .bindparams(bindparam("account_numbers", expanding=True))
    )
    rows = session.execute(
        stmt, {"account_numbers": account_numbers}
    ).mappings().all()
    result: dict[str, dict[str, float | str]] = {}
    for raw in rows:
        row = dict(raw)
        account = str(row.get("Account_Number") or "").strip()
        account_value = abs(_to_float(row.get("Account_Value")) or 0.0)
        cash_value = abs(_to_float(row.get("Cash_Value")) or 0.0)
        result[account] = {
            "account_name": str(row.get("Account_Name") or "").strip(),
            "account_value": account_value,
            "cash_value": cash_value,
            "cash_percent": (cash_value / account_value * 100.0) if account_value else 0.0,
        }
    return result


def _load_recent_buys(
    session: Session,
    account_numbers: list[str],
    *,
    start_date: date,
    end_date: date,
    match_values: list[float],
) -> list[dict]:
    """Push date/activity/account predicates into the external BUY scan."""
    if not account_numbers or not match_values:
        return []
    schema = table = ""
    columns: set[str] = set()
    for candidate_schema, candidate_table in CALLED_BONDS_TABLES:
        candidate_columns = _get_table_columns(
            session, schema=candidate_schema, table=candidate_table
        )
        if candidate_columns:
            schema, table, columns = candidate_schema, candidate_table, candidate_columns
            break
    account_col = _first_existing_column(
        columns, TRANSACTION_COLUMN_CANDIDATES["Account_Number"]
    )
    activity_col = _first_existing_column(
        columns, TRANSACTION_COLUMN_CANDIDATES["Transaction_Type"]
    )
    date_col = _first_existing_column(columns, TRANSACTION_COLUMN_CANDIDATES["Trade_Date"])
    quantity_col = _first_existing_column(
        columns, TRANSACTION_COLUMN_CANDIDATES["Quantity"]
    )
    amount_col = _first_existing_column(columns, TRANSACTION_COLUMN_CANDIDATES["Amount"])
    if not account_col or not activity_col or not date_col:
        return []
    select_clause = _build_select_clause_aliased(
        TRANSACTION_COLUMN_CANDIDATES, columns, "t"
    )
    match_col = quantity_col or amount_col
    value_filter = (
        f" AND ROUND(ABS(TRY_CAST(t.[{match_col}] AS FLOAT)), 2) IN :match_values"
        if match_col
        else ""
    )
    stmt = text(
        f"SELECT {select_clause} "
        f"FROM {_table_ref(schema, table)} AS t "
        f"WHERE t.[{date_col}] >= :start_date "
        f"AND t.[{date_col}] <= :end_date "
        f"AND {_activity_filter(activity_col, 'Buy')} "
        f"AND t.[{account_col}] IN :account_numbers"
        f"{value_filter}"
    ).bindparams(bindparam("account_numbers", expanding=True))
    params: dict = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "account_numbers": account_numbers,
    }
    if value_filter:
        stmt = stmt.bindparams(bindparam("match_values", expanding=True))
        params["match_values"] = match_values
    rows = session.execute(
        stmt, params
    ).mappings().all()
    return [_normalize_row(dict(row), f"{schema}.{table}") for row in rows]


def _load_bond_identifiers(
    session: Session,
    cusips: list[str],
    symbols: list[str],
) -> tuple[set[str], set[str]]:
    """Resolve the small BUY identifier set against tav.Security_Info."""
    if not cusips and not symbols:
        return set(), set()
    columns = _get_table_columns(session, schema="tav", table="Security_Info")
    cusip_col = _first_existing_column(columns, ["CUSIP"])
    symbol_col = _first_existing_column(columns, ["Symbol"])
    if not cusip_col and not symbol_col:
        return set(), set()
    security_type_col = _first_existing_column(columns, ["Security_Type", "Security Type"])
    maturity_col = _first_existing_column(
        columns, ["Maturity_Date", "Maturity Date", "Redemption_Date"]
    )
    description_col = _first_existing_column(
        columns, ["Security_Description", "Security Description", "Description"]
    )
    type_select = (
        f"s.[{security_type_col}] AS [Security_Type]"
        if security_type_col
        else "NULL AS [Security_Type]"
    )
    maturity_select = (
        f"s.[{maturity_col}] AS [Maturity_Date]"
        if maturity_col
        else "NULL AS [Maturity_Date]"
    )
    description_select = (
        f"s.[{description_col}] AS [Security_Description]"
        if description_col
        else "NULL AS [Security_Description]"
    )
    cusip_select = f"s.[{cusip_col}] AS [CUSIP]" if cusip_col else "NULL AS [CUSIP]"
    symbol_select = f"s.[{symbol_col}] AS [Symbol]" if symbol_col else "NULL AS [Symbol]"
    predicates: list[str] = []
    params: dict = {}
    if cusip_col and cusips:
        predicates.append(f"s.[{cusip_col}] IN :cusips")
        params["cusips"] = cusips
    if symbol_col and symbols:
        predicates.append(f"s.[{symbol_col}] IN :symbols")
        params["symbols"] = symbols
    stmt = text(
        f"SELECT {cusip_select}, {symbol_select}, {type_select}, "
        f"{maturity_select}, {description_select} "
        f"FROM [tav].[Security_Info] AS s "
        f"WHERE {' OR '.join(predicates)}"
    )
    if "cusips" in params:
        stmt = stmt.bindparams(bindparam("cusips", expanding=True))
    if "symbols" in params:
        stmt = stmt.bindparams(bindparam("symbols", expanding=True))
    rows = session.execute(stmt, params).mappings().all()
    bond_cusips: set[str] = set()
    bond_symbols: set[str] = set()
    bond_terms = ("BOND", "FIXED INCOME", "MUNICIPAL", "CORPORATE", "TREASURY", "NOTE")
    for raw in rows:
        row = dict(raw)
        security_text = " ".join(
            str(row.get(field) or "").upper()
            for field in ("Security_Type", "Security_Description")
        )
        if row.get("Maturity_Date") is not None or any(term in security_text for term in bond_terms):
            if row.get("CUSIP"):
                bond_cusips.add(str(row["CUSIP"]).strip())
            if row.get("Symbol"):
                bond_symbols.add(str(row["Symbol"]).strip())
    return bond_cusips, bond_symbols


def _same_quantity(left: float | None, right: float | None) -> bool:
    if left is None or right is None:
        return False
    return abs(abs(left) - abs(right)) <= max(0.01, abs(left) * 0.000001)


def _transaction_match_value(row: dict) -> float | None:
    """Use quantity when published; otherwise use the source transaction amount."""
    quantity = row.get("quantity")
    return quantity if quantity is not None else row.get("amount")


def get_called_bonds_review(
    session: Session,
    *,
    days: int = 30,
    start_date: date | None = None,
    end_date: date | None = None,
    force_refresh: bool = False,
) -> dict:
    """Assemble the called-bond cash/reinvestment review.

    The first external-table scan contains all selective predicates. Subsequent
    reads are restricted to only the affected accounts or BUY CUSIPs.
    """
    effective_end = end_date or date.today()
    effective_start = start_date or (effective_end - timedelta(days=days))
    if effective_start > effective_end:
        raise ValueError("Start date must be on or before end date.")
    if (effective_end - effective_start).days > 365:
        raise ValueError("Date range cannot exceed 365 days.")
    cache_key = (effective_start.isoformat(), effective_end.isoformat())

    if not force_refresh:
        with _called_report_cache_lock:
            cached = _called_report_cache.get(cache_key)
            if cached and time.monotonic() - cached[0] < CALLED_REPORT_CACHE_TTL_SECONDS:
                return cached[1]

    redemptions = _load_called_transactions(
        session, start_date=effective_start, end_date=effective_end
    )
    # Scope to the Bond Ladder Monitor's account universe (enrolled accounts only).
    ladder_accounts = get_bond_ladder_account_numbers(session)
    redemptions = [
        row for row in redemptions
        if str(row.get("account_number") or "").strip() in ladder_accounts
    ]
    accounts = sorted(
        {row["account_number"] for row in redemptions if row["account_number"]}
    )
    cash_by_account = _load_account_cash(session, accounts)
    redemption_match_values = sorted(
        {
            round(abs(float(value)), 2)
            for row in redemptions
            if (value := _transaction_match_value(row)) is not None
        }
    )
    buys = _load_recent_buys(
        session,
        accounts,
        start_date=effective_start,
        end_date=effective_end,
        match_values=redemption_match_values,
    )
    buy_cusips = sorted({str(row.get("cusip") or "").strip() for row in buys if row.get("cusip")})
    buy_symbols = sorted({str(row.get("symbol") or "").strip() for row in buys if row.get("symbol")})
    bond_cusips, bond_symbols = _load_bond_identifiers(
        session, buy_cusips, buy_symbols
    )

    rows: list[dict] = []
    for redemption in redemptions:
        account = redemption["account_number"]
        cash = cash_by_account.get(account, {})
        cash_value = float(cash.get("cash_value") or 0.0)
        cash_percent = float(cash.get("cash_percent") or 0.0)
        redeemed_amount = abs(redemption.get("amount") or 0.0)
        cash_flagged = (
            cash_percent > CASH_MINIMUM_PERCENT
            and redeemed_amount > 0
            and cash_value >= redeemed_amount
        )
        redemption_date = redemption.get("trade_date") or ""
        matching_buy = None
        if not cash_flagged:
            matching_buy = next(
                (
                    buy
                    for buy in buys
                    if buy["account_number"] == account
                    and (
                        (buy.get("cusip") or "") in bond_cusips
                        or (buy.get("symbol") or "") in bond_symbols
                    )
                    and _same_quantity(
                        _transaction_match_value(redemption),
                        _transaction_match_value(buy),
                    )
                    and (buy.get("trade_date") or "") >= redemption_date
                ),
                None,
            )
        row = {
            **redemption,
            "account_name": redemption.get("account_name")
            or str(cash.get("account_name") or ""),
            "account_value": round(float(cash.get("account_value") or 0.0), 2),
            "cash_value": round(cash_value, 2),
            "cash_percent": round(cash_percent, 2),
            "cash_flagged": cash_flagged,
            "matching_buy": matching_buy,
            "match_basis": (
                "quantity"
                if matching_buy
                and redemption.get("quantity") is not None
                and matching_buy.get("quantity") is not None
                else "amount" if matching_buy else None
            ),
            "highlight": "cash" if cash_flagged else "yellow" if matching_buy else None,
        }
        rows.append(row)

    report = {
        "days": (effective_end - effective_start).days,
        "start_date": effective_start.isoformat(),
        "end_date": effective_end.isoformat(),
        "as_of_date": date.today().isoformat(),
        "count": len(rows),
        "cash_flagged_count": sum(1 for row in rows if row["cash_flagged"]),
        "reinvested_count": sum(1 for row in rows if row["highlight"] == "yellow"),
        "unresolved_count": sum(1 for row in rows if row["highlight"] is None),
        "rows": rows,
        "cache_ttl_seconds": CALLED_REPORT_CACHE_TTL_SECONDS,
    }
    with _called_report_cache_lock:
        _called_report_cache[cache_key] = (time.monotonic(), report)
    return report
