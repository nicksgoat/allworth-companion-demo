"""NCNM 2-Month Pipeline Forecast — 3-component model (Flask port).

Faithful port of ``scripts/ncnm_forecast.py`` from the wealth-mcp repo, adapted to
run synchronously inside the Flask app using the shared Synapse connection pool
(``app.get_database_connection``) instead of the async ``execute_cached`` layer.

Three components:
  A — Tail funding from recent closes (channel-specific funding cycle)
  B — Closed but not yet funded (elapsed-aware remaining tail)
  C — Active pipeline (per-prospect dwell-adjusted hazard)

``compute_forecast(conn, months_n)`` returns a JSON-serializable dict.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

import pandas as pd
from dateutil.relativedelta import relativedelta

# ---------------------------------------------------------------------------
# Constants (verbatim from the model)
# ---------------------------------------------------------------------------

FUNDING_CYCLE = [0.55, 0.25, 0.10, 0.10]

FUNDING_CYCLE_BY_CHANNEL = {
    "Advisor Driven": [0.54, 0.25, 0.10, 0.11],
    "CRP":            [0.74, 0.17, 0.02, 0.07],
    "Media Driven":   [0.59, 0.25, 0.10, 0.06],
    "Paid Leads":     [0.47, 0.33, 0.08, 0.12],
}


def get_funding_cycle(channel: str) -> list[float]:
    return FUNDING_CYCLE_BY_CHANNEL.get(channel, FUNDING_CYCLE)


DISCOVERY_CLOSE_RATE = 0.48

STALE_CAPS_BY_STAGE = {
    "5 - Discovery":                  360,
    "6 - Proposal Delivered":         300,
    "7 - Verbal Commitment Received": None,
    "8 - Onboarding":                 None,
}

CHANNEL_MIDDLES_SQL = (
    "'Beneficiary','Other','Promoter','Referral','Self-Sourced',"
    "'Fidelity','Schwab',"
    "'Other Media','Radio','Target Market',"
    "'Paid Leads'"
)


def _channel_case(alias: str) -> str:
    return f"""CASE
    WHEN {alias}.Channel_Middle IN ('Beneficiary','Other','Promoter','Referral','Self-Sourced') THEN 'Advisor Driven'
    WHEN {alias}.Channel_Middle IS NULL                                                         THEN 'Advisor Driven'
    WHEN {alias}.Channel_Middle IN ('Fidelity','Schwab')                                        THEN 'CRP'
    WHEN {alias}.Channel_Middle IN ('Other Media','Radio','Target Market')                      THEN 'Media Driven'
    WHEN {alias}.Channel_Middle = 'Paid Leads'                                                  THEN 'Paid Leads'
END"""


CHANNEL_CASE = _channel_case

ACTIVE_STAGES = (
    "'5 - Discovery','6 - Proposal Delivered',"
    "'7 - Verbal Commitment Received','8 - Onboarding'"
)

STAGE_ORDER = [
    "5 - Discovery",
    "6 - Proposal Delivered",
    "7 - Verbal Commitment Received",
    "8 - Onboarding",
]

DWELL_CAPS = {
    "5 - Discovery":                  120,
    "6 - Proposal Delivered":          90,
    "7 - Verbal Commitment Received":  30,
    "8 - Onboarding":                  60,
}
DWELL_FALLBACK = {
    "5 - Discovery":                  90,
    "6 - Proposal Delivered":         45,
    "7 - Verbal Commitment Received": 14,
    "8 - Onboarding":                 30,
}

WINSORIZE_PCT = 0.02


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

SQL_RECENT_CLOSINGS = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    FORMAT(CAST(CAST(hf.ClientSince AS VARCHAR(8)) AS DATE), 'yyyy-MM') AS close_month,
    SUM(hf.PAUM)    AS close_paum,
    COUNT(hf.AVHHID) AS clients
FROM [tho].[Current_Household_Fact] hf
INNER JOIN [tho].[Current_Household_Demographic] cd ON hf.LeadId = cd.LeadId
WHERE hf.Current_Client = 1
  AND hf.ClientSince >= 20250901
  AND hf.PAUM > 0
  AND (hf.VMAC IS NULL OR hf.VMAC = 0)
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
  AND cd.Organic = 'Organic'
GROUP BY {CHANNEL_CASE('cd')},
         FORMAT(CAST(CAST(hf.ClientSince AS VARCHAR(8)) AS DATE), 'yyyy-MM')
"""

SQL_UNFUNDED_CLOSINGS = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    FORMAT(CAST(CAST(hf.ClientSince AS VARCHAR(8)) AS DATE), 'yyyy-MM') AS close_month,
    SUM(hf.PAUM)     AS unfunded_paum,
    COUNT(hf.AVHHID) AS clients
