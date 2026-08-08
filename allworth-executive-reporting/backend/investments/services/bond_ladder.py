"""Bond Ladder portfolio service.

Loads all accounts where the demographic field ``Bond_Ladder = 'Yes'``
from tho.Account_Daily_Holdings (via tho.Current_Account_Demographic),
enriches with tav.Security_Info, and returns a structured
summary ready for the API layer.

Results are cached in-process for CACHE_TTL_SECONDS to avoid hitting the
database on every page visit (data changes at most once per day).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from dateutil import parser as date_parser
from sqlalchemy import text
from sqlalchemy.orm import Session

from investments.models.bond import Bond, CreditRating
from investments.models.bond import rating_rank
from investments.services.db_analyzer import (
    HOLDINGS_COLUMN_CANDIDATES,
    TableSource,
    _custodian_join_and_reinvestment_filter,
    _first_existing_column,
    _get_table_columns,
    _load_security_by_cusip,
    _to_bool,
    _to_date,
    _to_float,
    _compute_market_value,
    _to_bond,
)

BOND_LADDER_COLUMN_CANDIDATES = ["Bond_Ladder", "Bond Ladder", "BondLadder"]
BOND_LADDER_TRUE_VALUES = ("1", "Y", "YES", "TRUE", "T", "X", "CHECK", "CHECKED", "✓", "✔")
STRATEGY_COLUMN_CANDIDATES = ["Rebalancing_Model_Name", "Rebalancing Model Name", "Strategy", "Model_Name"]


# ── In-process cache ──────────────────────────────────────────────────────────
# Holdings are uploaded once a day; 30 minutes is a safe TTL that keeps the
# data fresh without hammering the warehouse on every page visit.
CACHE_TTL_SECONDS = 30 * 60

@dataclass
class _CacheEntry:
    result: "BondLadderResult"
    fetched_at: float  # time.monotonic() timestamp
    fetched_wall: datetime  # wall-clock time (returned to the client)

_cache_lock = threading.Lock()
_cache: _CacheEntry | None = None


def invalidate_cache() -> None:
    """Force the next call to re-query the database."""
    global _cache
    with _cache_lock:
        _cache = None


def cache_age_seconds() -> float | None:
    """Return how old the cached result is, or None if no cache."""
    with _cache_lock:
        if _cache is None:
            return None
        return time.monotonic() - _cache.fetched_at


def cache_fetched_at() -> datetime | None:
    with _cache_lock:
        return _cache.fetched_wall if _cache else None


@dataclass
class BondLadderAccount:
    account_number: str
    account_name: str | None
    strategy: str  # e.g. "AWF - Bond Ladder Municipal 1-10 year"
    bonds: list[Bond]

    @property
    def total_market_value(self) -> float:
        return sum(b.effective_market_value() for b in self.bonds)

    @property
    def bond_count(self) -> int:
        return len(self.bonds)


@dataclass
class BondLadderResult:
    accounts: list[BondLadderAccount]
    strategies: list[str]  # distinct strategy names present

    @property
    def total_accounts(self) -> int:
        return len(self.accounts)

    @property
    def total_bonds(self) -> int:
        return sum(a.bond_count for a in self.accounts)

    @property
    def total_market_value(self) -> float:
        return sum(a.total_market_value for a in self.accounts)

    def all_bonds(self, *, strategy: str | None = None, sort_by: str = "maturity") -> list[dict]:
        """Return flat list of bond dicts optionally filtered by strategy, sorted by date field.

        sort_by: 'maturity' | 'call_date'
        """
        rows: list[dict] = []
        for acct in self.accounts:
            if strategy and acct.strategy != strategy:
                continue
            for bond in acct.bonds:
                fitch = next((r for r in bond.ratings if r.agency == "Fitch"), None)
                # Downgrade: current rank is numerically higher (worse) than previous
                fitch_rank_current = rating_rank(fitch.current) if fitch else None
                fitch_rank_previous = rating_rank(fitch.previous) if fitch else None
                is_downgraded = (
                    fitch_rank_current is not None
                    and fitch_rank_previous is not None
                    and fitch_rank_current > fitch_rank_previous
                )
                rows.append({
                    "account_number": acct.account_number,
                    "account_name": acct.account_name or "",
                    "strategy": acct.strategy,
                    "symbol": bond.symbol or "",
                    "cusip": bond.cusip or "",
                    "description": bond.description or "",
                    "issuer": bond.issuer or "",
                    "sector": bond.sector or "",
                    "state": bond.state or "",
                    "quantity": bond.quantity or 0.0,
                    "price": bond.price or 0.0,
                    "market_value": bond.effective_market_value(),
                    "coupon": bond.coupon or 0.0,
                    "yield_to_worst": bond.yield_to_worst or 0.0,
                    "effective_duration": bond.effective_duration or 0.0,
                    "maturity_date": bond.maturity_date.isoformat() if bond.maturity_date else None,
                    "call_date": bond.call_date.isoformat() if bond.call_date else None,
                    "callable": bond.callable,
                    "fitch_rating": fitch.current if fitch else None,
                    "fitch_rating_previous": fitch.previous if fitch else None,
                    "fitch_rating_effective_date": fitch.effective_date.isoformat() if fitch and fitch.effective_date else None,
                    "fitch_rating_previous_effective_date": fitch.previous_effective_date.isoformat() if fitch and fitch.previous_effective_date else None,
                    "is_downgraded": is_downgraded,
                    "annual_income": bond.effective_annual_income(),
                })

        # Sort
        if sort_by == "call_date":
            rows.sort(key=lambda r: r["call_date"] or "9999-12-31")
        else:
            rows.sort(key=lambda r: r["maturity_date"] or "9999-12-31")
        return rows


def _build_select_clause_aliased(candidates_map: dict[str, list[str]], available: set[str], table_alias: str = "h") -> str:
    """Like _build_select_clause but prefixes each column reference with a table alias."""
    selections: list[str] = []
    for alias, candidates in candidates_map.items():
        source = _first_existing_column(available, candidates)
        if source:
            selections.append(f"[{table_alias}].[{source}] AS [{alias}]")
        else:
            selections.append(f"NULL AS [{alias}]")
    return ", ".join(selections)


def _truthy_checkbox_filter(table_alias: str, column: str) -> str:
    values = ", ".join(f"'{value}'" for value in BOND_LADDER_TRUE_VALUES)
    return f"UPPER(LTRIM(RTRIM(CAST([{table_alias}].[{column}] AS NVARCHAR(255))))) IN ({values})"


def get_bond_ladder_account_numbers(session: Session) -> set[str]:
    """Account numbers enrolled in the Bond Ladder (the monitor's account universe).

    Uses the same enrollment source of truth as the monitor —
    ``tho.Current_Account_Demographic.Bond_Ladder`` — so other surfaces can be
    scoped to exactly the accounts the Bond Ladder Monitor covers.
    """
    demographic_columns = _get_table_columns(session, schema="tho", table="Current_Account_Demographic")
    account_col = _first_existing_column(demographic_columns, HOLDINGS_COLUMN_CANDIDATES["Account_Number"])
    bond_ladder_col = _first_existing_column(demographic_columns, BOND_LADDER_COLUMN_CANDIDATES)
    if not account_col or not bond_ladder_col:
        raise RuntimeError(
            "Could not resolve Account_Number/Bond_Ladder in tho.Current_Account_Demographic."
        )
    stmt = text(
        f"SELECT DISTINCT d.[{account_col}] AS acct "
        f"FROM [tho].[Current_Account_Demographic] d "
        f"WHERE {_truthy_checkbox_filter('d', bond_ladder_col)}"
    )
    rows = session.execute(stmt).mappings().all()
    return {str(r.get("acct")).strip() for r in rows if r.get("acct")}


def get_bond_ladder(session: Session) -> "BondLadderResult":
    """Return Bond Ladder result, serving from cache when still fresh."""
    global _cache
    with _cache_lock:
        if _cache is not None and (time.monotonic() - _cache.fetched_at) < CACHE_TTL_SECONDS:
            return _cache.result

    result = _fetch_bond_ladder(session)

    with _cache_lock:
        _cache = _CacheEntry(
            result=result,
            fetched_at=time.monotonic(),
            fetched_wall=datetime.utcnow(),
        )
    return result


def _fetch_bond_ladder(session: Session) -> "BondLadderResult":
    """Load all Bond Ladder accounts and their Individual Bond holdings."""
    holdings_columns = _get_table_columns(session, schema="tho", table="Account_Daily_Holdings")
    demographic_columns = _get_table_columns(session, schema="tho", table="Current_Account_Demographic")
    account_col = _first_existing_column(holdings_columns, HOLDINGS_COLUMN_CANDIDATES["Account_Number"])
    if not account_col:
        raise RuntimeError("Could not find Account_Number column in tho.Account_Daily_Holdings.")
    bond_ladder_col = _first_existing_column(demographic_columns, BOND_LADDER_COLUMN_CANDIDATES)
    if not bond_ladder_col:
        raise RuntimeError("Could not find Bond_Ladder column in tho.Current_Account_Demographic.")
    strategy_col = _first_existing_column(demographic_columns, STRATEGY_COLUMN_CANDIDATES)
    strategy_select = f"d.[{strategy_col}] AS [Strategy]" if strategy_col else "NULL AS [Strategy]"

    holdings_select = _build_select_clause_aliased(HOLDINGS_COLUMN_CANDIDATES, holdings_columns, "h")
    bond_ladder_filter = _truthy_checkbox_filter("d", bond_ladder_col)
    holdings_source = TableSource(schema="tho", table="Account_Daily_Holdings", columns=holdings_columns)
    custodian_join, reinvestment_filter = _custodian_join_and_reinvestment_filter(
        session,
        holdings_source,
        holdings_alias="h",
        custodian_alias="c",
        reinvest_only=True,
    )

    # Pull all Individual Bond rows for Bond Ladder accounts in one query,
    # joining to Current_Account_Demographic and using Bond_Ladder as the
    # enrollment source of truth.
    stmt = text(f"""
        SELECT {holdings_select},
               {strategy_select},
               d.[Account_Name] AS [Demo_Account_Name]
        FROM [tho].[Account_Daily_Holdings] h
        JOIN [tho].[Current_Account_Demographic] d
          ON h.[avaccountuploadid] = d.[Upload_Account_ID]
        {custodian_join}
        WHERE {bond_ladder_filter}
          AND h.[Total_Account_Value] > 0
          AND h.[Subsector] = 'Individual Bond'
          {reinvestment_filter}
        ORDER BY h.[Account_Number], h.[CUSIP]
    """)
    holdings = session.execute(stmt).mappings().all()

    if not holdings:
        return BondLadderResult(accounts=[], strategies=[])

    # Gather all CUSIPs for a single enrichment batch
    cusips = sorted({str(h.get("CUSIP") or "").strip() for h in holdings if h.get("CUSIP")})

    # Enrich from the shared security cache. Loading the Bond Ladder primes
    # account-detail requests for the same securities.
    security_by_cusip = _load_security_by_cusip(session, cusips)

    # Group into accounts
    accounts_map: dict[str, BondLadderAccount] = {}
    for holding in holdings:
        h = dict(holding)
        acct_num = str(h.get("Account_Number") or "").strip()
        raw_strategy = str(h.get("Strategy") or "").strip()
        strategy = raw_strategy if raw_strategy.upper() not in BOND_LADDER_TRUE_VALUES else "Bond Ladder"
        strategy = strategy or "Bond Ladder"
        acct_name = (h.get("Demo_Account_Name") or h.get("Account_Name") or "").strip() or None

        if acct_num not in accounts_map:
            accounts_map[acct_num] = BondLadderAccount(
                account_number=acct_num,
                account_name=acct_name,
                strategy=strategy,
                bonds=[],
            )
        security = security_by_cusip.get(str(h.get("CUSIP") or "").strip())
        accounts_map[acct_num].bonds.append(_to_bond(h, security))

    accounts = sorted(accounts_map.values(), key=lambda a: a.account_number)
    strategies = sorted({a.strategy for a in accounts})

    return BondLadderResult(accounts=accounts, strategies=strategies)
