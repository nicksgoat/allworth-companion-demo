"""Synapse read/write layer for the NFBC console.

Ported from the standalone prototype (nfbc-tool/wealth_mcp/web/synapse.py) with
two deliberate changes:

  1. The semantic-layer TML registry is replaced with **inlined SQL literals**
     (verified against the *.table.tml definitions) to match this app's
     raw-SQL style and drop the heavy wealth_mcp dependency.
  2. Connections are built from this app's AUTH_METHOD env path (mirroring
     backend/app.py::get_database_connection) so NFBC uses the same Synapse
     credentials already wired into docker-compose — but on a DEDICATED pool
     with explicit commit()/rollback() for writes, never the shared dashboard
     read connection.

Load-bearing detail preserved from the prototype: Azure Synapse dedicated SQL
pools reject implicit INT->BIGINT and FLOAT->DECIMAL conversions in
parameterized queries, so insert/update use explicit CAST(? AS ...).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import date, datetime
from decimal import Decimal
from threading import Lock
from typing import Any

import pyodbc

logger = logging.getLogger(__name__)

# ── Connection config (mirrors backend/app.py) ──────────────────────────────

SERVER = os.getenv("SYNAPSE_SERVER", "allworthsynapse.sql.azuresynapse.net")
DATABASE = os.getenv("SYNAPSE_DATABASE", "DataWarehouse")
DRIVER = os.getenv("ODBC_DRIVER", "{ODBC Driver 18 for SQL Server}")
AUTH_METHOD = os.getenv("AUTH_METHOD", "ActiveDirectoryInteractive")
QUERY_TIMEOUT = int(os.getenv("SYNAPSE_QUERY_TIMEOUT", "60"))


def _build_conn_str() -> str:
    """Build the ODBC connection string from AUTH_METHOD (same logic as app.py)."""
    if AUTH_METHOD == "ServicePrincipal":
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")
        if not all([client_id, client_secret, tenant_id]):
            raise ValueError(
                "Service Principal credentials not configured. Set AZURE_CLIENT_ID, "
                "AZURE_CLIENT_SECRET, and AZURE_TENANT_ID"
            )
        return (
            f"DRIVER={DRIVER};SERVER={SERVER};DATABASE={DATABASE};"
            f"Authentication=ActiveDirectoryServicePrincipal;"
            f"UID={client_id}@{tenant_id};PWD={client_secret};"
            f"Encrypt=yes;TrustServerCertificate=no"
        )
    if AUTH_METHOD == "SqlPassword":
        username = os.getenv("SYNAPSE_USERNAME")
        password = os.getenv("SYNAPSE_PASSWORD")
        if not all([username, password]):
            raise ValueError(
                "SQL credentials not configured. Set SYNAPSE_USERNAME and SYNAPSE_PASSWORD"
            )
        return (
            f"DRIVER={DRIVER};SERVER={SERVER};DATABASE={DATABASE};"
            f"UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=no"
        )
    if AUTH_METHOD == "ActiveDirectoryInteractive":
        return (
            f"DRIVER={DRIVER};SERVER={SERVER};DATABASE={DATABASE};"
            f"Authentication=ActiveDirectoryInteractive;"
            f"Encrypt=yes;TrustServerCertificate=no"
        )
    raise ValueError(
        f"Unknown AUTH_METHOD: {AUTH_METHOD}. "
        "Use ServicePrincipal, SqlPassword, or ActiveDirectoryInteractive"
    )


# ── Dedicated connection pool (separate from the dashboard read connection) ──

_pool: list[pyodbc.Connection] = []
_POOL_SIZE = int(os.getenv("NFBC_SYNAPSE_POOL_SIZE", "4"))
_pool_lock = Lock()


def _new_conn() -> pyodbc.Connection:
    """Open a fresh connection with BOTH login and query timeouts bounded.

    pyodbc.connect(timeout=...) sets only the LOGIN timeout. The query timeout is
    a separate attribute (conn.timeout, SQL_ATTR_QUERY_TIMEOUT) that defaults to 0
    = no timeout. Without it, a query on a silently-dropped Synapse connection
    (idle-timed-out server side) blocks forever with nothing visible server side.
    """
    c = pyodbc.connect(_build_conn_str(), timeout=QUERY_TIMEOUT)
    c.timeout = QUERY_TIMEOUT
    # Normalize autocommit: the app's read/write path is transactional (explicit
    # commit/rollback). pyodbc's ODBC-level pooling can hand back a connection
    # left in autocommit mode by the DDL path (ensure_cache_table), which would
    # make a later write()'s commit() fail with "no corresponding transaction"
    # (Synapse 111214 / SQLEndTran). Force a known transactional state here.
    c.autocommit = False
    return c


def _conn() -> pyodbc.Connection:
    """Return a live pooled connection, or open a fresh one.

    The liveness probe (SELECT 1) is a network round-trip and MUST run outside
    _pool_lock: holding a global lock across a network call means one stale
    connection freezes every worker. We pop a candidate under the lock, then
    validate it with the lock released. The query timeout set in _new_conn bounds
    the probe so a half-open connection can't hang it indefinitely.
    """
    while True:
        with _pool_lock:
            c = _pool.pop() if _pool else None
        if c is None:
            return _new_conn()
        try:
            cur = c.execute("SELECT 1")
            cur.fetchall()
            return c
        except Exception:
            try:
                c.close()
            except Exception:
                pass
            # fall through: try the next pooled connection or create a fresh one


def _release(c: pyodbc.Connection) -> None:
    with _pool_lock:
        if len(_pool) < _POOL_SIZE:
            _pool.append(c)
            return
    try:
        c.close()
    except Exception:
        pass


def _clean(val: Any) -> Any:
    if val is None or isinstance(val, (int, float, str, bool)):
        return val
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return str(val)


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a SELECT and return a list of row-dicts."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        cols = [d[0] for d in cur.description]
        return [{c: _clean(v) for c, v in zip(cols, row)} for row in cur.fetchall()]
    finally:
        _release(conn)


def write(sql: str, params: tuple = ()) -> int:
    """Run an INSERT/UPDATE/DELETE inside an explicit transaction. Returns rows_affected."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        affected = cur.rowcount
        conn.commit()
        logger.info("NFBC WRITE: %s | params=%s | rows=%d", sql[:120], params, affected)
        return affected
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _release(conn)