FROM [tho].[Current_Household_Fact] hf
INNER JOIN [tho].[Current_Household_Demographic] cd ON hf.LeadId = cd.LeadId
WHERE hf.Current_Client = 1
  AND hf.ClientSince >= 20260101
  AND hf.PAUM > 0
  AND (hf.VMAC IS NULL OR hf.VMAC = 0)
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
  AND cd.Organic = 'Organic'
  AND hf.AVHHID NOT IN (
      SELECT DISTINCT avhhid FROM [tho].[Household_Rollforward]
      WHERE NCNM > 0 AND reportingperiod >= '2026-01-01'
  )
GROUP BY {CHANNEL_CASE('cd')},
         FORMAT(CAST(CAST(hf.ClientSince AS VARCHAR(8)) AS DATE), 'yyyy-MM')
"""

SQL_PIPELINE_BY_STAGE = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    cd.Stage,
    hf.LeadId,
    hf.PAUM,
    ISNULL(hf2.days_in_current_stage, 0) AS days_in_stage
FROM [tho].[Current_Household_Fact] hf
INNER JOIN [tho].[Current_Household_Demographic] cd ON hf.LeadId = cd.LeadId
INNER JOIN [tho].[hh_fact] hf2 ON cd.LeadId = hf2.Leadid
WHERE hf.Current_Client = 0
  AND (hf.VMAC IS NULL OR hf.VMAC = 0)
  AND hf.PAUM > 0
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
  AND cd.Organic = 'Organic'
  AND cd.Stage IN ({ACTIVE_STAGES})
  AND cd.NurtureCode IS NULL
  AND (cd.Rating NOT IN ('Cold','Said No') OR cd.Rating IS NULL)
  AND hf.firstappt_set_combo IS NOT NULL
"""

SQL_STAGE_CLOSE_RATES = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    CAST(SUM(CASE WHEN pf.Opp_Proposal_Delivered_Stage_Key IS NOT NULL
                  THEN 1 ELSE 0 END) AS FLOAT) AS reached_proposal,
    CAST(SUM(CASE WHEN pf.Opp_Proposal_Delivered_Stage_Key IS NOT NULL
                   AND pf.Client_Since_Key IS NOT NULL THEN 1 ELSE 0 END) AS FLOAT) AS converted_proposal,
    CAST(SUM(CASE WHEN pf.Opp_Verbal_Commitment_Rcvd_Stage_Key IS NOT NULL
                  THEN 1 ELSE 0 END) AS FLOAT) AS reached_verbal,
    CAST(SUM(CASE WHEN pf.Opp_Verbal_Commitment_Rcvd_Stage_Key IS NOT NULL
                   AND pf.Client_Since_Key IS NOT NULL THEN 1 ELSE 0 END) AS FLOAT) AS converted_verbal,
    CAST(SUM(CASE WHEN pf.Opp_Onboarding_Stage_Key IS NOT NULL
                  THEN 1 ELSE 0 END) AS FLOAT) AS reached_onboarding,
    CAST(SUM(CASE WHEN pf.Opp_Onboarding_Stage_Key IS NOT NULL
                   AND pf.Client_Since_Key IS NOT NULL THEN 1 ELSE 0 END) AS FLOAT) AS converted_onboarding
FROM [tho].[Pipeline_Fact] pf
INNER JOIN [tho].[Current_Household_Demographic] cd ON pf.LeadId = cd.LeadId
INNER JOIN [tho].[Current_Household_Fact] hf ON pf.LeadId = hf.LeadId
WHERE cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
  AND cd.Organic = 'Organic'
  AND hf.lead_created_date >= 20240101
GROUP BY {CHANNEL_CASE('cd')}
"""

SQL_STAGE_DURATIONS = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    AVG(CASE WHEN pf.Days_In_Discovery > 0
             THEN CAST(pf.Days_In_Discovery AS FLOAT) END)                  AS avg_days_discovery,
    AVG(CASE WHEN pf.Days_In_Proposal_Delivered > 0
             THEN CAST(pf.Days_In_Proposal_Delivered AS FLOAT) END)         AS avg_days_proposal,
    AVG(CASE WHEN pf.Days_In_Verbal_Commitment_Received > 0
             THEN CAST(pf.Days_In_Verbal_Commitment_Received AS FLOAT) END) AS avg_days_verbal,
    AVG(CASE WHEN pf.Days_In_Onboarding > 0
             THEN CAST(pf.Days_In_Onboarding AS FLOAT) END)                 AS avg_days_onboarding
FROM [tho].[Pipeline_Fact] pf
INNER JOIN [tho].[Current_Household_Demographic] cd ON pf.LeadId = cd.LeadId
INNER JOIN [tho].[Current_Household_Fact] hf ON pf.LeadId = hf.LeadId
WHERE pf.Client_Since_Key IS NOT NULL
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
  AND cd.Organic = 'Organic'
  AND hf.lead_created_date >= 20240101
GROUP BY {CHANNEL_CASE('cd')}
"""

