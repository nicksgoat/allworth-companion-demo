"""Monthly flows forecast — ECNM / Distributions / Attrition / Expenses.

Predicts the current in-progress month's book flows without relying on the
partial current-month rollforward load. All history uses COMPLETE months only
(``reportingperiod`` strictly before the target month), so a half-loaded current
month never distorts the estimate.

Channels use the same buildout as the NCNM model — ``Channel_Middle`` mapped via
``CHANNEL_CASE`` (joined to the household demographic on ``avhhid``), not the
(empty) ``Marketing_Channel`` column on the rollforward.

Method
------
* ECNM and Distributions (per channel) — a 50/50 blend of:
    (A) seasonal-trend: deseasonalize the channel's monthly total series, take a
        weighted recent level (0.6 * last 3m + 0.4 * last 12m), reseasonalize to
        the target calendar month; and
    (B) funding-cycle: sum over TAV-size bands of the last complete month's
        household count times each band's pooled per-household flow rate over a
        recent window. This grounds the estimate in the current book composition
        and each size cohort's characteristic funding behavior.
* Attrition and Expenses (firm total) — seasonal-trend only. Attrition is lumpy
  and size-banding adds noise, so seasonality + trend is used as specified.

``compute_flows_forecast(conn, target_ym)`` returns a JSON-serializable dict of
raw-dollar predictions (per channel and firm total) plus method metadata.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHANNELS = ["Advisor Driven", "CRP", "Media Driven", "Paid Leads"]

# NCNM channel buildout (verbatim mapping from executive_report.ncnm_model).
CHANNEL_CASE = """CASE
    WHEN cd.Channel_Middle IN ('Beneficiary','Other','Promoter','Referral','Self-Sourced') THEN 'Advisor Driven'
    WHEN cd.Channel_Middle IS NULL                                                         THEN 'Advisor Driven'
    WHEN cd.Channel_Middle IN ('Fidelity','Schwab')                                        THEN 'CRP'
    WHEN cd.Channel_Middle IN ('Other Media','Radio','Target Market')                      THEN 'Media Driven'
    WHEN cd.Channel_Middle = 'Paid Leads'                                                  THEN 'Paid Leads'
    ELSE 'Advisor Driven'
END"""

# Household size bands on end-of-month Total_Account_Value.
BAND_CASE = """CASE
    WHEN rf.Total_Account_Value <  250000 THEN '1_lt250k'
    WHEN rf.Total_Account_Value <  500000 THEN '2_250_500k'
    WHEN rf.Total_Account_Value < 1000000 THEN '3_500k_1M'
    WHEN rf.Total_Account_Value < 2500000 THEN '4_1_2.5M'
    WHEN rf.Total_Account_Value < 5000000 THEN '5_2.5_5M'
    ELSE '6_5M+'