# ── Table / column literals (verified from *.table.tml) ─────────────────────

_NFBC = "[tho].[NFBC_Adjustment]"
_HH_DIM = "[fnp].[av_hh_dim_monthly_draft]"
_HH_RF = "[tho].[Household_Rollforward]"
_HH_FACT = "[tho].[Current_Household_Fact]"
_ACT = "[fnp].[av_activitytypes_monthly_draft]"

# NFBC_Adjustment columns
_NFBC_AVHHID = "avhhid"
_NFBC_PERIOD = "reportingperiod"
_NFBC_PERIOD_KEY = "Reporting_Period_Key"
_NFBC_FLOW_ADJ = "flow_adjustment"
_NFBC_MULTIPLIER = "flow_adjustment_multiplier"
_NFBC_ADJ_TYPE = "adjustment_type"

# av_hh_dim_monthly_draft columns (avhhid is VARCHAR here)
_HH_AVHHID = "avhhid"
_HH_NAME = "sfhhname"
_HH_ADVISOR = "sfadvisor"
_HH_PREV_ADV = "previousadvisor"
_HH_ADV_REGION = "advisorregion"
_HH_ADV_SOURCE = "advisoracqsource"
_HH_PERIOD = "reportingperiod"
_HH_SFHHID = "sfhhid"

# av_activitytypes_monthly_draft columns
_ACT_AVHHID = "avhhid"
_ACT_ACCOUNTNUM = "avaccountnum"

# Household_Rollforward columns (avhhid is INT64; note spaced column name)
_RF_AVHHID = "avhhid"
_RF_PERIOD = "reportingperiod"
_RF_TAV = "Total_Account_Value"
_RF_CASHDEPOSIT = "cashdeposit"
_RF_CASHWITHDRAW = "cashwithdrawal"
_RF_RECEIPTSEC = "receiptsecurities"
_RF_WITHDRAWSEC = "withdrawalsecurities"
_RF_NCNM = "NCNM"

