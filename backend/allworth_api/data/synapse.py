"""Synapse data warehouse client — scoped to a single household.

All queries are parameterized and scoped by household_id (AVHHID) to enforce
data isolation. Falls back to local seed data when Synapse is unavailable.

Schema mirrors the production analytics plugin:
  - [tho].Current_Household_Fact      → household lookup (AVHHID, LeadId)
  - [tho].Current_Household_Demographic → household name, demographics
  - [tho].Contact_Demographic          → household members (DOB, role)
  - [tho].Account_Daily_Holdings       → account balances by avhhid
  - [tav].All_Custodian_Values         → account metadata (name, type, category)
  - [tho].Household_Rollforward        → cash flows, distributions, expenses
"""

from __future__ import annotations

import logging
import os
import struct
import sys
import threading
import time
from contextlib import suppress
from typing import Any

import pyodbc

from allworth_api import config as _config  # noqa: F401  (loads .env)

logger = logging.getLogger(__name__)

_SERVER = os.environ.get("SYNAPSE_SERVER", "")
_DATABASE = os.environ.get("SYNAPSE_DATABASE", "DataWarehouse")
_DRIVER = os.environ.get("SYNAPSE_DRIVER", "ODBC Driver 18 for SQL Server")
_USERNAME = os.environ.get("SYNAPSE_USERNAME", "")
_PASSWORD = os.environ.get("SYNAPSE_PASSWORD", "")
_AUTH_MODE = os.environ.get("SYNAPSE_AUTH_MODE", "entra")

# ── Token + connection caching ────────────────────────────────────────────

_token_cache: dict[str, Any] = {"struct": None, "expires_at": 0.0}
_token_lock = threading.Lock()

_conn_local = threading.local()  # thread-local persistent connection


def _get_access_token() -> bytes:
    """Get an Azure AD token, cached until near expiry (~5 min buffer)."""
    with _token_lock:
        if _token_cache["struct"] and time.time() < _token_cache["expires_at"] - 300:
            return _token_cache["struct"]

        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential()
        token = credential.get_token("https://database.windows.net/.default")
        token_bytes = token.token.encode("UTF-16-LE")
        token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)
        _token_cache["struct"] = token_struct
        _token_cache["expires_at"] = token.expires_on
        logger.info(f"[synapse] acquired new Entra token, expires in {int(token.expires_on - time.time())}s")
        return token_struct


