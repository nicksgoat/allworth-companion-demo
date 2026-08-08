"""Company flows — appointments, PAUM, and conversion funnel YoY (Flask port).

Port of ``scripts/_ceo_flows_report.py``. The original hardcoded a fixed
Jan 1 – Apr 23 window across 2025 vs 2026; here the window is dynamic: current
year vs prior year, Jan 1 through today's month/day, so the page always reflects
a true year-to-date comparison.

``compute_flows(conn)`` returns a JSON-serializable dict.
"""

from __future__ import annotations

from datetime import date


# Channel_Middle values that roll up into the "Advisor Driven" super-channel.
_ADVISOR_DRIVEN = (
    "'referral','crp','advisor self-sourced','self-sourced','external referral',"
    "'custodial referral','internal referral','advisor driven',"
    "'other','promoter','beneficiary'"
)


def _rows(cursor, sql: str) -> list[dict]:
    cursor.execute(sql)
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, r)) for r in cursor.fetchall()]


def _fnum(x) -> float:
    try:
        return float(x) if x is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


# Channels considered "media / paid" for the advisor-concentration lens (BDO
# first-appointment takers), mirroring query #6 of the source CEO flows script.
_MEDIA_PAID_CHANNELS = "'paid leads','radio','other media','target market'"


def _compute_engagement(conn, cur_start, cur_end, prior_start, prior_end,
                        cur_y, prior_y, today) -> dict:
    """Client engagement events (annual reviews + general appointments) YoY, plus
    current-month pacing so the page can surface the April-style activity cliff.

    Grounded on ``tho.Activity_Fact`` + ``tho.Activity_Dim`` (completed client
    activities). Wrapped defensively by the caller: if the classification columns
    differ in the warehouse this returns empty and the section is simply hidden.
    """
    cursor = conn.cursor()
    try:
        by_type = _rows(cursor, f"""
        SELECT
            YEAR(da.Date) AS EvtYear,
            CASE WHEN LOWER(ISNULL(ad.Subject, '')) LIKE '%annual%review%'
                      OR LOWER(ISNULL(ad.Activity_Type, '')) LIKE '%annual%review%'
                 THEN 'Annual Review' ELSE 'General Appointment' END AS EvtType,
            COUNT(*) AS Events
        FROM tho.Activity_Fact af
        JOIN tho.Activity_Dim ad ON af.Id = ad.Id
        JOIN aip.DateDimension da ON af.CompletedDateKey = da.DateKey
        WHERE ad.Status IN ('Completed','Closed')
          AND (
                LOWER(ISNULL(ad.Activity_Type, '')) IN ('appointment','meeting','event')
             OR LOWER(ISNULL(ad.Subject, '')) LIKE '%appointment%'
             OR LOWER(ISNULL(ad.Subject, '')) LIKE '%review%'
          )
          AND ((da.Date >= '{prior_start}' AND da.Date <= '{prior_end}')
            OR (da.Date >= '{cur_start}'   AND da.Date <= '{cur_end}'))
        GROUP BY YEAR(da.Date),
            CASE WHEN LOWER(ISNULL(ad.Subject, '')) LIKE '%annual%review%'
                      OR LOWER(ISNULL(ad.Activity_Type, '')) LIKE '%annual%review%'
                 THEN 'Annual Review' ELSE 'General Appointment' END
        """)

        # Current-month pace: same month-to-date window in both years.
        month_start_cur = today.replace(day=1).isoformat()
        month_start_prior = today.replace(year=prior_y, day=1).isoformat()
        md = today.strftime("%m-%d")
        month_pace = _rows(cursor, f"""
        SELECT YEAR(da.Date) AS EvtYear, COUNT(*) AS Events
        FROM tho.Activity_Fact af
        JOIN tho.Activity_Dim ad ON af.Id = ad.Id
        JOIN aip.DateDimension da ON af.CompletedDateKey = da.DateKey
        WHERE ad.Status IN ('Completed','Closed')
          AND (
                LOWER(ISNULL(ad.Activity_Type, '')) IN ('appointment','meeting','event')
             OR LOWER(ISNULL(ad.Subject, '')) LIKE '%appointment%'
             OR LOWER(ISNULL(ad.Subject, '')) LIKE '%review%'
          )
          AND ((da.Date >= '{month_start_prior}' AND da.Date <= '{prior_y}-{md}')
            OR (da.Date >= '{month_start_cur}'   AND da.Date <= '{cur_y}-{md}'))
        GROUP BY YEAR(da.Date)
        """)
    finally:
        cursor.close()

    totals = {cur_y: 0, prior_y: 0}
    by_type_out: dict[str, dict[str, int]] = {}
    for r in by_type:
        yr = int(r["EvtYear"]); typ = r["EvtType"]; n = int(r["Events"] or 0)
        totals[yr] = totals.get(yr, 0) + n
        by_type_out.setdefault(typ, {"current": 0, "prior": 0})
        by_type_out[typ]["current" if yr == cur_y else "prior"] += n

    pace = {cur_y: 0, prior_y: 0}
    for r in month_pace:
        pace[int(r["EvtYear"])] = int(r["Events"] or 0)

    def _pct(cur, prior):
        return ((cur - prior) / prior) if prior else None

    return {
        "current_year": cur_y,
        "prior_year": prior_y,
        "events_current": totals.get(cur_y, 0),
        "events_prior": totals.get(prior_y, 0),
        "events_yoy_pct": _pct(totals.get(cur_y, 0), totals.get(prior_y, 0)),
        "by_type": [
            {"type": t, "current": v["current"], "prior": v["prior"],
             "yoy_pct": _pct(v["current"], v["prior"])}
            for t, v in sorted(by_type_out.items())
        ],
        "current_month_label": today.strftime("%B"),
        "month_pace_current": pace.get(cur_y, 0),
        "month_pace_prior": pace.get(prior_y, 0),
        "month_pace_yoy_pct": _pct(pace.get(cur_y, 0), pace.get(prior_y, 0)),
    }