# Current_Household_Fact columns
_CHF_AVHHID = "AVHHID"
_CHF_TTM_FLOWS = "ttm_net_flows"


# ── Advisor index (cached distinct sfadvisor values) ─────────────────────────

_advisor_index: dict[str, dict] | None = None


def _load_advisor_index() -> dict[str, dict]:
    global _advisor_index
    if _advisor_index is not None:
        return _advisor_index
    try:
        rows = query(
            f"SELECT DISTINCT {_HH_ADVISOR} FROM {_HH_DIM}"
            f" WHERE {_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})"
            f"   AND {_HH_ADVISOR} IS NOT NULL AND {_HH_ADVISOR} <> ''"
        )
        _advisor_index = {
            r[_HH_ADVISOR].strip().lower(): {"name": r[_HH_ADVISOR].strip()}
            for r in rows
            if r.get(_HH_ADVISOR)
        }
        logger.info("NFBC advisor index loaded: %d advisors", len(_advisor_index))
    except Exception as exc:
        logger.warning("Failed to load advisor index: %s", exc)
        _advisor_index = {}
    return _advisor_index


def get_advisors() -> list[dict]:
    return sorted(_load_advisor_index().values(), key=lambda a: a["name"])


def is_advisor(name: str) -> bool:
    return name.strip().lower() in _load_advisor_index()


# ── preview / confirm token system ──────────────────────────────────────────

_pending: dict[str, dict] = {}
_TOKEN_TTL = 300


def make_token(payload: dict) -> str:
    raw = f"{payload}{time.time()}"
    token = hashlib.sha256(raw.encode()).hexdigest()[:16]
    _pending[token] = {"payload": payload, "ts": time.time()}
    return token


def validate_token(token: str) -> dict | None:
    entry = _pending.pop(token, None)
    if entry is None:
        return None
    if time.time() - entry["ts"] > _TOKEN_TTL:
        return None
    return entry["payload"]


# ── domain queries ──────────────────────────────────────────────────────────


def lookup_avhhid_by_account(account_num: str) -> list[dict]:
    """Resolve a custodian account number to household row(s) via activities."""
    sql = f"""
        SELECT DISTINCT d.{_HH_AVHHID} AS avhhid, d.{_HH_NAME} AS sfhhname,
               d.{_HH_ADVISOR} AS sfadvisor, d.{_HH_PREV_ADV} AS previousadvisor
        FROM {_ACT} a
        JOIN {_HH_DIM} d
          ON a.{_ACT_AVHHID} = d.{_HH_AVHHID}
         AND d.{_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        WHERE a.{_ACT_ACCOUNTNUM} = ?
    """
    rows = query(sql, (account_num,))
    if rows:
        return rows

    digits_only = account_num.replace("-", "")
    sql_like = f"""
        SELECT DISTINCT d.{_HH_AVHHID} AS avhhid, d.{_HH_NAME} AS sfhhname,
               d.{_HH_ADVISOR} AS sfadvisor, d.{_HH_PREV_ADV} AS previousadvisor
        FROM {_ACT} a
        JOIN {_HH_DIM} d
          ON a.{_ACT_AVHHID} = d.{_HH_AVHHID}
         AND d.{_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        WHERE a.{_ACT_ACCOUNTNUM} LIKE ? OR a.{_ACT_ACCOUNTNUM} = ?
    """
    return query(sql_like, (f"%{account_num}", digits_only))


# Name-search tokens to ignore (connectors / suffixes, not identifying tokens).
_NAME_TOKEN_STOP = {"and", "the", "jr", "sr", "ii", "iii", "iv"}