def _get_connection_string() -> str:
    """Build ODBC connection string for Synapse (without auth for token mode)."""
    base = (
        f"DRIVER={{{_DRIVER}}};"
        f"SERVER={_SERVER};"
        f"DATABASE={_DATABASE};"
    )
    if _AUTH_MODE == "service_principal":
        base += (
            "Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={os.environ.get('AZURE_CLIENT_ID', '')};"
            f"PWD={os.environ.get('AZURE_CLIENT_SECRET', '')};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )
    elif _AUTH_MODE == "entra":
        # Token-based auth — no Authentication= attribute; token passed via attrs_before
        base += "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
    else:
        # SQL auth
        base += (
            f"UID={_USERNAME};PWD={_PASSWORD};"
            "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )
    return base


def is_available() -> bool:
    """Check if Synapse credentials are configured."""
    return bool(_SERVER)


def _connect() -> pyodbc.Connection:
    """Get or create a persistent connection for the current thread."""
    conn = getattr(_conn_local, "conn", None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except Exception:
            with suppress(Exception):
                conn.close()
            _conn_local.conn = None

    conn_str = _get_connection_string()
    if _AUTH_MODE == "entra":
        token_struct = _get_access_token()
        conn = pyodbc.connect(conn_str, attrs_before={1256: token_struct}, timeout=30)
    else:
        conn = pyodbc.connect(conn_str, timeout=30)
    conn.autocommit = True
    _conn_local.conn = conn
    return conn


def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute a parameterized query and return rows as dicts."""
    t0 = time.time()
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute(sql, params)
    if cursor.description is None:
        return []
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    elapsed = round((time.time() - t0) * 1000)
    logger.debug(f"[synapse] query returned {len(rows)} rows in {elapsed}ms")
    return rows


# ── Household-scoped queries ─────────────────────────────────────────────


def resolve_household(
    household_id: int | None = None,
    household_name: str | None = None,
) -> dict[str, Any] | None:
    """Look up a household by AVHHID or fuzzy name match.

    Returns dict with household_id, household_name, or None if not found.
    """
    if household_id is not None:
        rows = _query(
            """
            SELECT TOP 1
                chf.[AVHHID] AS household_id,
                chd.[HHName] AS household_name
            FROM [tho].[Current_Household_Fact] chf
            LEFT JOIN [tho].[Current_Household_Demographic] chd
                ON chf.[LeadId] = chd.[LeadId]
            WHERE chf.[AVHHID] = ?
            """,
            (household_id,),
        )
        return rows[0] if rows else None

    if household_name:
        rows = _query(
            """
            SELECT TOP 5
                chf.[AVHHID] AS household_id,
                chd.[HHName] AS household_name
            FROM [tho].[Current_Household_Fact] chf
            LEFT JOIN [tho].[Current_Household_Demographic] chd
                ON chf.[LeadId] = chd.[LeadId]
            WHERE chd.[HHName] LIKE ?
            ORDER BY chf.[AVHHID]
            """,
            (f"%{household_name}%",),
        )
        if len(rows) == 1:
            return rows[0]
        return None

    return None


def resolve_household_by_account(account_number: str) -> int | None:
    """Map an account number (e.g. the corporate account) to its household AVHHID.

    The warehouse is scoped by household, so this is the bridge from an account
    number to the DEMO_HOUSEHOLD_ID the data layer queries with. Returns None if
    the account isn't found.
    """
    rows = _query(
        """
        SELECT TOP 1 a.[Primary Household ID] AS household_id
        FROM [tav].[All_Custodian_Values] a
        WHERE a.[Account Number] = ?
        """,
        (account_number,),
    )
    hh = rows[0].get("household_id") if rows else None
    return int(hh) if hh is not None else None


def get_household_members(household_id: int) -> list[dict[str, Any]]:
    """Fetch contact demographics for a household (primary/secondary members)."""
    # Resolve AVHHID → Salesforce HHID for Contact_Demographic
    hh_rows = _query(
        "SELECT TOP 1 [HHID] FROM [tho].[hh_fact] WHERE [avhhid] = ?",
        (household_id,),
    )
    if not hh_rows:
        return []
    sf_hh_id = hh_rows[0]["HHID"]

    return _query(
        """
        SELECT
            cd.[contact_name] AS contact_name,
            cd.[dob] AS date_of_birth,
            cd.[primary_or_secondary] AS role,
            cd.[employment_status] AS employment_status,
            cd.[retire_date] AS retire_date
        FROM [tho].[Contact_Demographic] cd
        WHERE cd.[hh_id] = ?
        ORDER BY cd.[primary_or_secondary]
        """,
        (sf_hh_id,),
    )


def get_accounts(household_id: int) -> list[dict[str, Any]]:
    """Fetch all accounts for a household with balances."""
    return _query(
        """
        SELECT
            a.[Upload Account ID] AS account_id,
            a.[Account Number] AS account_number,
            a.[Account Name] AS account_name,
            a.[Account Type] AS account_type,
            a.[Account Category] AS account_category,
            a.[Custodian] AS custodian,
            CAST(a.[Total Account Value] AS FLOAT) AS balance,
            a.[Rebalancing Model Name] AS model_name
        FROM [tav].[All_Custodian_Values] a
        WHERE a.[Primary Household ID] = ?
          AND a.[Total Account Value] IS NOT NULL
          AND a.[Total Account Value] > 0
        ORDER BY CAST(a.[Total Account Value] AS FLOAT) DESC
        """,
        (household_id,),
    )


def get_holdings(household_id: int) -> list[dict[str, Any]]:
    """Fetch holdings grouped by account and asset class."""
    return _query(
        """
        SELECT
            [avaccountuploadid] AS account_id,
            ISNULL([Asset Class], 'Unclassified') AS asset_class,
            SUM(CAST([Total Account Value] AS FLOAT)) AS market_value
        FROM [tho].[Account_Daily_Holdings]
        WHERE [avhhid] = ?
          AND [Total Account Value] > 0
        GROUP BY [avaccountuploadid], [Asset Class]
        ORDER BY SUM(CAST([Total Account Value] AS FLOAT)) DESC
        """,
        (household_id,),
    )


def get_rollforward(household_id: int, periods: int = 12) -> list[dict[str, Any]]:
    """Fetch recent cash flow rollforward (distributions, withdrawals, expenses)."""
    return _query(
        """
        SELECT TOP (?)
            rf.[Reporting_Period_Key] AS period_key,
            CAST(ISNULL(rf.[Distribution], 0) AS FLOAT) AS distribution,
            CAST(ISNULL(rf.[cashwithdrawal], 0) AS FLOAT) AS cash_withdrawal,
            CAST(ISNULL(rf.[withdrawalsecurities], 0) AS FLOAT) AS withdrawal_securities,
            CAST(ISNULL(rf.[expenses], 0) AS FLOAT) AS expenses,
            CAST(ISNULL(rf.[BoP_AUM], 0) AS FLOAT) AS bop_aum,
            CAST(ISNULL(rf.[total account value], 0) AS FLOAT) AS eop_aum
        FROM [tho].[Household_Rollforward] rf
        WHERE rf.[avhhid] = ?
        ORDER BY rf.[Reporting_Period_Key] DESC
        """,
        (periods, household_id),
    )


def get_net_worth_history(household_id: int) -> list[dict[str, Any]]:
    """Fetch AUM/net worth history from rollforward data."""
    return _query(
        """
        SELECT
            rf.[Reporting_Period_Key] AS period_key,
            CAST(rf.[total account value] AS FLOAT) AS net_worth
        FROM [tho].[Household_Rollforward] rf
        WHERE rf.[avhhid] = ?
        ORDER BY rf.[Reporting_Period_Key] ASC
        """,
        (household_id,),
    )


def test_connection() -> dict[str, Any]:
    """Test Synapse connectivity. Returns status dict."""
    if not is_available():
        return {"connected": False, "reason": "SYNAPSE_SERVER not configured"}
    try:
        t0 = time.time()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS ping")
        conn.close()
        elapsed = round((time.time() - t0) * 1000)
        return {"connected": True, "server": _SERVER, "database": _DATABASE, "latency_ms": elapsed}
    except Exception as e:
        print(f"[synapse] connection failed: {e}", file=sys.stderr)
        return {"connected": False, "reason": str(e)}