def _compute_top_advisors(conn, cur_y, today) -> list[dict]:
    """Top advisors by prospect PAUM in media/paid channels (BDO first-appointment
    takers), with post-hand-off A2C. Port of query #6 of the source script, with a
    dynamic YTD upper bound instead of the hardcoded Apr 16."""
    ymd = int(today.strftime("%Y%m%d"))
    jan1 = int(f"{cur_y}0101")
    cursor = conn.cursor()
    try:
        rows = _rows(cursor, f"""
        WITH advisor_top_ch AS (
            SELECT advisorid, Channel,
                   ROW_NUMBER() OVER (PARTITION BY advisorid ORDER BY cnt DESC) AS rn
            FROM (
                SELECT f.firstappt_advisorid AS advisorid,
                       ISNULL(d.Channel_Middle, 'Unknown') AS Channel,
                       COUNT(*) AS cnt
                FROM tho.Current_Household_Fact f
                JOIN tho.Current_Household_Demographic d ON f.LeadId = d.LeadId
                WHERE f.firstappt_comp_combo >= {jan1}
                  AND f.firstappt_comp_combo <= {ymd}
                  AND LOWER(ISNULL(d.Channel_Middle, '')) IN ({_MEDIA_PAID_CHANNELS})
                GROUP BY f.firstappt_advisorid, ISNULL(d.Channel_Middle, 'Unknown')
            ) sub
        )
        SELECT TOP 12
            ISNULL(u.Name, 'Unknown') AS Advisor,
            atc.Channel AS TopChannel,
            COUNT(*) AS Appts,
            COUNT(CASE WHEN f.ClientSince IS NOT NULL
                        AND f.ClientSince >= {jan1} AND f.ClientSince <= {ymd}
                        AND f.firstappt_comp_combo >= {jan1} THEN 1 END) AS Clients,
            CAST(COUNT(CASE WHEN f.ClientSince IS NOT NULL
                        AND f.ClientSince >= {jan1} AND f.ClientSince <= {ymd}
                        AND f.firstappt_comp_combo >= {jan1} THEN 1 END) AS FLOAT)
                / NULLIF(COUNT(*), 0) AS A2C_Rate,
            SUM(ISNULL(f.paum, 0)) AS PAUM
        FROM tho.Current_Household_Fact f
        JOIN tho.Current_Household_Demographic d ON f.LeadId = d.LeadId
        LEFT JOIN tho.[User] u ON f.firstappt_advisorid = u.User_ID
        LEFT JOIN advisor_top_ch atc ON f.firstappt_advisorid = atc.advisorid AND atc.rn = 1
        WHERE f.firstappt_comp_combo >= {jan1}
          AND f.firstappt_comp_combo <= {ymd}
          AND LOWER(ISNULL(d.Channel_Middle, '')) IN ({_MEDIA_PAID_CHANNELS})
        GROUP BY u.Name, atc.Channel
        HAVING COUNT(*) >= 5
        ORDER BY SUM(ISNULL(f.paum, 0)) DESC
        """)
    finally:
        cursor.close()
    return [
        {"advisor": r["Advisor"], "top_channel": r["TopChannel"],
         "appts": int(r["Appts"] or 0), "clients": int(r["Clients"] or 0),
         "a2c_rate": _fnum(r["A2C_Rate"]), "paum": _fnum(r["PAUM"])}
        for r in rows
    ]