def lookup_by_sfhhid(sfid: str) -> list[dict]:
    """Resolve a Salesforce household/record id (from a ticket's Lightning URL)
    to the household via the dim's ``sfhhid`` — the most precise disambiguator."""
    sfid = (sfid or "").strip()
    if not sfid:
        return []
    return query(
        f"""
        SELECT DISTINCT {_HH_AVHHID} AS avhhid, {_HH_NAME} AS sfhhname,
               {_HH_ADVISOR} AS sfadvisor, {_HH_PREV_ADV} AS previousadvisor
        FROM {_HH_DIM}
        WHERE {_HH_SFHHID} = ?
          AND {_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        """,
        (sfid,),
    )


def search_households_by_name_account(name: str, acct_suffix: str) -> list[dict]:
    """Households matching a name AND holding an account ending in ``acct_suffix``.

    Disambiguates same-surname households (e.g. several William Jacksons) using
    the account number the ticket cites — 'William Jackson' + 'ending 2155'
    resolves to the one household that actually holds that account."""
    tokens = [w for w in re.findall(r"[A-Za-z]{3,}", name or "")
              if w.lower() not in _NAME_TOKEN_STOP]
    acct_suffix = (acct_suffix or "").strip()
    if not tokens or not acct_suffix:
        return []
    name_where = " AND ".join([f"d.{_HH_NAME} LIKE ?"] * len(tokens))
    sql = f"""
        SELECT DISTINCT TOP 5 d.{_HH_AVHHID} AS avhhid, d.{_HH_NAME} AS sfhhname,
               d.{_HH_ADVISOR} AS sfadvisor, d.{_HH_PREV_ADV} AS previousadvisor
        FROM {_ACT} a
        JOIN {_HH_DIM} d
          ON a.{_ACT_AVHHID} = d.{_HH_AVHHID}
         AND d.{_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        WHERE ({name_where})
          AND a.{_ACT_ACCOUNTNUM} LIKE ?
    """
    params = tuple(f"%{t}%" for t in tokens) + (f"%{acct_suffix}",)
    return query(sql, params)


def search_households(term: str, search_advisors: bool = False) -> list[dict]:
    """Search HH dim by name, avhhid, advisor name, or custodian account number."""
    term = (term or "").strip()
    if not term:
        return []

    if term.isdigit():
        sql = f"""
            SELECT DISTINCT {_HH_AVHHID} AS avhhid, {_HH_NAME} AS sfhhname,
                   {_HH_ADVISOR} AS sfadvisor, {_HH_PREV_ADV} AS previousadvisor
            FROM {_HH_DIM}
            WHERE {_HH_AVHHID} = ?
              AND {_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        """
        rows = query(sql, (term,))
        return rows if rows else lookup_avhhid_by_account(term)

    if re.fullmatch(r"\d{2,5}-\d{4,}", term):
        return lookup_avhhid_by_account(term)

    if search_advisors:
        sql = f"""
            SELECT DISTINCT {_HH_AVHHID} AS avhhid, {_HH_NAME} AS sfhhname,
                   {_HH_ADVISOR} AS sfadvisor, {_HH_PREV_ADV} AS previousadvisor
            FROM {_HH_DIM}
            WHERE ({_HH_NAME} LIKE ? OR {_HH_ADVISOR} LIKE ? OR {_HH_PREV_ADV} LIKE ?)
              AND {_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
            ORDER BY {_HH_NAME}
        """
        pat = f"%{term}%"
        return query(sql, (pat, pat, pat))

    sql = f"""
        SELECT DISTINCT {_HH_AVHHID} AS avhhid, {_HH_NAME} AS sfhhname,
               {_HH_ADVISOR} AS sfadvisor, {_HH_PREV_ADV} AS previousadvisor
        FROM {_HH_DIM}
        WHERE {_HH_NAME} LIKE ?
          AND {_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        ORDER BY {_HH_NAME}
    """
    rows = query(sql, (f"%{term}%",))
    if rows:
        return rows

    # Name-order tolerant fallback: tickets say "First Last" but the dim stores
    # "Last, First & Spouse". Match on every significant token (order-independent,
    # prefix-friendly so "Ken"->"Kenneth"); if that misses, the single most
    # distinctive token. TOP 25 bounds a broad surname match.
    tokens = [w for w in re.findall(r"[A-Za-z]{3,}", term)
              if w.lower() not in _NAME_TOKEN_STOP]

    def _run(where: str, params: tuple) -> list[dict]:
        return query(
            f"""
            SELECT TOP 25 {_HH_AVHHID} AS avhhid, {_HH_NAME} AS sfhhname,
                   {_HH_ADVISOR} AS sfadvisor, {_HH_PREV_ADV} AS previousadvisor
            FROM {_HH_DIM}
            WHERE ({where})
              AND {_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
            ORDER BY {_HH_NAME}
            """,
            params,
        )

    if len(tokens) >= 2:
        where = " AND ".join([f"{_HH_NAME} LIKE ?"] * len(tokens))
        rows = _run(where, tuple(f"%{t}%" for t in tokens))
        if rows:
            return rows
    if tokens:
        longest = max(tokens, key=len)
        return _run(f"{_HH_NAME} LIKE ?", (f"%{longest}%",))
    return []