SQL_NCNM_PER_CLIENT = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    hrf.avhhid,
    SUM(hrf.NCNM) AS total_ncnm,
    hf.PAUM
FROM [tho].[Household_Rollforward] hrf
INNER JOIN [tho].[Current_Household_Demographic] cd
    ON hrf.avhhid = cd.AVHHID
INNER JOIN [tho].[Current_Household_Fact] hf
    ON hrf.avhhid = hf.AVHHID
WHERE hrf.NCNM > 0
  AND hf.lead_created_date >= 20250101
  AND hf.Current_Client = 1
  AND hf.PAUM > 0
  AND cd.Organic = 'Organic'
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
  AND hrf.reportingperiod <= DATEADD(MONTH, 4,
      DATEFROMPARTS(
          hf.ClientSince / 10000,
          (hf.ClientSince / 100) % 100,
          1
      ))
GROUP BY {CHANNEL_CASE('cd')}, hrf.avhhid, hf.PAUM
"""

SQL_MONTHLY_CONVERTED_PAUM = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    FORMAT(CAST(CAST(hf.ClientSince AS VARCHAR(8)) AS DATE), 'yyyy-MM') AS convert_month,
    SUM(hf.PAUM) AS converted_paum
FROM [tho].[Current_Household_Fact] hf
INNER JOIN [tho].[Current_Household_Demographic] cd ON hf.LeadId = cd.LeadId
WHERE hf.Current_Client = 1
  AND hf.ClientSince >= 20250101
  AND (hf.VMAC IS NULL OR hf.VMAC = 0)
  AND hf.PAUM > 0
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
  AND cd.Organic = 'Organic'
GROUP BY {CHANNEL_CASE('cd')},
         FORMAT(CAST(CAST(hf.ClientSince AS VARCHAR(8)) AS DATE), 'yyyy-MM')
"""

SQL_MONTHLY_NCNM_HISTORY = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    FORMAT(hrf.reportingperiod, 'yyyy-MM') AS month,
    SUM(hrf.NCNM) AS total_ncnm
FROM [tho].[Household_Rollforward] hrf
INNER JOIN [tho].[Current_Household_Demographic] cd
    ON hrf.avhhid = cd.AVHHID
WHERE hrf.NCNM > 0
  AND hrf.reportingperiod >= '2024-07-01'
  AND cd.Organic = 'Organic'
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
GROUP BY {CHANNEL_CASE('cd')}, FORMAT(hrf.reportingperiod, 'yyyy-MM')
"""

SQL_MTD_ACTUAL = f"""
SELECT
    {CHANNEL_CASE('cd')} AS channel_group,
    SUM(hrf.NCNM) AS mtd_ncnm
FROM [tho].[Household_Rollforward] hrf
INNER JOIN [tho].[Current_Household_Demographic] cd
    ON hrf.avhhid = cd.AVHHID
CROSS JOIN (SELECT MAX(reportingperiod) AS latest FROM [tho].[Household_Rollforward]) mx
WHERE hrf.NCNM > 0
  AND hrf.reportingperiod >= DATEFROMPARTS(YEAR(mx.latest), MONTH(mx.latest), 1)
  AND hrf.reportingperiod <  DATEADD(MONTH, 1, DATEFROMPARTS(YEAR(mx.latest), MONTH(mx.latest), 1))
  AND cd.Organic = 'Organic'
  AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
GROUP BY {CHANNEL_CASE('cd')}
"""

# Latest reporting period actually loaded in the warehouse. The forecast anchors
# its "current month" to this rather than the wall clock, so a lagging monthly
# rollforward load does not zero out MTD actuals and inflate the EoM projection.
SQL_LATEST_PERIOD = """
SELECT MAX(reportingperiod) AS latest_period
FROM [tho].[Household_Rollforward]
"""

# Advisor Recruiting NCNM by month — a channel deliberately EXCLUDED from the
# forecast model (it has no discovery→close pipeline), tracked separately so the
# frontend can offer a "full firm flows" toggle that adds it 1:1 to the MTD
# actual and the EoM projection without disturbing the modeled forecast.
SQL_RECRUITING_NCNM_HISTORY = """
SELECT
    FORMAT(hrf.reportingperiod, 'yyyy-MM') AS month,
    SUM(hrf.NCNM) AS total_ncnm
FROM [tho].[Household_Rollforward] hrf
INNER JOIN [tho].[Current_Household_Demographic] cd
    ON hrf.avhhid = cd.AVHHID
WHERE hrf.NCNM > 0
  AND hrf.reportingperiod >= '2024-07-01'
  AND cd.Channel_Middle = 'Advisor Recruiting'