def _compute_aum_flows(conn, cur_y, prior_y) -> dict:
    """Firm-level AUM bridge headlines from ``tho.Household_Rollforward``.

    - BoP AUM: total account value at the Dec-31 reporting period of the prior year.
    - Current AUM: total account value at the latest reporting period.
    - Net flows YTD: SUM(NCNM + ECNM + Distribution + expenses + Attrition) across
      current-year periods, with a prior-year same-months comparison.
    """
    cursor = conn.cursor()
    try:
        rows = _rows(cursor, f"""
        SELECT
          (SELECT SUM(Total_Account_Value) FROM tho.Household_Rollforward
            WHERE reportingperiod = (SELECT MAX(reportingperiod) FROM tho.Household_Rollforward
                                     WHERE reportingperiod <= '{prior_y}-12-31')) AS bop_aum,
          (SELECT SUM(Total_Account_Value) FROM tho.Household_Rollforward
            WHERE reportingperiod = (SELECT MAX(reportingperiod) FROM tho.Household_Rollforward
                                     WHERE YEAR(reportingperiod) = {cur_y})) AS current_aum,
          (SELECT SUM(ISNULL(NCNM,0) + ISNULL(ECNM,0) + ISNULL(Distribution,0)
                    + ISNULL(expenses,0) + ISNULL(Attrition,0))
             FROM tho.Household_Rollforward WHERE YEAR(reportingperiod) = {cur_y}) AS net_flows_cur,
          (SELECT SUM(ISNULL(NCNM,0) + ISNULL(ECNM,0) + ISNULL(Distribution,0)
                    + ISNULL(expenses,0) + ISNULL(Attrition,0))
             FROM tho.Household_Rollforward
            WHERE YEAR(reportingperiod) = {prior_y}
              AND MONTH(reportingperiod) <= (SELECT MONTH(MAX(reportingperiod))
                                             FROM tho.Household_Rollforward
                                             WHERE YEAR(reportingperiod) = {cur_y})) AS net_flows_prior,
          (SELECT MAX(reportingperiod) FROM tho.Household_Rollforward
            WHERE reportingperiod <= '{prior_y}-12-31') AS bop_period,
          (SELECT MAX(reportingperiod) FROM tho.Household_Rollforward
            WHERE YEAR(reportingperiod) = {cur_y}) AS current_period
        """)
    finally:
        cursor.close()

    r = rows[0] if rows else {}
    bop = _fnum(r.get("bop_aum"))
    cur_aum = _fnum(r.get("current_aum"))
    nf_cur = _fnum(r.get("net_flows_cur"))
    nf_prior = _fnum(r.get("net_flows_prior"))

    def _pct(cur, prior):
        return ((cur - prior) / prior) if prior else None

    bop_period = r.get("bop_period")
    current_period = r.get("current_period")
    return {
        "bop_aum": bop,
        "current_aum": cur_aum,
        "aum_growth_pct": _pct(cur_aum, bop),
        "net_flows_current": nf_cur,
        "net_flows_prior": nf_prior,
        "net_flows_yoy_pct": _pct(nf_cur, nf_prior),
        "bop_period": bop_period.isoformat() if hasattr(bop_period, "isoformat") else bop_period,
        "current_period": current_period.isoformat() if hasattr(current_period, "isoformat") else current_period,
    }