def investigate_household(avhhid: str) -> dict:
    """Full investigation: dim info, last-12-month flows, existing adjustments, TTM fact."""
    dim = query(
        f"""
        SELECT {_HH_AVHHID} AS avhhid, {_HH_NAME} AS sfhhname, {_HH_ADVISOR} AS sfadvisor,
               {_HH_PREV_ADV} AS previousadvisor, {_HH_ADV_REGION} AS advisorregion,
               {_HH_ADV_SOURCE} AS advisoracqsource, {_HH_PERIOD} AS reportingperiod
        FROM {_HH_DIM}
        WHERE {_HH_AVHHID} = ?
          AND {_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        """,
        (str(avhhid),),
    )

    flows = query(
        f"""
        SELECT
            CONVERT(VARCHAR(10), r.{_RF_PERIOD}, 120) AS reportingperiod,
            r.{_RF_CASHDEPOSIT} + r.{_RF_RECEIPTSEC} AS inflows,
            r.{_RF_CASHWITHDRAW} + r.{_RF_WITHDRAWSEC} AS outflows,
            r.{_RF_NCNM} AS net_flows,
            r.{_RF_TAV} AS total_aum
        FROM {_HH_RF} r
        WHERE r.{_RF_AVHHID} = ?
          AND r.{_RF_PERIOD} >= DATEADD(MONTH, -12, GETDATE())
        ORDER BY r.{_RF_PERIOD}
        """,
        (int(avhhid),),
    )

    adjustments = get_adjustments_for(int(avhhid))

    fact = query(
        f"""
        SELECT {_CHF_AVHHID} AS avhhid, {_CHF_TTM_FLOWS} AS ttm_net_flows
        FROM {_HH_FACT}
        WHERE {_CHF_AVHHID} = ?
        """,
        (int(avhhid),),
    )

    return {
        "dim": dim[0] if dim else None,
        "flows": flows,
        "adjustments": adjustments,
        "fact": fact[0] if fact else None,
    }


def get_adjustments_for(avhhid: int) -> list[dict]:
    return query(
        f"""
        SELECT {_NFBC_AVHHID} AS avhhid,
               CONVERT(VARCHAR(10), {_NFBC_PERIOD}, 120) AS reportingperiod,
               {_NFBC_PERIOD_KEY} AS reporting_period_key,
               {_NFBC_FLOW_ADJ} AS flow_adjustment,
               {_NFBC_MULTIPLIER} AS multiplier,
               {_NFBC_ADJ_TYPE} AS adjustment_type
        FROM {_NFBC}
        WHERE {_NFBC_AVHHID} = ?
        ORDER BY {_NFBC_PERIOD}
        """,
        (int(avhhid),),
    )


