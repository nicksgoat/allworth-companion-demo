"""Database-backed account analyzer.

Loads holdings by account number from ``tav.Account_Daily_Holdings``, enriches
them with ``[tav].[Security_Info]`` (when present), maps records to the
canonical :class:`app.models.bond.Bond`, and reuses the existing analytics and
summary engines.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from dateutil import parser as date_parser
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from investments.models.bond import Bond, CreditRating
from investments.services import ai_summary, analytics


# ---------------------------------------------------------------------------
# Simple in-memory TTL cache for account analysis results.
# Keyed by (account_number, as_of_date_str) so the cache is automatically
# invalidated whenever the holdings data moves to a new as-of date.
# TTL defaults to 5 minutes to avoid hammering Synapse on repeated loads.
# ---------------------------------------------------------------------------

_CACHE_TTL_SECONDS = 300  # 5 minutes

_cache: dict[tuple, tuple[float, "AccountAnalysisResult"]] = {}
_cache_lock = threading.Lock()

# Warehouse schemas change infrequently. Avoid an INFORMATION_SCHEMA round trip
# before every holdings/security query while still refreshing automatically.
_COLUMN_CACHE_TTL_SECONDS = 30 * 60
_column_cache: dict[tuple[str, str], tuple[float, frozenset[str]]] = {}
_column_cache_lock = threading.Lock()

_SECURITY_CACHE_TTL_SECONDS = 30 * 60
_security_cache: dict[tuple[str, tuple[str, ...], str], tuple[float, dict | None]] = {}
_security_cache_lock = threading.Lock()


def _cache_get(key: tuple) -> "AccountAnalysisResult | None":
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        ts, result = entry
        if time.monotonic() - ts > _CACHE_TTL_SECONDS:
            del _cache[key]
            return None
        return result


def _cache_set(key: tuple, result: "AccountAnalysisResult") -> None:
    with _cache_lock:
        _cache[key] = (time.monotonic(), result)


FIELD_REQUIREMENTS: dict = {
    "tav.Account_Daily_Holdings": {
        "required": ["Account_Number", "CUSIP", "Quantity", "Upload_Account_ID"],
        "recommended": [
            "Account_Name",
            "Symbol",
            "Security_Description",
            "Security_Type",
            "Asset_Class",
            "Subsector",
            "Holdings_Current_Value",
            "Market_Value",
            "Total_Account_Value",
            "Price",
            "Current_Price",
            "As_Of_Date",
            "Maturity_Date",
            "Accrued_Income",
            "Annual_Income",
            "Interest_Rate",
            "Total_Unrealized_Gain_Loss",
            "Cost_Basis",
            "Weight",
        ],
    },
    "tav.All_Custodian_Values": {
        "required": ["Upload_Account_ID", "Reinvestment_Instructions"],
        "recommended": ["Bond_Ladder", "Account_Number", "Account_Name"],
    },
    "tav.Security_Info": {
        "required": [
            "CUSIP",
            "Security_Description",
            "Security_Type",
            "Interest_Rate",
            "Maturity_Date",
            "Current_Yield_To_Worst_Market",
            "Effective_Duration",
        ],
        "recommended": [
            "Symbol",
            "Sector",
            "Issue_State",
            "Current_Price",
            "Issue_Date",
            "Call_Date",
            "Call_Price",
            "Income_Frequency",
            "Annual_Dividend",
            "Fitch_Bond_Rating",
            "Fitch_Bond_Rating_Previous_Value",
            "Fitch_Bond_Rating_Effective_Date",
            "Federal_Taxable",
            "State_Taxable",
        ],
    },
}


HOLDINGS_TABLE_CANDIDATES = [
    ("tav", "Account_Daily_Holdings"),
    ("tho", "Account_Daily_Holdings"),
]

SECURITY_TABLE_CANDIDATES = [
    ("tav", "Security_Info"),
]


HOLDINGS_COLUMN_CANDIDATES: dict[str, list[str]] = {
    "Account_Number": ["Account_Number", "Account Number"],
    "Account_Name": ["Account_Name", "Account Name"],
    "CUSIP": ["CUSIP"],
    "Symbol": ["Symbol"],
    "Upload_Account_ID": ["Upload_Account_ID", "avaccountuploadid"],
    "Security_Description": ["Security_Description", "Security Description"],
    "Security_Type": ["Security_Type", "Security Type"],
    "Asset_Class": ["Asset_Class", "Asset Class", "Primary_Asset_Class", "Primary Asset Class"],
    "Quantity": ["Quantity"],
    "Market_Value": ["Holdings_Current_Value", "Market_Value", "Market Value"],
    "Current_Price": ["Price", "Current_Price", "Current Price"],
    "As_Of_Date": ["As_Of_Date", "As Of Date"],
    "Maturity_Date": ["Maturity_Date", "Maturity Date", "Redemption_Date", "Redemption Date"],
    "Current_Yield": [
        "Yield_To_Maturity_Market", "Yield To Maturity Market",
        "Yield_To_Call_Market", "Yield To Call Market",
        "Current_Yield", "Current Yield",
    ],
    # Used to compute per-holding market value when Market_Value column is absent
    "Weight": ["Weight"],
    "Total_Account_Value": ["Total_Account_Value", "Total Account Value"],
    "Cost_Basis": ["Cost_Basis", "Cost Basis"],
    "Accrued_Income": ["Accrued_Income", "Accrued Income"],
    "Is_Deleted": ["isdeleted", "Is_Deleted", "Is Deleted"],
    # Used to filter to individual bonds only
    "Subsector": ["Subsector"],
    # Appraisal / gain-loss fields
    "Unrealized_Gain_Loss": [
        "Total_Unrealized_Gain_Loss", "Total Unrealized Gain/Loss",
        "Unrealized_Gain_Loss", "Unrealized Gain/Loss", "Unrealized Gain (Loss)",
        "UnrealizedGainLoss", "Unrealized_Gain", "Unrealized Gain",
    ],
    "Percent_Gain_Loss": [
        "Percent_Gain_Loss", "Percent Gain/Loss", "Percent Gain (Loss)",
        "Pct_Gain_Loss", "Unrealized_Gain_Loss_Pct", "Percent_Unrealized_Gain_Loss",
    ],
    "Open_Date": [
        "Open_Date", "Open Date", "Purchase_Date", "Purchase Date",
        "Acquire_Date", "Acquired_Date", "Date_Acquired",
    ],
    "Annual_Income": ["Annual_Income", "Annual Income", "Estimated_Annual_Income", "Estimated Annual Income"],
    "Annual_Income_Rate": [
        "Annual_Income_Rate", "Annual Income Rate", "Income_Rate", "Income Rate",
        "Interest_Rate", "Interest Rate", "Current_Yield", "Current Yield",
        "Yield_at_Cost", "Yield at Cost",
    ],
}


CUSTODIAN_TABLE_CANDIDATES = [
    ("tav", "All_Custodian_Values"),
]

CUSTODIAN_COLUMN_CANDIDATES: dict[str, list[str]] = {
    "Upload_Account_ID": ["Upload_Account_ID"],
    "Reinvestment_Instructions": ["Reinvestment_Instructions", "Reinvestment Instructions"],
}


SECURITY_COLUMN_CANDIDATES: dict[str, list[str]] = {
    "CUSIP": ["CUSIP"],
    "Symbol": ["Symbol"],
    "Security_Description": ["Security_Description", "Security Description"],
    "Security_Type": ["Security_Type", "Security Type"],
    "Issuer": ["Issuer", "Issuer_Name", "Issuer Name"],
    "Interest_Rate": ["Interest_Rate", "Interest Rate"],
    "Current_Price": ["Current_Price", "Current Price"],
    "Current_Yield_to_Worst": [
        "Current_Yield_to_Worst",
        "Current_Yield_To_Worst_Market",
        "Current Yield To Worst (Market)",
    ],
    "Effective_Duration": ["Effective_Duration", "Effective Duration"],
    # Annual Dividend is the available income field in this security master
    "Security_Annual_Income": ["Security_Annual_Income", "Security Annual Income", "Annual_Dividend", "Annual Dividend"],
    "Issue_Date": ["Issue_Date", "Issue Date"],
    "Maturity_Date": ["Maturity_Date", "Maturity Date"],
    "First_Coupon_Date": ["First_Coupon_Date", "First Coupon Date"],
    "Call_Date": ["Call_Date", "Call Date"],
    "Call_Price": ["Call_Price", "Call Price"],
    "Call_Put": ["Call_Put", "Call/Put"],
    "Income_Frequency": ["Income_Frequency", "Income Frequency"],
    "Next_Income_Date": ["Next_Income_Date", "Next Income Date"],
    "Sector": ["Sector"],
    "Broad_Sector": ["Broad_Sector", "Broad Sector"],
    "Segment": ["Segment"],
    "Issue_State": ["Issue_State", "Issue State"],
    "Federal_Taxable": ["Federal_Taxable", "Federal Taxable"],
    "State_Taxable": ["State_Taxable", "State Taxable"],
    # Fitch only — Moody's is not present in this security master
    "Fitch_Rating": ["Fitch_Bond_Rating", "Fitch Bond Rating", "Fitch_Rating", "Fitch Rating"],
    "Previous_Fitch_Rating": [
        "Fitch_Bond_Rating_Previous_Value",
        "Fitch Bond Rating Previous Value",
        "Previous_Fitch_Rating",
        "Previous Fitch Rating",
    ],
    "Fitch_Effective_Date": [
        "Fitch_Bond_Rating_Effective_Date",
        "Fitch Bond Rating Effective Date",
        "Fitch_Effective_Date",
        "Fitch Effective Date",
    ],
    "Previous_Fitch_Effective_Date": [
        "Fitch_Bond_Rating_Previous_Value_Effective_Date",
        "Fitch Bond Rating Previous Value Effective Date",
        "Previous_Fitch_Effective_Date",
    ],
}


@dataclass(frozen=True)
class TableSource:
    schema: str
    table: str
    columns: set[str]

    @property
    def ref(self) -> str:
        return f"[{self.schema}].[{self.table}]"


@dataclass
class AccountAnalysisResult:
    account_number: str
    account_name: str | None
    account_numbers: list[str]
    account_names: list[str]
    holdings_count: int
    enriched_count: int
    bonds: list[Bond]
    dashboard: dict
    summary: dict
    fields_required: dict


def analyze_account_number(session: Session, account_number: str) -> AccountAnalysisResult | None:
    return analyze_account_numbers(session, [account_number])


def analyze_account_numbers(session: Session, account_numbers: list[str]) -> AccountAnalysisResult | None:
    normalized_accounts = list(dict.fromkeys(str(a).strip() for a in account_numbers if str(a).strip()))
    if not normalized_accounts:
        return None
    # Fast path: avoid even the filtered holdings scan when this account set was
    # analyzed recently. The TTL bounds staleness and the slower as-of-date key
    # below still handles daily snapshot changes after this entry expires.
    request_cache_key = ("accounts", tuple(sorted(normalized_accounts)))
    cached_request = _cache_get(request_cache_key)
    if cached_request is not None:
        return cached_request

    holdings_source = _resolve_table_source(session, HOLDINGS_TABLE_CANDIDATES)
    holdings_columns = holdings_source.columns
    account_col = _first_existing_column(
        holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Account_Number"]
    )
    if not account_col:
        raise RuntimeError(
            f"Could not find an account number column in {holdings_source.ref}. "
            "Expected one of: Account_Number / Account Number."
        )

    holdings_select = _build_select_clause_aliased(HOLDINGS_COLUMN_CANDIDATES, holdings_columns, "h")
    custodian_join, reinvestment_filter = _custodian_join_and_reinvestment_filter(
        session,
        holdings_source,
        holdings_alias="h",
        custodian_alias="c",
    )

    # Filter to individual bonds only when the Subsector column is present
    subsector_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Subsector"])
    subsector_filter = f" AND h.[{subsector_col}] = 'Individual Bond'" if subsector_col else ""

    # Exclude zero-quantity holdings — these are stale/closed positions that
    # have not yet been purged from the warehouse (e.g. matured bonds, errors).
    quantity_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Quantity"])
    quantity_filter = f" AND ISNULL(h.[{quantity_col}], 0) <> 0" if quantity_col else ""

    holdings_stmt = (
        text(
            f"SELECT {holdings_select} "
            f"FROM {holdings_source.ref} AS h "
            f"{custodian_join} "
            f"WHERE h.[{account_col}] IN :account_numbers"
            f"{subsector_filter}{quantity_filter}{reinvestment_filter}"
        )
        .bindparams(bindparam("account_numbers", expanding=True))
    )
    holdings = session.execute(holdings_stmt, {"account_numbers": normalized_accounts}).mappings().all()
    if not holdings:
        return None

    # Use the as-of date from the first holding row as part of the cache key so
    # results are automatically invalidated when the data moves to a new date.
    as_of_raw = holdings[0].get("As_Of_Date")
    as_of_str = str(as_of_raw.date() if hasattr(as_of_raw, "date") else as_of_raw or "")
    cache_key = (tuple(normalized_accounts), as_of_str)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    cusips = sorted({str(h.get("CUSIP") or "").strip() for h in holdings if h.get("CUSIP")})

    security_by_cusip = _load_security_by_cusip(session, cusips)

    bonds: list[Bond] = []
    enriched = 0
    for holding in holdings:
        holding_dict = dict(holding)
        security = security_by_cusip.get(str(holding_dict.get("CUSIP") or "").strip())
        if security is not None:
            enriched += 1
        bond = _to_bond(holding_dict, security)
        # Warehouse snapshots sometimes retain matured positions with non-zero
        # quantity in combined-account pulls. Keep only current/future bonds.
        if bond.maturity_date and bond.maturity_date < date.today():
            continue
        bonds.append(bond)

    total_bond_mv = sum(b.effective_market_value() for b in bonds)
    if total_bond_mv > 0:
        for bond in bonds:
            bond.weight = round(bond.effective_market_value() / total_bond_mv * 100.0, 4)

    dashboard = analytics.build_dashboard(bonds)
    summary = ai_summary.generate_summary(bonds)
    present_account_numbers = list(
        dict.fromkeys(str(h.get("Account_Number") or "").strip() for h in holdings if h.get("Account_Number"))
    )
    present_account_names = list(
        dict.fromkeys(str(h.get("Account_Name") or "").strip() for h in holdings if h.get("Account_Name"))
    )

    result = AccountAnalysisResult(
        account_number=", ".join(present_account_numbers) if len(present_account_numbers) > 1 else present_account_numbers[0],
        account_name=(present_account_names[0] if len(present_account_names) == 1 else None),
        account_numbers=present_account_numbers,
        account_names=present_account_names,
        holdings_count=len(bonds),
        enriched_count=enriched,
        bonds=bonds,
        dashboard=dashboard,
        summary=summary,
        fields_required=FIELD_REQUIREMENTS,
    )
    _cache_set(cache_key, result)
    _cache_set(request_cache_key, result)
    return result


def _compute_market_value(holding: dict) -> float | None:
    """Return per-holding market value.

    Priority:
    1. Direct Market_Value column (if the table has one).
    2. Total_Account_Value — in tho.Account_Daily_Holdings each row stores the
       holding's own market value in this column (not the account total).
    3. Fall back to None so Bond.effective_market_value() can attempt
       price × quantity / 100 as a last resort.
    """
    direct = _to_float(holding.get("Market_Value"))
    if direct is not None:
        return direct
    total = _to_float(holding.get("Total_Account_Value"))
    if total is not None:
        return total
    return None


def _first_float(*values) -> float | None:
    for value in values:
        converted = _to_float(value)
        if converted is not None:
            return converted
    return None


def _first_date(*values) -> date | None:
    for value in values:
        converted = _to_date(value)
        if converted is not None:
            return converted
    return None


def _to_bond(
    holding: dict,
    security: dict | None,
) -> Bond:
    ratings: list[CreditRating] = []
    if security and security.get("Fitch_Rating"):
        ratings.append(
            CreditRating(
                agency="Fitch",
                current=security.get("Fitch_Rating"),
                previous=security.get("Previous_Fitch_Rating"),
                effective_date=_to_date(security.get("Fitch_Effective_Date")),
                previous_effective_date=_to_date(security.get("Previous_Fitch_Effective_Date")),
            )
        )

    call_date = _first_date(security.get("Call_Date") if security else None)

    return Bond(
        symbol=holding.get("Symbol") or (security.get("Symbol") if security else None),
        cusip=holding.get("CUSIP"),
        description=(
            holding.get("Security_Description")
            or (security.get("Security_Description") if security else None)
            or "Unknown Security"
        ),
        account_id=holding.get("Account_Number"),
        account_name=holding.get("Account_Name"),
        coupon=_first_float(holding.get("Annual_Income_Rate"), security.get("Interest_Rate") if security else None),
        price=_first_float(holding.get("Current_Price"), security.get("Current_Price") if security else None),
        quantity=_to_float(holding.get("Quantity")),
        market_value=_compute_market_value(holding),
        weight=_to_float(holding.get("Weight")),
        annual_income=_first_float(holding.get("Annual_Income"), security.get("Security_Annual_Income") if security else None),
        yield_to_worst=_first_float(holding.get("Current_Yield"), security.get("Current_Yield_to_Worst") if security else None),
        effective_duration=_first_float(holding.get("Effective_Duration"), security.get("Effective_Duration") if security else None),
        issue_date=_first_date(security.get("Issue_Date") if security else None),
        maturity_date=_first_date(holding.get("Maturity_Date"), security.get("Maturity_Date") if security else None),
        call_date=call_date,
        # callable when a call date is set OR security master flags it as a call option
        callable=call_date is not None or str((security or {}).get("Call_Put") or "").strip().upper() == "CALL",
        call_price=_to_float(security.get("Call_Price") if security else None),
        ratings=ratings,
        asset_class="Fixed Income",
        sector=(security.get("Sector") if security else None) or holding.get("Sector"),
        issuer=security.get("Issuer") if security else None,
        state=security.get("Issue_State") if security else None,
        income_frequency=security.get("Income_Frequency") if security else None,
        next_income_date=_to_date(security.get("Next_Income_Date") if security else None),
        federal_taxable=_to_bool(security.get("Federal_Taxable") if security else None),
        state_taxable=_to_bool(security.get("State_Taxable") if security else None),
    )


def _to_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        negative = stripped.startswith("(") and stripped.endswith(")")
        cleaned = stripped.strip("()").replace(",", "").replace("$", "").replace("%", "")
        if cleaned.lower() in {"none", "null", "n/a", "na", "-"}:
            return None
        try:
            parsed = float(cleaned)
        except ValueError:
            return None
        return -parsed if negative else parsed
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Years used as placeholder / sentinel values in security masters.
# Any date whose year is >= this threshold is treated as "unknown" and
# returned as None so it doesn't pollute maturity-date calculations or display.
_SENTINEL_YEAR_THRESHOLD = 2098


def _to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        d = value.date()
        return None if d.year >= _SENTINEL_YEAR_THRESHOLD else d
    if isinstance(value, date):
        return None if value.year >= _SENTINEL_YEAR_THRESHOLD else value
    if isinstance(value, str) and not value.strip():
        return None
    try:
        d = date_parser.parse(str(value), fuzzy=True).date()
        return None if d.year >= _SENTINEL_YEAR_THRESHOLD else d
    except (ValueError, OverflowError, TypeError):
        return None


def _to_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text_value = str(value).strip().lower()
    if text_value in {"", "none", "null", "n/a", "na", "-"}:
        return None
    if text_value in {"1", "true", "yes", "y", "taxable"}:
        return True
    if text_value in {"0", "false", "no", "n", "exempt", "tax exempt", "tax-exempt"}:
        return False
    return None


def _get_table_columns(session: Session, *, schema: str, table: str) -> set[str]:
    key = (schema.lower(), table.lower())
    with _column_cache_lock:
        cached = _column_cache.get(key)
        if cached and time.monotonic() - cached[0] < _COLUMN_CACHE_TTL_SECONDS:
            return set(cached[1])

    stmt = text(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :table"
    )
    rows = session.execute(stmt, {"schema": schema, "table": table}).fetchall()
    columns = {str(row[0]) for row in rows}
    with _column_cache_lock:
        _column_cache[key] = (time.monotonic(), frozenset(columns))
    return columns


def _resolve_table_source(session: Session, candidates: list[tuple[str, str]]) -> TableSource:
    checked: list[str] = []
    for schema, table in candidates:
        columns = _get_table_columns(session, schema=schema, table=table)
        checked.append(f"{schema}.{table}")
        if columns:
            return TableSource(schema=schema, table=table, columns=columns)
    raise RuntimeError(f"Could not find any configured source table. Checked: {', '.join(checked)}.")


def _load_security_by_cusip(session: Session, cusips: list[str]) -> dict[str, dict]:
    normalized = list(dict.fromkeys(str(cusip).strip() for cusip in cusips if str(cusip).strip()))
    if not normalized:
        return {}

    try:
        security_source = _resolve_table_source(session, SECURITY_TABLE_CANDIDATES)
    except RuntimeError:
        return {}

    security_cusip_col = _first_existing_column(
        security_source.columns, SECURITY_COLUMN_CANDIDATES["CUSIP"]
    )
    if not security_cusip_col:
        return {}

    source_signature = (
        security_source.ref,
        tuple(sorted(security_source.columns)),
    )
    now = time.monotonic()
    result: dict[str, dict] = {}
    missing: list[str] = []
    with _security_cache_lock:
        for cusip in normalized:
            cache_key = (*source_signature, cusip)
            cached = _security_cache.get(cache_key)
            if cached and now - cached[0] < _SECURITY_CACHE_TTL_SECONDS:
                if cached[1] is not None:
                    result[cusip] = cached[1]
            else:
                missing.append(cusip)
    if not missing:
        return result

    security_select = _build_select_clause(SECURITY_COLUMN_CANDIDATES, security_source.columns)
    security_stmt = (
        text(
            f"SELECT {security_select} "
            f"FROM {security_source.ref} "
            f"WHERE [{security_cusip_col}] IN :cusips"
        )
        .bindparams(bindparam("cusips", expanding=True))
    )
    security_rows = session.execute(security_stmt, {"cusips": missing}).mappings().all()
    fetched = {
        str(row.get("CUSIP") or "").strip(): dict(row)
        for row in security_rows
        if row.get("CUSIP")
    }
    fetched_at = time.monotonic()
    with _security_cache_lock:
        for cusip in missing:
            cache_key = (*source_signature, cusip)
            _security_cache[cache_key] = (fetched_at, fetched.get(cusip))
    result.update(fetched)
    return result


def _first_existing_column(available: set[str], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def _build_select_clause_aliased(candidates_map: dict[str, list[str]], available: set[str], table_alias: str) -> str:
    selections: list[str] = []
    for alias, candidates in candidates_map.items():
        source = _first_existing_column(available, candidates)
        if source:
            selections.append(f"[{table_alias}].[{source}] AS [{alias}]")
        else:
            selections.append(f"NULL AS [{alias}]")
    return ", ".join(selections)


def _build_select_clause(candidates_map: dict[str, list[str]], available: set[str]) -> str:
    selections: list[str] = []
    for alias, candidates in candidates_map.items():
        source = _first_existing_column(available, candidates)
        if source:
            selections.append(f"[{source}] AS [{alias}]")
        else:
            selections.append(f"NULL AS [{alias}]")
    return ", ".join(selections)


def _custodian_join_and_reinvestment_filter(
    session: Session,
    holdings_source: TableSource,
    *,
    holdings_alias: str = "h",
    custodian_alias: str = "c",
    reinvest_only: bool = False,
) -> tuple[str, str]:
    """Join tav.All_Custodian_Values and filter on reinvestment instructions.

    By default (``reinvest_only=False``) accounts with a blank/``NULL`` or
    ``Reinvest`` instruction are kept — this preserves account-lookup behaviour
    where a specific account should still resolve even when the custodian value
    is missing.

    When ``reinvest_only=True`` (used by the Bond Ladder monitor) only accounts
    explicitly flagged ``Reinvest`` are kept, so 'do not reinvest' and
    blank/unenrolled accounts are excluded from maturity reporting.
    """
    holdings_upload_col = _first_existing_column(
        holdings_source.columns,
        HOLDINGS_COLUMN_CANDIDATES["Upload_Account_ID"],
    )
    if not holdings_upload_col:
        raise RuntimeError(f"Could not find Upload_Account_ID column in {holdings_source.ref}.")

    custodian_source = _resolve_table_source(session, CUSTODIAN_TABLE_CANDIDATES)
    custodian_upload_col = _first_existing_column(
        custodian_source.columns,
        CUSTODIAN_COLUMN_CANDIDATES["Upload_Account_ID"],
    )
    reinvestment_col = _first_existing_column(
        custodian_source.columns,
        CUSTODIAN_COLUMN_CANDIDATES["Reinvestment_Instructions"],
    )
    if not custodian_upload_col:
        raise RuntimeError(f"Could not find Upload_Account_ID column in {custodian_source.ref}.")
    if not reinvestment_col:
        raise RuntimeError(f"Could not find Reinvestment_Instructions column in {custodian_source.ref}.")

    join_sql = (
        f"JOIN {custodian_source.ref} AS {custodian_alias} "
        f"ON {holdings_alias}.[{holdings_upload_col}] = {custodian_alias}.[{custodian_upload_col}]"
    )
    if reinvest_only:
        filter_sql = (
            f" AND UPPER(LTRIM(RTRIM(CAST({custodian_alias}.[{reinvestment_col}] AS NVARCHAR(255))))) = 'REINVEST'"
        )
    else:
        filter_sql = (
            f" AND ({custodian_alias}.[{reinvestment_col}] IS NULL "
            f"OR UPPER(LTRIM(RTRIM(CAST({custodian_alias}.[{reinvestment_col}] AS NVARCHAR(255))))) = 'REINVEST')"
        )
    return join_sql, filter_sql


# ---------------------------------------------------------------------------
# Appraisal holdings — flat rows with all columns for the Holdings page
# ---------------------------------------------------------------------------

@dataclass
class AppraisalResult:
    account_number: str
    account_name: str | None
    account_numbers: list[str]
    account_names: list[str]
    as_of_date: str | None
    rows: list[dict]


def get_appraisal_holdings(session: Session, account_numbers: list[str]) -> AppraisalResult | None:
    """Return flat appraisal rows (one per holding) for the given account numbers.

    Includes appraisal columns (weight, unrealized gain/loss, open date, annual
    income rate) sourced from the warehouse, falling back to NULL when absent.
    """
    normalized = list(dict.fromkeys(str(a).strip() for a in account_numbers if str(a).strip()))
    if not normalized:
        return None

    holdings_source = _resolve_table_source(session, HOLDINGS_TABLE_CANDIDATES)
    holdings_columns = holdings_source.columns
    account_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Account_Number"])
    if not account_col:
        raise RuntimeError(
            f"Could not find an account number column in {holdings_source.ref}."
        )

    holdings_select = _build_select_clause_aliased(HOLDINGS_COLUMN_CANDIDATES, holdings_columns, "h")
    custodian_join, reinvestment_filter = _custodian_join_and_reinvestment_filter(
        session,
        holdings_source,
        holdings_alias="h",
        custodian_alias="c",
    )
    deleted_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Is_Deleted"])
    deleted_filter = f" AND ISNULL(h.[{deleted_col}], 0) = 0" if deleted_col else ""
    quantity_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Quantity"])
    # Drop only rows that are truly empty (no quantity AND no value). Cash sweep
    # balances and some money-market funds carry their value in a value column
    # with a NULL quantity, so a bare ``Quantity <> 0`` filter would silently
    # omit valid cash from the appraisal.
    value_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Market_Value"])
    total_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Total_Account_Value"])
    presence_terms: list[str] = []
    if quantity_col:
        presence_terms.append(f"ISNULL(h.[{quantity_col}], 0) <> 0")
    if value_col:
        presence_terms.append(f"ISNULL(h.[{value_col}], 0) <> 0")
    if total_col:
        presence_terms.append(f"ISNULL(h.[{total_col}], 0) <> 0")
    quantity_filter = f" AND ({' OR '.join(presence_terms)})" if presence_terms else ""

    holdings_stmt = (
        text(
            f"SELECT {holdings_select} "
            f"FROM {holdings_source.ref} AS h "
            f"{custodian_join} "
            f"WHERE h.[{account_col}] IN :account_numbers{deleted_filter}{quantity_filter}{reinvestment_filter}"
        )
        .bindparams(bindparam("account_numbers", expanding=True))
    )
    holdings = session.execute(holdings_stmt, {"account_numbers": normalized}).mappings().all()
    if not holdings:
        return None

    cusips = sorted({str(h.get("CUSIP") or "").strip() for h in holdings if h.get("CUSIP")})
    security_by_cusip = _load_security_by_cusip(session, cusips)

    # Drop matured bonds that linger in warehouse snapshots (especially in
    # combined-account pulls). Only dated maturities in the past are dropped —
    # cash and equities have no maturity date and are always retained.
    today = date.today()
    kept_holdings: list[dict] = []
    for holding in holdings:
        h = dict(holding)
        sec = security_by_cusip.get(str(h.get("CUSIP") or "").strip())
        maturity = _first_date(h.get("Maturity_Date"), sec.get("Maturity_Date") if sec else None)
        if maturity and maturity < today:
            continue
        kept_holdings.append(h)
    if not kept_holdings:
        return None
    holdings = kept_holdings

    # Compute total market value for weight calculation
    total_mv = sum(
        (_to_float(h.get("Market_Value")) or _to_float(h.get("Total_Account_Value")) or 0.0)
        for h in holdings
    )

    rows: list[dict] = []
    for h in holdings:
        h = dict(h)
        sec = security_by_cusip.get(str(h.get("CUSIP") or "").strip())
        mv = _to_float(h.get("Market_Value")) or _to_float(h.get("Total_Account_Value"))
        cost_basis = _to_float(h.get("Cost_Basis"))
        unrealized_gain_loss = _to_float(h.get("Unrealized_Gain_Loss"))
        percent_gain_loss = _to_float(h.get("Percent_Gain_Loss"))
        if percent_gain_loss is None and unrealized_gain_loss is not None and cost_basis:
            percent_gain_loss = unrealized_gain_loss / cost_basis * 100.0
        weight = round(mv / total_mv * 100.0, 4) if (mv is not None and total_mv > 0) else None
        maturity = _first_date(h.get("Maturity_Date"), sec.get("Maturity_Date") if sec else None)
        call_dt = _first_date(sec.get("Call_Date") if sec else None)
        open_dt = _to_date(h.get("Open_Date"))
        interest_rate = (
            _to_float(h.get("Annual_Income_Rate"))
            if h.get("Annual_Income_Rate") is not None
            else _to_float(sec.get("Interest_Rate") if sec else None)
        )
        holding_annual_income = _to_float(h.get("Annual_Income"))
        sec_annual_income = _to_float(sec.get("Security_Annual_Income") if sec else None)
        quantity = _to_float(h.get("Quantity"))
        annual_income = (
            holding_annual_income
            if holding_annual_income is not None
            else sec_annual_income
            if sec_annual_income is not None
            else (interest_rate / 100.0 * quantity if interest_rate is not None and quantity is not None else None)
        )
        rows.append({
            "account_number": h.get("Account_Number") or "",
            "account_name": h.get("Account_Name") or "",
            "asset_class": h.get("Asset_Class") or h.get("Security_Type") or "",
            "subsector": h.get("Subsector") or "",
            "security_type": h.get("Security_Type") or "",
            "cusip": h.get("CUSIP") or "",
            "symbol": h.get("Symbol") or (sec.get("Symbol") if sec else None) or "",
            "description": (
                h.get("Security_Description")
                or (sec.get("Security_Description") if sec else None)
                or ""
            ),
            "redemption_date": maturity.isoformat() if maturity else None,
            "quantity": quantity,
            "price": _first_float(h.get("Current_Price"), sec.get("Current_Price") if sec else None),
            "market_value": mv,
            "weight": weight,
            "call_date": call_dt.isoformat() if call_dt else None,
            "unrealized_gain_loss": unrealized_gain_loss,
            "percent_gain_loss": percent_gain_loss,
            "annual_income": annual_income,
            "annual_income_rate": interest_rate,
            "accrued_income": _to_float(h.get("Accrued_Income")),
            "open_date": open_dt.isoformat() if open_dt else None,
        })

    present_account_numbers = list(
        dict.fromkeys(str(h.get("Account_Number") or "") for h in [dict(h) for h in holdings] if h.get("Account_Number"))
    )
    present_account_names = list(
        dict.fromkeys(str(h.get("Account_Name") or "") for h in [dict(h) for h in holdings] if h.get("Account_Name"))
    )
    as_of_raw = dict(holdings[0]).get("As_Of_Date")
    as_of_str = str(as_of_raw.date() if hasattr(as_of_raw, "date") else as_of_raw or "")

    return AppraisalResult(
        account_number=(
            ", ".join(present_account_numbers)
            if len(present_account_numbers) > 1
            else (present_account_numbers[0] if present_account_numbers else normalized[0])
        ),
        account_name=present_account_names[0] if len(present_account_names) == 1 else None,
        account_numbers=present_account_numbers,
        account_names=present_account_names,
        as_of_date=as_of_str or None,
        rows=rows,
    )
