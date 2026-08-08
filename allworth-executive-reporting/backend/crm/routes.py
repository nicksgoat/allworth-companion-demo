"""CRM routes — read-only Client 360 + Advisor book views over Synapse ``tho.*``.

This blueprint is READ-ONLY. It stitches together the Salesforce-sourced
warehouse tables into a Wealthbox-style CRM:

    Current_Household_Demographic  →  client attributes (LeadId grain)
    Current_Household_Fact         →  client measures + advisorid + AVHHID FKs
    User                           →  the advisor who owns the household
    Activity_Dim / Activity_Fact   →  the client's activity timeline / tasks
    Pipeline_Review_Snapshot       →  open opportunities in the pipeline
    Current_Account_Demographic    →  Tamarac accounts (join AVHHID)
    Household_Rollforward          →  monthly AUM + net flows (join avhhid)

Join fabric: LeadId (CRM) → Current_Household_Fact.AVHHID (portfolio household)
→ Household_Rollforward.avhhid / Current_Account_Demographic.Primary_Household_ID.

It follows the same conventions as ``pipeline_review/routes.py``: the shared
Synapse connection from ``app.py``, an in-memory TTL cache, a ``{success, data}``
envelope, and defensive per-route error handling.
"""

from __future__ import annotations

import functools
import math
import re
import threading
import time
from typing import Any

from flask import Blueprint, jsonify, request

bp = Blueprint("crm", __name__)

# The app-wide Synapse connection is a single pyodbc connection with no MARS,
# so concurrent cursors raise "Connection is busy". The CRM page fires several
# requests in parallel — serialize this blueprint's queries.
_query_lock = threading.Lock()