GROUP BY FORMAT(hrf.reportingperiod, 'yyyy-MM')
"""


# ---------------------------------------------------------------------------
# Data fetch (sync)
# ---------------------------------------------------------------------------

def _rows(cursor, sql: str) -> list[dict]:
    cursor.execute(sql)
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def fetch_all(conn) -> dict[str, list[dict]]:
    cursor = conn.cursor()
    try:
        return {
            "recent_closings":       _rows(cursor, SQL_RECENT_CLOSINGS),
            "unfunded_closings":     _rows(cursor, SQL_UNFUNDED_CLOSINGS),
            "pipeline_by_stage":     _rows(cursor, SQL_PIPELINE_BY_STAGE),
            "stage_close_rates":     _rows(cursor, SQL_STAGE_CLOSE_RATES),
            "stage_durations":       _rows(cursor, SQL_STAGE_DURATIONS),
            "ncnm_per_client":       _rows(cursor, SQL_NCNM_PER_CLIENT),
            "monthly_converted_paum": _rows(cursor, SQL_MONTHLY_CONVERTED_PAUM),
            "monthly_ncnm_history":  _rows(cursor, SQL_MONTHLY_NCNM_HISTORY),
            "mtd_actual":            _rows(cursor, SQL_MTD_ACTUAL),
            "recruiting_ncnm":       _rows(cursor, SQL_RECRUITING_NCNM_HISTORY),
            "latest_period":         _rows(cursor, SQL_LATEST_PERIOD),
        }
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Parameter builders
# ---------------------------------------------------------------------------

def build_close_rates(rows: list[dict]) -> dict[str, dict[str, float]]:
    rates: dict[str, dict[str, float]] = {}
    for r in rows:
        ch = r["channel_group"]
        if not ch:
            continue
        rates[ch] = {
            "6 - Proposal Delivered":         r["converted_proposal"]   / max(r["reached_proposal"],   1),
            "7 - Verbal Commitment Received": r["converted_verbal"]     / max(r["reached_verbal"],     1),
            "8 - Onboarding":                 r["converted_onboarding"] / max(r["reached_onboarding"], 1),
            "5 - Discovery": DISCOVERY_CLOSE_RATE,
        }
    return rates


def build_stage_durations(rows: list[dict]) -> dict[str, dict[str, float]]:
    stage_col_map = {
        "5 - Discovery":                  "avg_days_discovery",
        "6 - Proposal Delivered":         "avg_days_proposal",
        "7 - Verbal Commitment Received": "avg_days_verbal",
        "8 - Onboarding":                 "avg_days_onboarding",
    }
    durations: dict[str, dict[str, float]] = {}
    for r in rows:
        ch = r["channel_group"]
        if not ch:
            continue
        durations[ch] = {}
        for stage, col in stage_col_map.items():
            raw = r.get(col)
            cap = DWELL_CAPS[stage]
            durations[ch][stage] = min(float(raw), cap) if raw is not None else DWELL_FALLBACK[stage]
    return durations


def build_ncnm_paum_ratio(ncnm_rows: list[dict]) -> dict[str, float]:
    ncnm_by_ch: dict[str, float] = defaultdict(float)
    paum_by_ch: dict[str, float] = defaultdict(float)
    for r in ncnm_rows:
        ch = r.get("channel_group")
        if ch:
            ncnm_by_ch[ch] += float(r["total_ncnm"])
            paum_by_ch[ch] += float(r["PAUM"])
    return {ch: ncnm_by_ch[ch] / paum_by_ch[ch] for ch in ncnm_by_ch if paum_by_ch.get(ch, 0) > 0}


def build_calibrated_hazards(
    monthly_conv_rows: list[dict],
    pipeline_rows: list[dict],
    close_rates: dict[str, dict[str, float]],
    stage_durations: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    conv_by_ch: dict[str, list[float]] = defaultdict(list)
    for r in monthly_conv_rows:
        if r["channel_group"]:
            conv_by_ch[r["channel_group"]].append(float(r["converted_paum"]))
    avg_conv = {ch: sum(v) / len(v) for ch, v in conv_by_ch.items() if v}

    pipe_by_ch_stage: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    pipe_paum_ch: dict[str, float] = defaultdict(float)
    for r in pipeline_rows:
        ch = r["channel_group"]
        stage = r["Stage"]
        paum = float(r["PAUM"] or 0)
        if ch and stage:
            pipe_by_ch_stage[ch][stage] += paum
            pipe_paum_ch[ch] += paum

    actual_ch_hazard = {}
    for ch in avg_conv:
        if pipe_paum_ch.get(ch, 0) > 0:
            actual_ch_hazard[ch] = avg_conv[ch] / pipe_paum_ch[ch]

    theoretical: dict[str, dict[str, float]] = {}
    for ch in actual_ch_hazard:
        ch_rates = close_rates.get(ch, {})
        ch_dur = stage_durations.get(ch, DWELL_FALLBACK)
        theoretical[ch] = {}
        for stage in STAGE_ORDER:
            cr = ch_rates.get(stage, 0.0)
            idx = STAGE_ORDER.index(stage)
            total_days = sum(ch_dur.get(s, DWELL_FALLBACK.get(s, 30)) for s in STAGE_ORDER[idx:])
            exp_months = max(total_days / 30.0, 0.5)
            theoretical[ch][stage] = cr / exp_months

    theoretical_ch = {}
    for ch in theoretical:
        total = pipe_paum_ch.get(ch, 0)
        if total > 0:
            weighted = sum(
                theoretical[ch].get(s, 0) * pipe_by_ch_stage[ch].get(s, 0)
                for s in STAGE_ORDER
            )
            theoretical_ch[ch] = weighted / total

    result: dict[str, dict[str, float]] = {}
    for ch in actual_ch_hazard:
        th = theoretical_ch.get(ch, 0)
        scale = actual_ch_hazard[ch] / th if th > 0 else 1.0
        result[ch] = {}
        for stage in STAGE_ORDER:
            base = theoretical[ch].get(stage, 0.0)
            result[ch][stage] = base * scale
    return result


def monthly_hazard(
    stage: str,
    channel: str,
    calibrated_hazards: dict[str, dict[str, float]],
    stage_durations: dict[str, dict[str, float]],
    days_in_stage: int = 0,
) -> float:
    base = calibrated_hazards.get(channel, {}).get(stage, 0.0)
    if base <= 0:
        return 0.0
    ch_durations = stage_durations.get(channel, DWELL_FALLBACK)
    avg_stage_days = ch_durations.get(stage, DWELL_FALLBACK.get(stage, 30))
    if avg_stage_days > 0 and days_in_stage > 0:
        progress = days_in_stage / avg_stage_days
        mult = min(1.0 + progress, 2.0)
        max_rate = calibrated_hazards.get(channel, {}).get(stage, 1.0)
        return min(base * mult, max_rate * 2)
    return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    m += n
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return f"{y}-{m:02d}"


def _month_diff_ym(a: str, b: str) -> int:
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    return (ya - yb) * 12 + (ma - mb)


def _latest_period_ym(data: dict) -> str | None:
    """Latest reporting-period month (yyyy-MM) actually present in the warehouse.

    Prefers the dedicated MAX(reportingperiod) probe; falls back to the newest
    month in the monthly NCNM history. Returns None only when both are empty.
    """
    for r in data.get("latest_period", []):
        lp = r.get("latest_period")
        if lp is not None:
            try:
                return lp.strftime("%Y-%m")
            except AttributeError:
                return str(lp)[:7]
    months = [r.get("month") for r in data.get("monthly_ncnm_history", []) if r.get("month")]
    return max(months) if months else None


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def component_a(recent_closings, ncnm_paum, forecast_months) -> pd.DataFrame:
    records = []
    for r in recent_closings:
        ch = r["channel_group"]
        close_month = r["close_month"]
        paum = float(r["close_paum"] or 0)
        if paum <= 0 or ch not in ncnm_paum:
            continue
        ratio = ncnm_paum[ch]
        base = paum * ratio
        cycle = get_funding_cycle(ch)
        for offset, frac in enumerate(cycle):
            if offset == 0:
                continue
            try:
                recv_month = _add_months(close_month, offset)
            except Exception:
                continue
            if recv_month not in forecast_months:
                continue
            records.append({
                "component": "A - Tail Funding",
                "forecast_month": recv_month,
                "channel": ch,
                "close_month": close_month,
                "paum": paum,
                "ncnm_paum_ratio": ratio,
                "expected_ncnm": base * frac,
            })
    return pd.DataFrame(records)


def component_b(unfunded_closings, ncnm_paum, forecast_months) -> pd.DataFrame:
    records = []
    first_forecast = forecast_months[0]
    for r in unfunded_closings:
        ch = r["channel_group"]
        close_month = r["close_month"]
        paum = float(r["unfunded_paum"] or 0)
        if paum <= 0 or ch not in ncnm_paum:
            continue
        ratio = ncnm_paum[ch]
        base = paum * ratio
        cycle = get_funding_cycle(ch)
        elapsed = _month_diff_ym(first_forecast, close_month)
        for fc_idx in range(len(cycle)):
            forecast_offset = fc_idx - elapsed
            if forecast_offset < 0:
                continue
            if forecast_offset >= len(forecast_months):
                break
            recv_month = forecast_months[forecast_offset]
            records.append({
                "component": "B - Unfunded Closes",
                "forecast_month": recv_month,
                "channel": ch,
                "close_month": close_month,
                "paum": paum,
                "ncnm_paum_ratio": ratio,
                "expected_ncnm": base * cycle[fc_idx],
            })
    return pd.DataFrame(records)


def component_c(pipeline_rows, calibrated_hazards, ncnm_paum, stage_durations, forecast_months) -> pd.DataFrame:
    bucket_ncnm: dict[tuple, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    bucket_meta: dict[tuple, dict] = {}

    for r in pipeline_rows:
        ch = r["channel_group"]
        stage = r["Stage"]
        paum = float(r["PAUM"] or 0)
        days = int(r.get("days_in_stage") or 0)
        if paum <= 0 or ch not in ncnm_paum:
            continue
        if stage not in STAGE_ORDER:
            continue
        stale_cap = STALE_CAPS_BY_STAGE.get(stage)
        if stale_cap is not None and days > stale_cap:
            continue
        ratio = ncnm_paum[ch]
        h = monthly_hazard(stage, ch, calibrated_hazards, stage_durations, days_in_stage=days)
        if h <= 0:
            continue
        close_prob = [h] + [h * (1 - h) ** i for i in range(1, len(forecast_months))]
        base_ncnm = paum * ratio
        cycle = get_funding_cycle(ch)

        monthly_ncnm: dict[str, float] = {}
        for close_idx, cp in enumerate(close_prob):
            for fund_offset, fund_frac in enumerate(cycle):
                recv_idx = close_idx + fund_offset
                if recv_idx >= len(forecast_months):
                    break
                label = forecast_months[recv_idx]
                monthly_ncnm[label] = monthly_ncnm.get(label, 0.0) + base_ncnm * cp * fund_frac

        key = (ch, stage)
        if key not in bucket_meta:
            bucket_meta[key] = {"prospects": 0, "paum": 0.0, "hazard_sum": 0.0}
        bucket_meta[key]["prospects"] += 1
        bucket_meta[key]["paum"] += paum
        bucket_meta[key]["hazard_sum"] += h
        for recv_month, ncnm_val in monthly_ncnm.items():
            bucket_ncnm[key][recv_month] += ncnm_val

    records = []
    for (ch, stage), month_vals in bucket_ncnm.items():
        meta = bucket_meta[(ch, stage)]
        avg_h = meta["hazard_sum"] / meta["prospects"] if meta["prospects"] else 0
        for recv_month, ncnm_val in month_vals.items():
            if ncnm_val <= 0:
                continue
            records.append({
                "component": "C - Pipeline",
                "forecast_month": recv_month,
                "channel": ch,
                "stage": stage,
                "paum": meta["paum"],
                "prospects": meta["prospects"],
                "hazard": avg_h,
                "ncnm_paum_ratio": ncnm_paum[ch],
                "expected_ncnm": ncnm_val,
            })
    return pd.DataFrame(records)


def build_volatility(history_rows: list[dict]) -> dict[str, float]:
    by_ch: dict[str, list[float]] = defaultdict(list)
    for r in history_rows:
        ch = r.get("channel_group")
        ncnm = float(r.get("total_ncnm") or 0)
        if ch and ncnm > 0:
            by_ch[ch].append(ncnm)

    result: dict[str, float] = {}
    for ch, vals in by_ch.items():
        if len(vals) < 3:
            result[ch] = 0.25
            continue
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)
        std = math.sqrt(variance)
        result[ch] = std / mean if mean > 0 else 0.25

    monthly_totals: dict[str, float] = defaultdict(float)
    for r in history_rows:
        month = r.get("month")
        ncnm = float(r.get("total_ncnm") or 0)
        if month and ncnm > 0:
            monthly_totals[month] += ncnm
    totals = list(monthly_totals.values())
    if len(totals) >= 3:
        mean = sum(totals) / len(totals)
        variance = sum((v - mean) ** 2 for v in totals) / (len(totals) - 1)
        result["_total"] = math.sqrt(variance) / mean if mean > 0 else 0.20
    else:
        result["_total"] = 0.20
    return result


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def compute_forecast(conn, months_n: int = 1) -> dict:
    """Run the 3-component NCNM forecast and return a JSON-serializable dict."""
    data = fetch_all(conn)

    # Anchor the "current month" to the latest reporting period loaded in the
    # warehouse, not the wall clock. The monthly rollforward can lag the calendar
    # by a month or more; keying MTD/forecast off GETDATE() then yields an empty
    # current month ($0 MTD) and a doubled EoM projection. When the warehouse is
    # current, the anchor equals the calendar month and behavior is unchanged.
    anchor_ym = _latest_period_ym(data) or date.today().strftime("%Y-%m")
    anchor = date(int(anchor_ym[:4]), int(anchor_ym[5:7]), 1)
    core_months = [_add_months(anchor_ym, i) for i in range(0, months_n)]
    all_months = [_add_months(anchor_ym, i) for i in range(0, months_n + len(FUNDING_CYCLE))]

    close_rates = build_close_rates(data["stage_close_rates"])
    stage_durations = build_stage_durations(data["stage_durations"])
    ncnm_paum = build_ncnm_paum_ratio(data["ncnm_per_client"])
    cal_hazards = build_calibrated_hazards(
        data["monthly_converted_paum"], data["pipeline_by_stage"],
        close_rates, stage_durations,
    )

    df_a = component_a(data["recent_closings"], ncnm_paum, all_months)
    df_b = component_b(data["unfunded_closings"], ncnm_paum, all_months)
    df_c = component_c(data["pipeline_by_stage"], cal_hazards, ncnm_paum, stage_durations, all_months)
    df = pd.concat([df_a, df_b, df_c], ignore_index=True)

    vol = build_volatility(data["monthly_ncnm_history"])
    mtd_actual = sum(float(r.get("mtd_ncnm") or 0) for r in data["mtd_actual"])

    if df.empty:
        core = df
    else:
        core = df[df["forecast_month"].isin(core_months)]

    grand_total = float(core["expected_ncnm"].sum()) if not core.empty else 0.0
    total_cv = vol.get("_total", 0.20)
    low = grand_total * (1 - 0.675 * total_cv)
    high = grand_total * (1 + 0.675 * total_cv)

    remaining = max(0.0, grand_total - mtd_actual)
    eom_projection = mtd_actual + remaining

    # By channel
    by_channel = []
    if not core.empty:
        for ch in sorted(core["channel"].dropna().unique()):
            ch_total = float(core[core["channel"] == ch]["expected_ncnm"].sum())
            cv = vol.get(ch, 0.20)
            by_channel.append({
                "channel": ch,
                "projection": ch_total,
                "p25": ch_total * (1 - 0.675 * cv),
                "p75": ch_total * (1 + 0.675 * cv),
                "cv": cv,
            })

    # By component
    component_defs = [
        ("A - Tail Funding", "A", "Tail Funding", "Recently closed clients with assets still in transit."),
        ("B - Unfunded Closes", "B", "Unfunded Closes", "Clients closed but no NCNM in rollforward yet."),
        ("C - Pipeline", "C", "Active Pipeline", "Unconverted prospects expected to close and fund."),
    ]
    by_component = []
    for comp_key, letter, label, desc in component_defs:
        comp_total = 0.0
        if not core.empty:
            comp_total = float(core[core["component"] == comp_key]["expected_ncnm"].sum())
        by_component.append({"component": letter, "label": label, "total": comp_total, "description": desc})

    # Component detail
    detail: dict[str, list[dict]] = {"A": [], "B": [], "C": []}
    if not core.empty:
        for comp_key, letter in (("A - Tail Funding", "A"), ("B - Unfunded Closes", "B")):
            cdf = core[core["component"] == comp_key].sort_values(["channel", "close_month"])
            for _, r in cdf.iterrows():
                detail[letter].append({
                    "channel": r["channel"],
                    "close_month": r.get("close_month", ""),
                    "paum": float(r["paum"]),
                    "ncnm_paum_ratio": float(r.get("ncnm_paum_ratio", 0) or 0),
                    "expected_ncnm": float(r["expected_ncnm"]),
                })
        cdf = core[core["component"] == "C - Pipeline"]
        if not cdf.empty:
            grouped = (
                cdf.groupby(["channel", "stage"])
                .agg(prospects=("prospects", "first"),
                     paum=("paum", "first"),
                     expected_ncnm=("expected_ncnm", "sum"))
                .reset_index()
                .sort_values("expected_ncnm", ascending=False)
            )
            for _, r in grouped.iterrows():
                detail["C"].append({
                    "channel": r["channel"],
                    "stage": r["stage"],
                    "prospects": int(r["prospects"]),
                    "paum": float(r["paum"]),
                    "expected_ncnm": float(r["expected_ncnm"]),
                })

    end_of_month = (anchor + relativedelta(months=1) - relativedelta(days=1))

    # Tail (this calendar month) vs opening (next calendar month) — a 30-day-ish
    # forward view derived from the same run, without changing the primary
    # single-month projection above.
    by_period = []
    if core_months:
        period_months = [core_months[0], _add_months(core_months[0], 1)]
        labels = ["This month (tail)", "Next month (opening)"]
        comp_keys = [("A - Tail Funding", "A"), ("B - Unfunded Closes", "B"), ("C - Pipeline", "C")]
        for m, lbl in zip(period_months, labels):
            mdf = df[df["forecast_month"] == m] if not df.empty else df
            total = float(mdf["expected_ncnm"].sum()) if not mdf.empty else 0.0
            comp_split = {
                letter: (float(mdf[mdf["component"] == key]["expected_ncnm"].sum())
                         if not mdf.empty else 0.0)
                for key, letter in comp_keys
            }
            by_period.append({"month": m, "label": lbl, "total": total, "by_component": comp_split})
    forward_30day_total = sum(p["total"] for p in by_period)

    # Trailing monthly NCNM actuals (for the forecast-vs-actual chart). Exclude
    # the anchor month — it is the current in-progress month (MTD) shown
    # separately as the actual-so-far + forecast-remaining projection bar.
    cur_month_ym = anchor_ym
    hist_by_month: dict[str, float] = defaultdict(float)
    for r in data["monthly_ncnm_history"]:
        m = r.get("month")
        if m and m != cur_month_ym:
            hist_by_month[m] += float(r.get("total_ncnm") or 0)
    monthly_history = [
        {"month": m, "actual": hist_by_month[m]} for m in sorted(hist_by_month)[-8:]
    ]

    # Advisor Recruiting NCNM — excluded from the model above; surfaced separately
    # so the frontend "full firm flows" toggle can add it 1:1 to the MTD actual,
    # the EoM projection, and the trailing-actual bars without changing anything else.
    recruiting_by_month: dict[str, float] = defaultdict(float)
    for r in data["recruiting_ncnm"]:
        m = r.get("month")
        if m:
            recruiting_by_month[m] += float(r.get("total_ncnm") or 0)
    recruiting_mtd = recruiting_by_month.get(cur_month_ym, 0.0)
    recruiting_history = {m: v for m, v in recruiting_by_month.items() if m != cur_month_ym}

    return {
        "as_of": end_of_month.isoformat(),
        "period_label": f"{anchor.strftime('%b %d')} - {end_of_month.strftime('%b %d, %Y')}",
        "forecast_months": core_months,
        "mtd_actual": mtd_actual,
        "remaining_expected": remaining,
        "eom_projection": eom_projection,
        "grand_total": grand_total,
        "confidence": {"cv": total_cv, "low": low, "high": high},
        "by_channel": by_channel,
        "by_component": by_component,
        "by_period": by_period,
        "forward_30day_total": forward_30day_total,
        "monthly_history": monthly_history,
        "component_detail": detail,
        "ncnm_paum_ratio": {ch: ncnm_paum[ch] for ch in sorted(ncnm_paum)},
        "recruiting": {
            "label": "Advisor Recruiting",
            "mtd": recruiting_mtd,
            "by_month": recruiting_history,
        },
    }


def compute_closes_by_advisor(conn, top_n: int = 10) -> list[dict]:
    """Advisors ranked by new-client PAUM closed month-to-date, with all NCNM
    booked to date for those same closed households.

    Grounded on the same tables/filters as the NCNM closings queries; NCNM is the
    full ``Household_Rollforward`` total (across all reporting periods) for the
    households that closed this month. Called defensively by the route so a schema
    mismatch hides the section rather than breaking the report.
    """
    today = date.today()
    first_of_month = int(today.replace(day=1).strftime("%Y%m%d"))
    today_key = int(today.strftime("%Y%m%d"))
    sql = f"""
    SELECT TOP {int(top_n)}
        ISNULL(u.Name, 'Unknown') AS advisor,
        COUNT(DISTINCT hf.AVHHID) AS clients,
        SUM(hf.PAUM) AS paum,
        SUM(ISNULL(rf.ncnm, 0)) AS ncnm
    FROM [tho].[Current_Household_Fact] hf
    INNER JOIN [tho].[Current_Household_Demographic] cd ON hf.LeadId = cd.LeadId
    LEFT JOIN [tho].[User] u ON hf.advisorid = u.User_ID
    LEFT JOIN (
        SELECT avhhid, SUM(NCNM) AS ncnm
        FROM [tho].[Household_Rollforward]
        WHERE NCNM > 0
        GROUP BY avhhid
    ) rf ON hf.AVHHID = rf.avhhid
    WHERE hf.Current_Client = 1
      AND hf.ClientSince >= {first_of_month}
      AND hf.ClientSince <= {today_key}
      AND hf.PAUM > 0
      AND (hf.VMAC IS NULL OR hf.VMAC = 0)
      AND cd.Channel_Middle IN ({CHANNEL_MIDDLES_SQL})
      AND cd.Organic = 'Organic'
    GROUP BY u.Name
    ORDER BY SUM(hf.PAUM) DESC
    """
    cursor = conn.cursor()
    try:
        rows = _rows(cursor, sql)
    finally:
        cursor.close()

    return [
        {
            "advisor": r["advisor"],
            "clients": int(r["clients"] or 0),
            "paum": float(r["paum"] or 0),
            "ncnm": float(r["ncnm"] or 0),
        }
        for r in rows
    ]