def get_all_adjustments() -> list[dict]:
    """All NFBC adjustments joined with HH names for the audit view."""
    return query(
        f"""
        SELECT
            a.{_NFBC_AVHHID} AS avhhid,
            h.{_HH_NAME} AS sfhhname,
            h.{_HH_ADVISOR} AS sfadvisor,
            CONVERT(VARCHAR(10), a.{_NFBC_PERIOD}, 120) AS reportingperiod,
            a.{_NFBC_FLOW_ADJ} AS flow_adjustment,
            a.{_NFBC_MULTIPLIER} AS multiplier,
            a.{_NFBC_ADJ_TYPE} AS adjustment_type
        FROM {_NFBC} a
        LEFT JOIN {_HH_DIM} h
            ON CAST(a.{_NFBC_AVHHID} AS NVARCHAR) = h.{_HH_AVHHID}
           AND h.{_HH_PERIOD} = (SELECT MAX({_HH_PERIOD}) FROM {_HH_DIM})
        ORDER BY a.{_NFBC_PERIOD} DESC, a.{_NFBC_AVHHID}
        """
    )


# ── Durable per-ticket build cache ──────────────────────────────────────────
# Caches each ticket's finalized proposal rows keyed by a change-fingerprint so a
# queue rebuild only re-runs the expensive Jira+LLM+Synapse work for tickets that
# actually changed. Persisted in Synapse (survives container restart/redeploy,
# unlike the ephemeral proposals.json) and records per-ticket build time so the
# slowest tickets are visible for tuning.
_CACHE = "[tho].[NFBC_Console_Cache]"
_cache_table_ready = False
_cache_ddl_lock = Lock()


def ensure_cache_table() -> None:
    """Create the cache table once. DDL must run with autocommit — Synapse
    dedicated pools reject CREATE TABLE inside a transaction."""
    global _cache_table_ready
    if _cache_table_ready:
        return
    with _cache_ddl_lock:
        if _cache_table_ready:
            return
        conn = _new_conn()
        try:
            conn.autocommit = True
            conn.execute(
                f"""
                IF OBJECT_ID('{_CACHE}') IS NULL
                CREATE TABLE {_CACHE} (
                    ticket_key   NVARCHAR(32)   NOT NULL,
                    fingerprint  NVARCHAR(64)   NOT NULL,
                    rows_json    NVARCHAR(MAX)  NOT NULL,
                    build_ms     INT            NULL,
                    provider     NVARCHAR(32)   NULL,
                    model        NVARCHAR(64)   NULL,
                    built_by     NVARCHAR(128)  NULL,
                    built_at     DATETIME2      NOT NULL
                ) WITH (HEAP, DISTRIBUTION = ROUND_ROBIN)
                """
            )
            _cache_table_ready = True
        finally:
            try:
                conn.autocommit = False  # don't pool a connection in autocommit mode
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass


def get_cached_build(ticket_key: str) -> dict | None:
    """Return ``{'fingerprint', 'rows'}`` for a ticket, or None. Never raises —
    a cache miss/failure just means the ticket gets recomputed."""
    try:
        ensure_cache_table()
        rows = query(
            f"SELECT TOP 1 fingerprint, rows_json FROM {_CACHE} "
            f"WHERE ticket_key = CAST(? AS NVARCHAR(32))",
            (str(ticket_key),),
        )
    except Exception:
        logger.warning("NFBC cache read failed for %s", ticket_key, exc_info=True)
        return None
    if not rows:
        return None
    try:
        return {"fingerprint": rows[0]["fingerprint"],
                "rows": json.loads(rows[0]["rows_json"])}
    except Exception:
        return None


def save_cached_build(ticket_key: str, fingerprint: str, rows: list[dict],
                      build_ms: int | None, provider: str | None,
                      model: str | None, built_by: str | None) -> None:
    """Upsert (delete + insert) a ticket's cached rows and build telemetry.

    Never raises — caching is best-effort and must not fail a build. INSERT uses
    the SELECT/CAST form (Synapse rejects CAST expressions in INSERT..VALUES)."""
    try:
        ensure_cache_table()
        payload = json.dumps(rows, ensure_ascii=False)
        conn = _conn()
        try:
            cur = conn.cursor()
            cur.execute(
                f"DELETE FROM {_CACHE} WHERE ticket_key = CAST(? AS NVARCHAR(32))",
                (str(ticket_key),),
            )
            cur.execute(
                f"""
                INSERT INTO {_CACHE}
                    (ticket_key, fingerprint, rows_json, build_ms, provider, model, built_by, built_at)
                SELECT CAST(? AS NVARCHAR(32)), CAST(? AS NVARCHAR(64)), CAST(? AS NVARCHAR(MAX)),
                       CAST(? AS INT), CAST(? AS NVARCHAR(32)), CAST(? AS NVARCHAR(64)),
                       CAST(? AS NVARCHAR(128)), SYSUTCDATETIME()
                """,
                (str(ticket_key), str(fingerprint), payload,
                 int(build_ms) if build_ms is not None else None,
                 provider, model, built_by),
            )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            _release(conn)
    except Exception:
        logger.warning("NFBC cache write failed for %s", ticket_key, exc_info=True)