END"""

HISTORY_START = "2024-01-01"   # earliest reporting period to pull
RATE_WINDOW = 6                # months for funding-cycle per-HH rates
SEAS_SHRINK = 2.0              # shrink seasonal index toward 1.0 (limited history)
BLEND_W = 0.5                  # weight on seasonal-trend vs funding-cycle

METHOD_LABEL = "seasonal-trend + TAV funding-cycle blend"


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

def _sql_channel_month() -> str:
    return f"""
    SELECT {CHANNEL_CASE} AS channel,
           FORMAT(rf.reportingperiod,'yyyy-MM') AS ym,
           SUM(ISNULL(rf.ECNM,0))         AS ecnm,
           SUM(ISNULL(rf.Distribution,0)) AS dist,
           SUM(ISNULL(rf.Attrition,0))    AS attr,
           SUM(ISNULL(rf.expenses,0))     AS expenses,
           COUNT(*)                       AS hh
    FROM tho.Household_Rollforward rf
    LEFT JOIN tho.Current_Household_Demographic cd ON rf.avhhid = cd.AVHHID
    WHERE rf.reportingperiod >= '{HISTORY_START}'
    GROUP BY {CHANNEL_CASE}, FORMAT(rf.reportingperiod,'yyyy-MM')
    """


def _sql_channel_band_month() -> str:
    return f"""
    SELECT {CHANNEL_CASE} AS channel,
           {BAND_CASE}    AS band,
           FORMAT(rf.reportingperiod,'yyyy-MM') AS ym,
           SUM(ISNULL(rf.ECNM,0))         AS ecnm,
           SUM(ISNULL(rf.Distribution,0)) AS dist,
           COUNT(*)                       AS hh
    FROM tho.Household_Rollforward rf
    LEFT JOIN tho.Current_Household_Demographic cd ON rf.avhhid = cd.AVHHID
    WHERE rf.reportingperiod >= '{HISTORY_START}'
    GROUP BY {CHANNEL_CASE}, {BAND_CASE}, FORMAT(rf.reportingperiod,'yyyy-MM')
    """


# ---------------------------------------------------------------------------
# Model helpers
# ---------------------------------------------------------------------------

def _seasonal_index(series_by_ym: dict[str, float], target_month: int) -> float:
    """Shrunk month-of-year index for ``target_month`` from a {ym: value} series."""
    by_m: dict[int, list[float]] = {}
    for ym, v in series_by_ym.items():
        by_m.setdefault(int(ym[5:7]), []).append(v)
    all_vals = [v for vs in by_m.values() for v in vs]
    overall = float(np.mean(all_vals)) if all_vals else 0.0
    if overall == 0:
        return 1.0
    obs = by_m.get(target_month, [])
    raw = (float(np.mean(obs)) / overall) if obs else 1.0
    n = len(obs)
    return (n * raw + SEAS_SHRINK) / (n + SEAS_SHRINK)


def _seasonal_trend(series_by_ym: dict[str, float], target_ym: str) -> float:
    """Deseasonalize -> weighted recent level -> reseasonalize to target month."""
    months = sorted(series_by_ym)
    if not months:
        return 0.0
    idx = {m: _seasonal_index(series_by_ym, int(m[5:7])) for m in months}
    desees = [series_by_ym[m] / (idx[m] or 1.0) for m in months]
    last3 = float(np.mean(desees[-3:]))
    last12 = float(np.mean(desees[-12:]))
    level = 0.6 * last3 + 0.4 * last12
    return level * _seasonal_index(series_by_ym, int(target_ym[5:7]))


def _funding_cycle(cb: pd.DataFrame, channel: str, metric: str,
                   window_months: list[str], book_ym: str) -> float:
    """Sum over bands of book_HH[ch,band] * pooled per-HH rate over the window."""
    sub = cb[(cb["channel"] == channel) & (cb["ym"].isin(window_months))]
    if sub.empty:
        return 0.0
    flow = sub.groupby("band")[metric].sum()
    heads = sub.groupby("band")["hh"].sum()
    rates = (flow / heads.replace(0, np.nan)).fillna(0.0)
    book = cb[(cb["channel"] == channel) & (cb["ym"] == book_ym)].set_index("band")["hh"]
    return float(sum(hh * rates.get(band, 0.0) for band, hh in book.items()))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_flows_forecast(conn, target_ym: str | None = None) -> dict:
    """Predict ECNM / Distributions / Attrition / Expenses for ``target_ym``.

    ``target_ym`` defaults to the current calendar month. Returns raw-dollar
    predictions (per channel and firm total) plus method metadata.
    """
    if target_ym is None:
        today = date.today()
        target_ym = f"{today.year:04d}-{today.month:02d}"

    cm = pd.read_sql(_sql_channel_month(), conn)
    cb = pd.read_sql(_sql_channel_band_month(), conn)

    complete = sorted(m for m in cm["ym"].unique() if m < target_ym)
    if not complete:
        raise RuntimeError("flows-model: no complete months before target")
    book_ym = complete[-1]
    rate_window = complete[-RATE_WINDOW:]

    ecnm_by: dict[str, float] = {}
    dist_by: dict[str, float] = {}
    for ch in CHANNELS:
        cmc = cm[(cm["channel"] == ch) & (cm["ym"].isin(complete))]
        for metric, dest in (("ecnm", ecnm_by), ("dist", dist_by)):
            series = dict(zip(cmc["ym"], cmc[metric].astype(float)))
            st = _seasonal_trend(series, target_ym)
            fc = _funding_cycle(cb, ch, metric, rate_window, book_ym)
            dest[ch] = BLEND_W * st + (1.0 - BLEND_W) * fc

    # Firm-total seasonal-trend for attrition and expenses.
    complete_cm = cm[cm["ym"].isin(complete)]
    attr_series = dict(complete_cm.groupby("ym")["attr"].sum().astype(float))
    exp_series = dict(complete_cm.groupby("ym")["expenses"].sum().astype(float))
    attr_total = _seasonal_trend(attr_series, target_ym)
    exp_total = _seasonal_trend(exp_series, target_ym)

    return {
        "target_ym": target_ym,
        "book_ym": book_ym,
        "method": METHOD_LABEL,
        "ecnm": {"total": float(sum(ecnm_by.values())), "by_channel": ecnm_by},
        "distributions": {"total": float(sum(dist_by.values())), "by_channel": dist_by},
        "attrition": {"total": float(attr_total)},
        "expenses": {"total": float(exp_total)},
    }