def _serialized(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        with _query_lock:
            return view(*args, **kwargs)
    return wrapper


# ─── JSON safety ─────────────────────────────────────────────────────────────

def _json_safe(value: Any) -> Any:
    """Replace NaN/Infinity (which browsers' JSON.parse rejects) with None."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def _f(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _i(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


# Mojibake signature: a UTF-8 lead-byte character (â/Ã/ð/Â as text) followed by
# a non-ASCII continuation character, or a replacement char. Plain words like
# "château" (â followed by ASCII) do NOT match.
_MOJIBAKE_RE = re.compile(r"[\u00c2\u00c3\u00e2\u00f0][^\x00-\x7f]|\ufffd")


def _fix_mojibake(text: str) -> str:
    """Repair UTF-8 stored through a cp1252/latin-1 round-trip (e.g. Salesforce
    subjects where '✉️ Email' arrives as 'â\\x9c\\x89 Email')."""
    if not _MOJIBAKE_RE.search(text):
        return text
    for codec in ("latin-1", "cp1252"):
        try:
            return text.encode(codec).decode("utf-8", errors="ignore").replace("\ufffd", "").strip()
        except UnicodeError:
            continue
    return text.replace("\ufffd", "").strip()


def _s(value: Any) -> str:
    return _fix_mojibake(str(value)) if value is not None else ""


# ─── DB + cache ──────────────────────────────────────────────────────────────

_conn_holder: dict[str, Any] = {"conn": None}


def _get_db_connection():
    """Dedicated read connection for the CRM (same auth config as app.py).

    The app-wide shared connection is also used by analytics/KPI endpoints;
    pyodbc connections don't support concurrent cursors, so sharing it makes
    parallel CRM page loads fail with "Connection is busy". Reuses the nfbc
    connection-string builder; callers are serialized by ``_serialized``.
    """
    import pyodbc

    from nfbc.synapse_nfbc import _build_conn_str

    conn = _conn_holder["conn"]
    if conn is not None:
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return conn
        except Exception:
            _conn_holder["conn"] = None

    conn = pyodbc.connect(_build_conn_str(), timeout=60)
    conn.timeout = 60
    _conn_holder["conn"] = conn
    return conn


_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 900  # 15 min — warehouse refreshes on a slow cadence


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if entry and (time.time() - entry[0]) < _CACHE_TTL_SECONDS:
        return entry[1]
    return None


def _cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


def _clamp_limit(raw: str | None, default: int, ceiling: int) -> int:
    """Parse a caller-supplied limit into a safe integer (no SQL injection risk
    since it is only ever formatted as a validated int)."""
    try:
        n = int(raw) if raw else default
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, ceiling))


def _sf_lead_url(lead_id: str) -> str:
    return (
        f"https://allworth.lightning.force.com/lightning/r/lead/{lead_id}/view"
        if lead_id else ""
    )


# ─── Row mappers ─────────────────────────────────────────────────────────────

_CLIENT_COLUMNS = [
    "lead_id", "name", "state", "hh_status", "segment", "channel", "stage",
    "job_title", "aum", "paum", "advisor_id", "advisor_name", "avhhid",
]

_CLIENT_SELECT = (
    "D.LeadId, D.Name, D.State, D.HHStatus, D.Client_Segment, D.Channel, D.Stage, "
    "D.Job_Title, F.AUM, F.PAUM, F.advisorid, U.Name AS advisor_name, F.AVHHID"
)

_CLIENT_FROM = (
    "FROM tho.Current_Household_Demographic D "
    "LEFT JOIN tho.Current_Household_Fact F ON F.LeadId = D.LeadId "
    "LEFT JOIN tho.[User] U ON U.User_ID = F.advisorid"
)


def _row_to_client(row) -> dict[str, Any]:
    d = dict(zip(_CLIENT_COLUMNS, row))
    d["aum"] = _f(d["aum"])
    d["paum"] = _f(d["paum"])
    for k in ("name", "state", "hh_status", "segment", "channel", "stage",
              "job_title", "advisor_id", "advisor_name", "avhhid"):
        d[k] = _s(d[k])
    d["lead_id"] = _s(d["lead_id"])
    d["sf_url"] = _sf_lead_url(d["lead_id"])
    return d


_ACTIVITY_COLUMNS = [
    "id", "activity_type", "subject", "status", "call_disposition",
    "completed_by", "created", "owner_name",
]

_ACTIVITY_SELECT = (
    "AD.Id, AD.Activity_Type, AD.Subject, AD.Status, AD.Call_Disposition, "
    "AD.Completed_By, CONVERT(VARCHAR(19), AD.Created_Datetime, 120) AS created, "
    "U.Name AS owner_name"
)

_ACTIVITY_FROM = (
    "FROM tho.Activity_Dim AD "
    "LEFT JOIN tho.Activity_Fact AF ON AF.Id = AD.Id "
    "LEFT JOIN tho.[User] U ON U.User_ID = AF.OwnerId"
)


def _row_to_activity(row) -> dict[str, Any]:
    d = dict(zip(_ACTIVITY_COLUMNS, row))
    for k in _ACTIVITY_COLUMNS:
        d[k] = _s(d[k])
    return d


_OPP_COLUMNS = [
    "lead_id", "name", "paum", "stage", "days_in_stage", "score", "channel",
    "advisor_name", "region", "expected_close_date", "last_activity_date",
    "next_activity_date",
]

_OPP_SELECT = (
    "lead_id, name, paum, stage, days_in_stage, score, channel, advisor_name, region, "
    "CONVERT(VARCHAR(10), expected_close_date, 23) AS expected_close_date, "
    "CONVERT(VARCHAR(10), last_activity_date, 23) AS last_activity_date, "
    "CONVERT(VARCHAR(10), next_activity_date, 23) AS next_activity_date"
)


def _row_to_opp(row) -> dict[str, Any]:
    d = dict(zip(_OPP_COLUMNS, row))
    d["paum"] = _f(d["paum"])
    d["days_in_stage"] = _i(d["days_in_stage"])
    d["score"] = _i(d["score"])
    for k in ("name", "stage", "channel", "advisor_name", "region",
              "expected_close_date", "last_activity_date", "next_activity_date"):
        d[k] = _s(d[k])
    d["lead_id"] = _s(d["lead_id"])
    d["sf_url"] = _sf_lead_url(d["lead_id"])
    return d


def _latest_snapshot_week(cursor) -> str | None:
    cursor.execute("SELECT MAX(snapshot_week) FROM tho.Pipeline_Review_Snapshot")
    row = cursor.fetchone()
    return str(row[0]) if row and row[0] is not None else None


# ─── Routes ──────────────────────────────────────────────────────────────────

@bp.route("/summary", methods=["GET"])
@_serialized
def get_summary():
    """Top-line counts for the CRM dashboard."""
    cached = _cache_get("summary")
    if cached is not None:
        return jsonify({"success": True, "data": cached})
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM tho.Current_Household_Demographic")
        total_clients = _i(cursor.fetchone()[0])

        cursor.execute(
            "SELECT COUNT(DISTINCT advisorid) FROM tho.Current_Household_Fact "
            "WHERE advisorid IS NOT NULL AND advisorid <> ''"
        )
        total_advisors = _i(cursor.fetchone()[0])

        open_opps = 0
        open_paum = 0.0
        week = _latest_snapshot_week(cursor)
        if week:
            cursor.execute(
                "SELECT COUNT(*), SUM(paum) FROM tho.Pipeline_Review_Snapshot "
                "WHERE snapshot_week = ?",
                week,
            )
            r = cursor.fetchone()
            open_opps = _i(r[0])
            open_paum = _f(r[1])

        cursor.close()
        data = _json_safe({
            "total_clients": total_clients,
            "total_advisors": total_advisors,
            "open_opportunities": open_opps,
            "open_pipeline_paum": open_paum,
        })
        _cache_set("summary", data)
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/filters", methods=["GET"])
@_serialized
def get_filters():
    """Distinct segment / channel / status values for the client filter bar."""
    cached = _cache_get("filters")
    if cached is not None:
        return jsonify({"success": True, "data": cached})
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        def _distinct(col: str) -> list[str]:
            cursor.execute(
                f"SELECT DISTINCT {col} FROM tho.Current_Household_Demographic "
                f"WHERE {col} IS NOT NULL AND {col} <> '' ORDER BY {col}"
            )
            return [str(r[0]) for r in cursor.fetchall()]

        data = {
            "segments": _distinct("Client_Segment"),
            "channels": _distinct("Channel"),
            "statuses": _distinct("HHStatus"),
        }
        cursor.close()
        _cache_set("filters", data)
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/clients", methods=["GET"])
@_serialized
def get_clients():
    """Search / list households. Query params: q, advisor (id), segment,
    status, limit."""
    q = request.args.get("q", "").strip()
    advisor = request.args.get("advisor", "").strip()
    segment = request.args.get("segment", "").strip()
    status = request.args.get("status", "").strip()
    limit = _clamp_limit(request.args.get("limit"), default=200, ceiling=1000)

    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        where: list[str] = []
        params: list[Any] = []
        if q:
            where.append("D.Name LIKE ?")
            params.append(f"%{q}%")
        if advisor:
            where.append("F.advisorid = ?")
            params.append(advisor)
        if segment:
            where.append("D.Client_Segment = ?")
            params.append(segment)
        if status:
            where.append("D.HHStatus = ?")
            params.append(status)
        clause = (" WHERE " + " AND ".join(where)) if where else ""

        cursor.execute(
            f"SELECT TOP {limit} {_CLIENT_SELECT} {_CLIENT_FROM}{clause} "
            "ORDER BY F.AUM DESC",
            *params,
        )
        clients = [_row_to_client(r) for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "data": _json_safe(clients)})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/clients/<lead_id>", methods=["GET"])
@_serialized
def get_client(lead_id: str):
    """Full client 360 record for one household."""
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_CLIENT_SELECT}, D.Email, D.Phone, D.Mobile_Phone, D.Address, "
            "D.Zip, F.AUM_Billed, F.HHID, F.secondaryadvisorid "
            f"{_CLIENT_FROM} WHERE D.LeadId = ?",
            lead_id,
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            return jsonify({"success": False, "error": "Client not found"}), 404

        d = _row_to_client(row[: len(_CLIENT_COLUMNS)])
        extra = row[len(_CLIENT_COLUMNS):]
        d["email"] = _s(extra[0])
        d["phone"] = _s(extra[1]) or _s(extra[2])
        d["address"] = _s(extra[3])
        d["zip"] = _s(extra[4])
        d["aum_billed"] = _f(extra[5])
        d["hhid"] = _s(extra[6])
        d["secondary_advisor_id"] = _s(extra[7])
        cursor.close()
        return jsonify({"success": True, "data": _json_safe(d)})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/clients/<lead_id>/activities", methods=["GET"])
@_serialized
def get_client_activities(lead_id: str):
    """Reverse-chronological activity timeline for a household."""
    limit = _clamp_limit(request.args.get("limit"), default=100, ceiling=500)
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT TOP {limit} {_ACTIVITY_SELECT} {_ACTIVITY_FROM} "
            "WHERE AD.LeadId = ? ORDER BY AD.Created_Datetime DESC",
            lead_id,
        )
        activities = [_row_to_activity(r) for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "data": _json_safe(activities)})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/clients/<lead_id>/opportunities", methods=["GET"])
@_serialized
def get_client_opportunities(lead_id: str):
    """Open pipeline opportunities for a household (latest snapshot week)."""
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        week = _latest_snapshot_week(cursor)
        if not week:
            cursor.close()
            return jsonify({"success": True, "data": []})
        cursor.execute(
            f"SELECT {_OPP_SELECT} FROM tho.Pipeline_Review_Snapshot "
            "WHERE lead_id = ? AND snapshot_week = ? ORDER BY paum DESC",
            lead_id, week,
        )
        opps = [_row_to_opp(r) for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "data": _json_safe(opps)})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Portfolio (Tamarac) ─────────────────────────────────────────────────────

def _avhhid_for_lead(cursor, lead_id: str) -> str | None:
    """Resolve the Tamarac household key for a Salesforce lead."""
    cursor.execute(
        "SELECT AVHHID FROM tho.Current_Household_Fact WHERE LeadId = ?", lead_id
    )
    row = cursor.fetchone()
    return str(row[0]) if row and row[0] else None


_ACCOUNT_COLUMNS = [
    "account_id", "account_name", "account_type", "master_category", "custodian",
    "taxable", "total_value", "current_cash", "rmd_total", "rmd_satisfied",
]

_ACCOUNT_SELECT = (
    "Upload_Account_ID, Account_Name, Account_Type, Master_Category, "
    "Custodian, Taxable, Total_Account_Value, Current_Cash, "
    "RMD_Current_Total_Amount, RMD_Current_Satisfied"
)


def _row_to_account(row) -> dict[str, Any]:
    d = dict(zip(_ACCOUNT_COLUMNS, row))
    d["total_value"] = _f(d["total_value"])
    d["current_cash"] = _f(d["current_cash"])
    d["rmd_total"] = _f(d["rmd_total"])
    for k in ("account_id", "account_name", "account_type", "master_category",
              "custodian", "taxable", "rmd_satisfied"):
        d[k] = _s(d[k])
    return d


@bp.route("/clients/<lead_id>/accounts", methods=["GET"])
@_serialized
def get_client_accounts(lead_id: str):
    """Tamarac accounts for a household (Current_Account_Demographic)."""
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        avhhid = _avhhid_for_lead(cursor, lead_id)
        if not avhhid:
            cursor.close()
            return jsonify({"success": True, "data": []})
        cursor.execute(
            f"SELECT {_ACCOUNT_SELECT} FROM tho.Current_Account_Demographic "
            "WHERE Primary_Household_ID = ? ORDER BY Total_Account_Value DESC",
            avhhid,
        )
        accounts = [_row_to_account(r) for r in cursor.fetchall()]
        cursor.close()
        return jsonify({"success": True, "data": _json_safe(accounts)})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


_FLOW_COLUMNS = [
    "period", "total_value", "ncnm", "acquisition", "attrition", "distribution",
    "income", "mgmt_fee",
]

_FLOW_SELECT = (
    "CONVERT(VARCHAR(10), reportingperiod, 23) AS period, "
    "SUM(Total_Account_Value) AS total_value, SUM(NCNM) AS ncnm, "
    "SUM(Acquisition) AS acquisition, SUM(Attrition) AS attrition, "
    "SUM(Distribution) AS distribution, SUM(income) AS income, "
    "SUM(mgntfee) AS mgmt_fee"
)


def _row_to_flow(row) -> dict[str, Any]:
    d = dict(zip(_FLOW_COLUMNS, row))
    d["period"] = _s(d["period"])
    for k in _FLOW_COLUMNS[1:]:
        d[k] = _f(d[k])
    return d


@bp.route("/clients/<lead_id>/flows", methods=["GET"])
@_serialized
def get_client_flows(lead_id: str):
    """Monthly AUM + net-flow history for a household (Household_Rollforward)."""
    months = _clamp_limit(request.args.get("months"), default=24, ceiling=60)
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        avhhid = _avhhid_for_lead(cursor, lead_id)
        if not avhhid:
            cursor.close()
            return jsonify({"success": True, "data": []})
        cursor.execute(
            f"SELECT TOP {months} {_FLOW_SELECT} FROM tho.Household_Rollforward "
            "WHERE avhhid = ? GROUP BY reportingperiod "
            # the current month exists as an all-zero stub until it's filled in
            "HAVING SUM(Total_Account_Value) > 0 "
            "ORDER BY reportingperiod DESC",
            avhhid,
        )
        flows = [_row_to_flow(r) for r in cursor.fetchall()]
        flows.reverse()  # chronological for charting
        cursor.close()
        return jsonify({"success": True, "data": _json_safe(flows)})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Portfolio analytics (allocation, performance, risk, holdings) ───────────

# Allocation buckets in Household_Rollforward are DOLLAR amounts per month-end.
_ALLOCATION_BUCKETS = [
    ("US equities", "asset_allocation_US_equities"),
    ("International equities", "asset_allocation_international_equities"),
    ("Fixed income", "asset_allocation_fixed_income"),
    ("Cash", "asset_allocation_cash"),
    ("Alternatives", "asset_allocation_alternative"),
    ("Asset allocation funds", "asset_allocation_asset_allocation"),
    ("401(k)", "asset_allocation_401K"),
    ("Other", "asset_allocation_other"),
    ("Unclassified", "asset_allocation_unclassified"),
]

_ALLOC_SELECT = ", ".join(f"SUM({col})" for _, col in _ALLOCATION_BUCKETS)


def _allocation_from_row(row, offset: int = 0) -> list[dict[str, Any]]:
    """Map summed bucket columns to labeled slices, dropping empty buckets."""
    slices = []
    for i, (label, _col) in enumerate(_ALLOCATION_BUCKETS):
        value = _f(row[offset + i])
        if value > 0:
            slices.append({"label": label, "value": value})
    total = sum(s["value"] for s in slices) or 1.0
    for s in slices:
        s["pct"] = round(100.0 * s["value"] / total, 1)
    slices.sort(key=lambda s: -s["value"])
    return slices


# Performance methodology mirrors the Allworth plugin's Tamarac MCP
# (tamarac_mcp/warehouse.py): household rows from the raw Tamarac performance
# table are summed per month, monthly return is the cash-flow-adjusted TWR
# (End − Outflows) / (Start + Inflows) − 1, and multi-month figures are
# geometric chain-links of the monthly returns.

def _cash_flow_adjusted_twr(start_value: float, end_value: float,
                            inflows: float, outflows: float) -> float:
    denominator = start_value + inflows
    return ((end_value - outflows) / denominator - 1.0) if denominator > 0 else 0.0


def _chain_link(returns: list[float]) -> float | None:
    if not returns:
        return None
    product = 1.0
    for value in returns:
        product *= 1.0 + value
    return product - 1.0


@bp.route("/clients/<lead_id>/portfolio", methods=["GET"])
@_serialized
def get_client_portfolio(lead_id: str):
    """Portfolio analytics for a household: latest asset allocation, risk
    metrics (beta / duration / yield), monthly performance (MTD %), and top
    holdings with cost basis + unrealized gain/loss from Tamarac positions."""
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        avhhid = _avhhid_for_lead(cursor, lead_id)
        if not avhhid:
            cursor.close()
            return jsonify({"success": True, "data": None})

        # Latest month-end: allocation dollars + risk metrics
        cursor.execute(
            "SELECT TOP 1 CONVERT(VARCHAR(10), reportingperiod, 23), "
            f"{_ALLOC_SELECT}, MAX(beta), MAX(duration), MAX(weighted_average_yield) "
            "FROM tho.Household_Rollforward WHERE avhhid = ? AND Total_Account_Value > 0 "
            "GROUP BY reportingperiod ORDER BY reportingperiod DESC",
            avhhid,
        )
        row = cursor.fetchone()
        allocation: list[dict[str, Any]] = []
        as_of = None
        beta = duration = yield_pct = 0.0
        if row:
            as_of = _s(row[0])
            allocation = _allocation_from_row(row, offset=1)
            n = len(_ALLOCATION_BUCKETS)
            beta, duration, yield_pct = _f(row[1 + n]), _f(row[2 + n]), _f(row[3 + n])

        # Monthly performance from the raw Tamarac table (tav.tamarac_performance),
        # summed to household level per month-end, oldest first
        cursor.execute(
            "SELECT TOP 12 CONVERT(VARCHAR(10), End_Date, 23) AS period, "
            "SUM(ISNULL(Start_Value, 0)), SUM(ISNULL(End_Value, 0)), "
            "SUM(ISNULL(Inflows, 0)), SUM(ISNULL(Outflows, 0)) "
            "FROM tav.tamarac_performance "
            "WHERE Primary_Household_ID = TRY_CAST(? AS BIGINT) "
            "GROUP BY End_Date "
            # skip empty stub months (mirrors the plugin's denominator guard)
            "HAVING SUM(ISNULL(Start_Value, 0)) + SUM(ISNULL(Inflows, 0)) > 0 "
            "ORDER BY End_Date DESC",
            avhhid,
        )
        perf_rows = list(cursor.fetchall())
        perf_rows.reverse()
        performance = []
        monthly_returns: list[float] = []
        for r in perf_rows:
            twr = _cash_flow_adjusted_twr(_f(r[1]), _f(r[2]), _f(r[3]), _f(r[4]))
            monthly_returns.append(twr)
            performance.append({"period": _s(r[0]), "mtd_pct": round(twr * 100.0, 2)})

        # YTD = chain-link of the latest calendar year's monthly returns
        latest_year = performance[-1]["period"][:4] if performance else ""
        ytd_returns = [
            twr for p, twr in zip(performance, monthly_returns)
            if p["period"][:4] == latest_year
        ]
        ytd = _chain_link(ytd_returns)
        ytd_pct = round(ytd * 100.0, 2) if ytd is not None else None

        # Top holdings by market value, with cost basis + unrealized G/L
        cursor.execute(
            "SELECT TOP 15 symbol, custodian, "
            "SUM(market_price * trade_date_quantity) AS market_value, "
            "SUM(cost_basis) AS cost_basis, SUM(unrealized_gain_loss) AS unrealized "
            "FROM tho.positions WHERE avhhid = ? "
            "GROUP BY symbol, custodian "
            "HAVING SUM(market_price * trade_date_quantity) > 0 "
            "ORDER BY market_value DESC",
            avhhid,
        )
        holdings = [
            {
                "symbol": _s(r[0]) or "—",
                "custodian": _s(r[1]),
                "market_value": _f(r[2]),
                "cost_basis": _f(r[3]),
                "unrealized": _f(r[4]),
            }
            for r in cursor.fetchall()
        ]
        cursor.close()

        data = _json_safe({
            "as_of": as_of,
            "allocation": allocation,
            "beta": beta,
            "duration": duration,
            "yield_pct": yield_pct,
            "performance": performance,
            "ytd_pct": ytd_pct,
            "holdings": holdings,
        })
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/opportunities", methods=["GET"])
@_serialized
def get_opportunities():
    """The full open pipeline (latest snapshot week), highest-scoring first."""
    cached = _cache_get("opportunities")
    if cached is not None:
        return jsonify({"success": True, "data": cached})
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        week = _latest_snapshot_week(cursor)
        if not week:
            cursor.close()
            return jsonify({"success": True, "data": []})
        cursor.execute(
            f"SELECT {_OPP_SELECT} FROM tho.Pipeline_Review_Snapshot "
            "WHERE snapshot_week = ? ORDER BY score DESC, paum DESC",
            week,
        )
        opps = [_row_to_opp(r) for r in cursor.fetchall()]
        cursor.close()
        data = _json_safe(opps)
        _cache_set("opportunities", data)
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/tasks", methods=["GET"])
@_serialized
def get_tasks():
    """Open tasks across the book (Activity_Type = 'task', not completed)."""
    limit = _clamp_limit(request.args.get("limit"), default=200, ceiling=1000)
    owner = request.args.get("owner", "").strip()
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        params: list[Any] = []
        owner_clause = ""
        if owner:
            owner_clause = " AND AF.OwnerId = ?"
            params.append(owner)
        cursor.execute(
            f"SELECT TOP {limit} AD.Id, AD.Subject, AD.Status, AD.Activity_Type, "
            "AD.LeadId, CONVERT(VARCHAR(19), AD.Created_Datetime, 120) AS created, "
            "U.Name AS owner_name, D.Name AS client_name "
            "FROM tho.Activity_Dim AD "
            "LEFT JOIN tho.Activity_Fact AF ON AF.Id = AD.Id "
            "LEFT JOIN tho.[User] U ON U.User_ID = AF.OwnerId "
            "LEFT JOIN tho.Current_Household_Demographic D ON D.LeadId = AD.LeadId "
            "WHERE AD.Activity_Type = 'task' "
            "AND (AD.Status IS NULL OR AD.Status <> 'Completed')"
            f"{owner_clause} ORDER BY AD.Created_Datetime DESC",
            *params,
        )
        cols = ["id", "subject", "status", "activity_type", "lead_id",
                "created", "owner_name", "client_name"]
        tasks = []
        for r in cursor.fetchall():
            d = dict(zip(cols, r))
            for k in cols:
                d[k] = _s(d[k])
            d["sf_url"] = _sf_lead_url(d["lead_id"])
            tasks.append(d)
        cursor.close()
        return jsonify({"success": True, "data": _json_safe(tasks)})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


# ─── Advisor view ────────────────────────────────────────────────────────────

_ADVISOR_COLUMNS = [
    "advisor_id", "name", "region", "title", "email", "client_count", "total_aum",
]

_ADVISOR_SELECT = (
    "U.User_ID, U.Name, U.Operational_Region, U.Title, U.Email, "
    "COUNT(F.LeadId) AS client_count, SUM(F.AUM) AS total_aum"
)


def _row_to_advisor(row) -> dict[str, Any]:
    d = dict(zip(_ADVISOR_COLUMNS, row))
    d["client_count"] = _i(d["client_count"])
    d["total_aum"] = _f(d["total_aum"])
    for k in ("advisor_id", "name", "region", "title", "email"):
        d[k] = _s(d[k])
    return d


@bp.route("/advisors", methods=["GET"])
@_serialized
def get_advisors():
    """Advisor roster with book-of-business rollups (client count + AUM)."""
    cached = _cache_get("advisors")
    if cached is not None:
        return jsonify({"success": True, "data": cached})
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_ADVISOR_SELECT} FROM tho.[User] U "
            "JOIN tho.Current_Household_Fact F ON F.advisorid = U.User_ID "
            "GROUP BY U.User_ID, U.Name, U.Operational_Region, U.Title, U.Email "
            "ORDER BY total_aum DESC"
        )
        advisors = [_row_to_advisor(r) for r in cursor.fetchall()]
        cursor.close()
        data = _json_safe(advisors)
        _cache_set("advisors", data)
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/advisors/<user_id>", methods=["GET"])
@_serialized
def get_advisor(user_id: str):
    """One advisor's profile plus their book of clients."""
    limit = _clamp_limit(request.args.get("limit"), default=500, ceiling=2000)
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT {_ADVISOR_SELECT} FROM tho.[User] U "
            "JOIN tho.Current_Household_Fact F ON F.advisorid = U.User_ID "
            "WHERE U.User_ID = ? "
            "GROUP BY U.User_ID, U.Name, U.Operational_Region, U.Title, U.Email",
            user_id,
        )
        row = cursor.fetchone()
        if not row:
            cursor.close()
            return jsonify({"success": False, "error": "Advisor not found"}), 404
        advisor = _row_to_advisor(row)

        cursor.execute(
            f"SELECT TOP {limit} {_CLIENT_SELECT} {_CLIENT_FROM} "
            "WHERE F.advisorid = ? ORDER BY F.AUM DESC",
            user_id,
        )
        clients = [_row_to_client(r) for r in cursor.fetchall()]
        cursor.close()
        return jsonify({
            "success": True,
            "data": _json_safe({"advisor": advisor, "clients": clients}),
        })
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/advisors/<user_id>/book", methods=["GET"])
@_serialized
def get_advisor_book(user_id: str):
    """Book-of-business intelligence for one advisor: 12-month AUM/flow trend,
    segment mix, clients needing attention, open pipeline, outstanding RMDs,
    and open task count — everything an advisor reviews at the book level."""
    cache_key = f"book:{user_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return jsonify({"success": True, "data": cached})
    try:
        conn = _get_db_connection()
        cursor = conn.cursor()

        # 12-month AUM + net-flow trend across the whole book
        cursor.execute(
            f"SELECT TOP 12 {_FLOW_SELECT} "
            "FROM tho.Household_Rollforward R "
            "JOIN tho.Current_Household_Fact F ON F.AVHHID = R.avhhid "
            "WHERE F.advisorid = ? "
            "GROUP BY reportingperiod "
            # the current month exists as an all-zero stub until it's filled in
            "HAVING SUM(Total_Account_Value) > 0 "
            "ORDER BY reportingperiod DESC",
            user_id,
        )
        flows = [_row_to_flow(r) for r in cursor.fetchall()]
        flows.reverse()

        # Book-wide asset allocation at the latest month-end WITH data (the
        # current month exists as an all-zero stub until it's filled in)
        cursor.execute(
            f"SELECT {_ALLOC_SELECT} "
            "FROM tho.Household_Rollforward R "
            "JOIN tho.Current_Household_Fact F ON F.AVHHID = R.avhhid "
            "WHERE F.advisorid = ? AND R.reportingperiod = "
            "(SELECT MAX(reportingperiod) FROM tho.Household_Rollforward "
            "WHERE Total_Account_Value > 0)",
            user_id,
        )
        arow = cursor.fetchone()
        allocation = _allocation_from_row(arow) if arow else []

        # Segment mix
        cursor.execute(
            "SELECT D.Client_Segment, COUNT(*), SUM(F.AUM) "
            "FROM tho.Current_Household_Demographic D "
            "JOIN tho.Current_Household_Fact F ON F.LeadId = D.LeadId "
            "WHERE F.advisorid = ? GROUP BY D.Client_Segment "
            "ORDER BY SUM(F.AUM) DESC",
            user_id,
        )
        segments = [
            {"segment": _s(r[0]) or "Unassigned", "clients": _i(r[1]), "aum": _f(r[2])}
            for r in cursor.fetchall()
        ]

        # Clients needing attention: highest-AUM households with no activity in 90 days
        cursor.execute(
            "SELECT TOP 10 D.LeadId, D.Name, F.AUM, "
            "CONVERT(VARCHAR(10), MAX(AD.Created_Datetime), 23) AS last_activity "
            "FROM tho.Current_Household_Demographic D "
            "JOIN tho.Current_Household_Fact F ON F.LeadId = D.LeadId "
            "LEFT JOIN tho.Activity_Dim AD ON AD.LeadId = D.LeadId "
            "WHERE F.advisorid = ? "
            "GROUP BY D.LeadId, D.Name, F.AUM "
            "HAVING MAX(AD.Created_Datetime) IS NULL "
            "OR MAX(AD.Created_Datetime) < DATEADD(day, -90, GETDATE()) "
            "ORDER BY F.AUM DESC",
            user_id,
        )
        needs_attention = [
            {
                "lead_id": _s(r[0]),
                "name": _s(r[1]),
                "aum": _f(r[2]),
                "last_activity": _s(r[3]) or None,
                "sf_url": _sf_lead_url(_s(r[0])),
            }
            for r in cursor.fetchall()
        ]

        # Advisor's open pipeline (latest snapshot week, matched by advisor name)
        cursor.execute("SELECT Name FROM tho.[User] WHERE User_ID = ?", user_id)
        name_row = cursor.fetchone()
        advisor_name = _s(name_row[0]) if name_row else ""
        pipeline: list[dict[str, Any]] = []
        week = _latest_snapshot_week(cursor)
        if week and advisor_name:
            cursor.execute(
                f"SELECT {_OPP_SELECT} FROM tho.Pipeline_Review_Snapshot "
                "WHERE snapshot_week = ? AND advisor_name = ? "
                "ORDER BY score DESC, paum DESC",
                week, advisor_name,
            )
            pipeline = [_row_to_opp(r) for r in cursor.fetchall()]

        # Outstanding RMDs across the book
        cursor.execute(
            "SELECT COUNT(*), SUM(A.RMD_Current_Total_Amount) "
            "FROM tho.Current_Account_Demographic A "
            "JOIN tho.Current_Household_Fact F ON F.AVHHID = A.Primary_Household_ID "
            "WHERE F.advisorid = ? AND A.RMD_Current_Satisfied = 'No' "
            "AND A.RMD_Current_Total_Amount > 0",
            user_id,
        )
        r = cursor.fetchone()
        rmd_summary = {"count": _i(r[0]) if r else 0, "total": _f(r[1]) if r else 0.0}

        cursor.execute(
            "SELECT TOP 10 D.LeadId, D.Name, A.Account_Name, "
            "A.RMD_Current_Total_Amount "
            "FROM tho.Current_Account_Demographic A "
            "JOIN tho.Current_Household_Fact F ON F.AVHHID = A.Primary_Household_ID "
            "JOIN tho.Current_Household_Demographic D ON D.LeadId = F.LeadId "
            "WHERE F.advisorid = ? AND A.RMD_Current_Satisfied = 'No' "
            "AND A.RMD_Current_Total_Amount > 0 "
            "ORDER BY A.RMD_Current_Total_Amount DESC",
            user_id,
        )
        rmd_items = [
            {
                "lead_id": _s(r2[0]),
                "client_name": _s(r2[1]),
                "account_name": _s(r2[2]),
                "amount": _f(r2[3]),
            }
            for r2 in cursor.fetchall()
        ]

        # Open task count for this advisor
        cursor.execute(
            "SELECT COUNT(*) FROM tho.Activity_Dim AD "
            "JOIN tho.Activity_Fact AF ON AF.Id = AD.Id "
            "WHERE AF.OwnerId = ? AND AD.Activity_Type = 'task' "
            "AND (AD.Status IS NULL OR AD.Status <> 'Completed')",
            user_id,
        )
        open_tasks = _i(cursor.fetchone()[0])
        cursor.close()

        data = _json_safe({
            "flows": flows,
            "allocation": allocation,
            "segments": segments,
            "needs_attention": needs_attention,
            "pipeline": pipeline,
            "rmds": {**rmd_summary, "items": rmd_items},
            "open_tasks": open_tasks,
        })
        _cache_set(cache_key, data)
        return jsonify({"success": True, "data": data})
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": str(e)}), 500