def build_stats(limit: int = 100) -> list[dict]:
    """Per-ticket cached build telemetry (slowest first) for efficiency analysis."""
    try:
        ensure_cache_table()
        return query(
            f"""
            SELECT TOP {int(limit)} ticket_key, build_ms, provider, model,
                   CONVERT(VARCHAR(19), built_at, 120) AS built_at, built_by
            FROM {_CACHE}
            ORDER BY build_ms DESC
            """
        )
    except Exception:
        logger.warning("NFBC build_stats failed", exc_info=True)
        return []


def insert_adjustment(
    avhhid: int,
    reportingperiod: str,
    flow_adjustment: float,
    adjustment_type: str,
    multiplier: int = 1,
) -> int:
    """Insert one NFBC adjustment row.

    Explicit CAST is required: Synapse dedicated pools reject implicit
    INT->BIGINT / FLOAT->DECIMAL conversions in parameterized queries.
    """
    return write(
        f"""
        INSERT INTO {_NFBC}
            ({_NFBC_AVHHID}, {_NFBC_PERIOD}, {_NFBC_PERIOD_KEY}, {_NFBC_FLOW_ADJ},
             {_NFBC_MULTIPLIER}, {_NFBC_ADJ_TYPE})
        SELECT CAST(? AS BIGINT), ?, NULL, CAST(? AS DECIMAL(18,2)), CAST(? AS INT), ?
        """,
        (avhhid, reportingperiod, flow_adjustment, multiplier, adjustment_type),
    )


def update_adjustment(
    avhhid: int,
    reportingperiod: str,
    old_flow_adjustment: float,
    old_adjustment_type: str,
    new_flow_adjustment: float,
    new_adjustment_type: str,
    new_multiplier: int = 1,
) -> int:
    """Update an existing row (matched on avhhid+period+amount+type; no surrogate PK)."""
    return write(
        f"""
        UPDATE {_NFBC}
        SET {_NFBC_FLOW_ADJ}   = CAST(? AS DECIMAL(18,2)),
            {_NFBC_ADJ_TYPE}   = ?,
            {_NFBC_MULTIPLIER} = CAST(? AS INT)
        WHERE {_NFBC_AVHHID}   = CAST(? AS BIGINT)
          AND CONVERT(VARCHAR(10), {_NFBC_PERIOD}, 120) = ?
          AND CAST({_NFBC_FLOW_ADJ} AS DECIMAL(18,2)) = CAST(? AS DECIMAL(18,2))
          AND {_NFBC_ADJ_TYPE} = ?
        """,
        (new_flow_adjustment, new_adjustment_type, new_multiplier,
         avhhid, reportingperiod, old_flow_adjustment, old_adjustment_type),
    )


def delete_adjustment(
    avhhid: int,
    reportingperiod: str,
    flow_adjustment: float,
    adjustment_type: str,
) -> int:
    """Delete a row (matched on avhhid+period+amount+type)."""
    return write(
        f"""
        DELETE FROM {_NFBC}
        WHERE {_NFBC_AVHHID}   = CAST(? AS BIGINT)
          AND CONVERT(VARCHAR(10), {_NFBC_PERIOD}, 120) = ?
          AND CAST({_NFBC_FLOW_ADJ} AS DECIMAL(18,2)) = CAST(? AS DECIMAL(18,2))
          AND {_NFBC_ADJ_TYPE} = ?
        """,
        (avhhid, reportingperiod, flow_adjustment, adjustment_type),
    )