def compute_flows(conn) -> dict:
    today = date.today()
    cur_y = today.year
    prior_y = cur_y - 1
    md = today.strftime("%m-%d")
    cur_start, cur_end = f"{cur_y}-01-01", f"{cur_y}-{md}"
    prior_start, prior_end = f"{prior_y}-01-01", f"{prior_y}-{md}"
    window = (
        f"((da.Date >= '{prior_start}' AND da.Date <= '{prior_end}') "
        f"OR (da.Date >= '{cur_start}' AND da.Date <= '{cur_end}'))"
    )

    cursor = conn.cursor()
    try:
        # 1. Client vs Prospect appointments YoY
        appts_yoy = _rows(cursor, f"""
        SELECT
            YEAR(da.Date) AS ApptYear,
            CASE WHEN f.ClientSince IS NOT NULL
                  AND f.ClientSince < f.firstappt_comp_combo THEN 'Existing Client'
                 ELSE 'Prospect' END AS ApptType,
            COUNT(*) AS Appts,
            SUM(ISNULL(f.paum, 0)) AS PAUM
        FROM tho.Current_Household_Fact f
        JOIN aip.DateDimension da ON f.firstappt_comp_combo = da.DateKey
        WHERE {window}
        GROUP BY YEAR(da.Date),
            CASE WHEN f.ClientSince IS NOT NULL
                  AND f.ClientSince < f.firstappt_comp_combo THEN 'Existing Client'
                 ELSE 'Prospect' END
        ORDER BY ApptYear, ApptType
        """)

        # 2. YTD appointments + PAUM by channel (current year)
        by_channel = _rows(cursor, f"""
        SELECT
            ISNULL(d.Channel_Middle, 'Unknown / NULL') AS Channel,
            COUNT(*) AS Appts,
            SUM(ISNULL(f.paum, 0)) AS PAUM,
            COUNT(CASE WHEN f.ClientSince >= {cur_y}0101
                       AND f.ClientSince <= CAST(FORMAT(GETDATE(), 'yyyyMMdd') AS INT)
                       AND f.firstappt_comp_combo >= {cur_y}0101 THEN 1 END) AS Converted_YTD
        FROM tho.Current_Household_Fact f
        JOIN tho.Current_Household_Demographic d ON f.LeadId = d.LeadId
        JOIN aip.DateDimension da ON f.firstappt_comp_combo = da.DateKey
        WHERE da.Date >= '{cur_start}' AND da.Date <= '{cur_end}'
        GROUP BY ISNULL(d.Channel_Middle, 'Unknown / NULL')
        ORDER BY Appts DESC
        """)

        # 3. Full funnel by channel YoY (Advisor Driven rolled up), true YTD both years
        funnel_yoy = _rows(cursor, f"""
        SELECT
            ApptYear, Channel,
            SUM(Leads) AS Leads, SUM(Appts) AS Appts, SUM(Clients) AS Clients,
            CASE WHEN SUM(Leads) > 0 THEN CAST(SUM(Appts) AS FLOAT) / SUM(Leads) END AS L2A_Rate,
            CASE WHEN SUM(Appts) > 0 THEN CAST(SUM(Clients) AS FLOAT) / SUM(Appts) END AS A2C_Rate
        FROM (
            SELECT
                YEAR(da.Date) AS ApptYear,
                CASE WHEN LOWER(ISNULL(d.Channel_Middle, '')) IN ({_ADVISOR_DRIVEN})
                     THEN 'Advisor Driven'
                     ELSE ISNULL(d.Channel_Middle, 'Unknown') END AS Channel,
                1 AS Leads,
                CASE WHEN f.firstappt_comp_combo IS NOT NULL
                      AND da2.Date >= CASE YEAR(da.Date) WHEN {prior_y} THEN '{prior_start}' ELSE '{cur_start}' END
                      AND da2.Date <= CASE YEAR(da.Date) WHEN {prior_y} THEN '{prior_end}' ELSE '{cur_end}' END
                     THEN 1 ELSE 0 END AS Appts,
                CASE WHEN f.ClientSince IS NOT NULL
                      AND da3.Date >= CASE YEAR(da.Date) WHEN {prior_y} THEN '{prior_start}' ELSE '{cur_start}' END
                      AND da3.Date <= CASE YEAR(da.Date) WHEN {prior_y} THEN '{prior_end}' ELSE '{cur_end}' END
                     THEN 1 ELSE 0 END AS Clients
            FROM tho.Current_Household_Fact f
            JOIN tho.Current_Household_Demographic d ON f.LeadId = d.LeadId
            JOIN aip.DateDimension da ON f.lead_created_date = da.DateKey
            LEFT JOIN aip.DateDimension da2 ON f.firstappt_comp_combo = da2.DateKey
            LEFT JOIN aip.DateDimension da3 ON f.ClientSince = da3.DateKey
            WHERE {window}
        ) x
        GROUP BY ApptYear, Channel
        HAVING SUM(Leads) >= 10
        ORDER BY ApptYear DESC, SUM(Appts) DESC
        """)
    finally:
        cursor.close()

    # ── Derive KPI headline numbers ────────────────────────────────────
    appts_by_year = {cur_y: 0, prior_y: 0}
    paum_by_year = {cur_y: 0.0, prior_y: 0.0}
    for r in appts_yoy:
        yr = int(r["ApptYear"])
        appts_by_year[yr] = appts_by_year.get(yr, 0) + int(r["Appts"] or 0)
        paum_by_year[yr] = paum_by_year.get(yr, 0.0) + _fnum(r["PAUM"])

    def _pct(cur, prior):
        return ((cur - prior) / prior) if prior else None

    kpis = {
        "current_year": cur_y,
        "prior_year": prior_y,
        "ytd_through": today.isoformat(),
        "appts_current": appts_by_year.get(cur_y, 0),
        "appts_prior": appts_by_year.get(prior_y, 0),
        "appts_yoy_pct": _pct(appts_by_year.get(cur_y, 0), appts_by_year.get(prior_y, 0)),
        "appt_paum_current": paum_by_year.get(cur_y, 0.0),
        "appt_paum_prior": paum_by_year.get(prior_y, 0.0),
        "appt_paum_yoy_pct": _pct(paum_by_year.get(cur_y, 0.0), paum_by_year.get(prior_y, 0.0)),
    }

    funnel_out = [
        {"year": int(r["ApptYear"]), "channel": r["Channel"],
         "leads": int(r["Leads"] or 0), "appts": int(r["Appts"] or 0),
         "clients": int(r["Clients"] or 0),
         "l2a_rate": _fnum(r["L2A_Rate"]), "a2c_rate": _fnum(r["A2C_Rate"])}
        for r in funnel_yoy
    ]

    # A2C-by-channel 2025-vs-2026 comparison (hero chart of the exec summary),
    # derived from the funnel so there is no extra query.
    a2c_cur = {r["channel"]: r["a2c_rate"] for r in funnel_out if r["year"] == cur_y}
    a2c_prior = {r["channel"]: r["a2c_rate"] for r in funnel_out if r["year"] == prior_y}
    a2c_by_channel = [
        {"channel": ch,
         "a2c_current": a2c_cur.get(ch),
         "a2c_prior": a2c_prior.get(ch),
         "delta_pp": (a2c_cur.get(ch) - a2c_prior[ch]) if ch in a2c_prior and a2c_cur.get(ch) is not None else None}
        for ch in sorted(set(a2c_cur) | set(a2c_prior))
    ]

    # Client vs prospect appointment split (already queried above).
    cvp = {}
    for r in appts_yoy:
        yr = int(r["ApptYear"]); typ = r["ApptType"]
        cvp.setdefault(typ, {"current": 0, "prior": 0})
        cvp[typ]["current" if yr == cur_y else "prior"] += int(r["Appts"] or 0)
    client_vs_prospect = [
        {"type": t, "current": v["current"], "prior": v["prior"],
         "yoy_pct": _pct(v["current"], v["prior"])}
        for t, v in sorted(cvp.items())
    ]

    # Optional enrichments — each guarded so a warehouse/schema hiccup can't take
    # down the core report. Missing sections are simply hidden by the frontend.
    try:
        engagement = _compute_engagement(
            conn, cur_start, cur_end, prior_start, prior_end, cur_y, prior_y, today)
    except Exception:  # pragma: no cover - defensive
        engagement = None
    try:
        top_advisors = _compute_top_advisors(conn, cur_y, today)
    except Exception:  # pragma: no cover - defensive
        top_advisors = []
    try:
        aum = _compute_aum_flows(conn, cur_y, prior_y)
    except Exception:  # pragma: no cover - defensive
        aum = None

    return {
        "as_of": today.isoformat(),
        "kpis": kpis,
        "appts_client_vs_prospect_yoy": [
            {"year": int(r["ApptYear"]), "type": r["ApptType"],
             "appts": int(r["Appts"] or 0), "paum": _fnum(r["PAUM"])}
            for r in appts_yoy
        ],
        "client_vs_prospect": client_vs_prospect,
        "appts_paum_by_channel": [
            {"channel": r["Channel"], "appts": int(r["Appts"] or 0),
             "paum": _fnum(r["PAUM"]), "converted_ytd": int(r["Converted_YTD"] or 0)}
            for r in by_channel
        ],
        "funnel_by_channel_yoy": funnel_out,
        "a2c_by_channel_yoy": a2c_by_channel,
        "engagement": engagement,
        "top_advisors_prospect_paum": top_advisors,
        "aum": aum,
    }
