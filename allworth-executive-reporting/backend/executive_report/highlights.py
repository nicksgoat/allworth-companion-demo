"""Deterministic highlights — concerns, bright spots, watch items, and priority
actions derived purely from the flows + NCNM data snapshot.

This mirrors the structured narrative of the CEO flows executive summary
(``ceo_flows_exec_summary``) but is rule-based and viewer-independent, so it is
byte-identical for every viewer of the same refresh. The GPT-4.1 prose summary
still leads the page; these are the structured, thresholded callouts beneath it.
"""

from __future__ import annotations


def _m(v) -> str:
    if v is None:
        return "$0"
    a = abs(float(v))
    s = "-" if v < 0 else ""
    if a >= 1e6:
        return f"{s}${a/1e6:,.1f}M"
    if a >= 1e3:
        return f"{s}${a/1e3:,.0f}K"
    return f"${a:,.0f}"


def _pp(cur, prior) -> str:
    if cur is None or prior is None:
        return "n/a"
    return f"{(cur - prior) * 100:+.1f}pp"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v*100:+.1f}%"


def build_highlights(flows: dict, ncnm: dict) -> dict:
    """Return {concerns, bright_spots, watch, actions} — each a list of strings."""
    concerns: list[str] = []
    bright: list[str] = []
    watch: list[str] = []
    actions: list[str] = []

    a2c = flows.get("a2c_by_channel_yoy", []) or []
    cur_y = flows.get("kpis", {}).get("current_year")
    prior_y = flows.get("kpis", {}).get("prior_year")

    # Channel A2C movers (largest declines → concern, largest gains → bright).
    movers = [r for r in a2c if r.get("delta_pp") is not None]
    decliners = sorted(movers, key=lambda r: r["delta_pp"])[:2]
    gainers = sorted(movers, key=lambda r: r["delta_pp"], reverse=True)[:2]
    for r in decliners:
        if r["delta_pp"] < -0.02:
            concerns.append(
                f"{r['channel']} appt-to-client fell {_pp(r['a2c_current'], r['a2c_prior'])} "
                f"to {r['a2c_current']*100:.1f}% vs {prior_y}."
            )
    for r in gainers:
        if r["delta_pp"] > 0.02:
            bright.append(
                f"{r['channel']} converting at {r['a2c_current']*100:.1f}% appt-to-client, "
                f"up {_pp(r['a2c_current'], r['a2c_prior'])} vs {prior_y}."
            )

    # Appointment growth.
    k = flows.get("kpis", {})
    if k.get("appts_yoy_pct") is not None:
        line = (f"Prospect appointments {_pct(k['appts_yoy_pct'])} YoY "
                f"({k.get('appts_prior')} → {k.get('appts_current')}); "
                f"appointment PAUM {_pct(k.get('appt_paum_yoy_pct'))}.")
        (bright if k["appts_yoy_pct"] >= 0 else watch).append(line)

    # Client engagement cliff.
    eng = flows.get("engagement")
    if eng:
        if eng.get("events_yoy_pct") is not None and eng["events_yoy_pct"] < -0.03:
            concerns.append(
                f"Client engagement events {_pct(eng['events_yoy_pct'])} YoY "
                f"({eng.get('events_prior'):,} → {eng.get('events_current'):,})."
            )
        mp = eng.get("month_pace_yoy_pct")
        if mp is not None and mp < -0.15:
            concerns.append(
                f"{eng.get('current_month_label')} client activity pacing {_pct(mp)} vs prior year "
                f"({eng.get('month_pace_current'):,} vs {eng.get('month_pace_prior'):,} events) — "
                f"confirm scheduling lag vs. real drop."
            )
            actions.append(
                f"Confirm the {eng.get('current_month_label')} client-activity cliff — pull scheduled "
                f"vs. completed counts before month-end and escalate regionally if the shortfall is real."
            )

    # Advisor PAUM concentration.
    advisors = flows.get("top_advisors_prospect_paum", []) or []
    if advisors:
        top2 = advisors[:2]
        paum2 = sum(a.get("paum", 0) for a in top2)
        if len(top2) == 2 and paum2 > 0:
            a2c_lo = min(a.get("a2c_rate", 0) for a in top2)
            a2c_hi = max(a.get("a2c_rate", 0) for a in top2)
            concerns.append(
                f"{top2[0]['advisor']} & {top2[1]['advisor']} hold {_m(paum2)} in prospect PAUM "
                f"at {a2c_lo*100:.1f}–{a2c_hi*100:.1f}% post-hand-off conversion."
            )
            actions.append(
                f"Audit {top2[0]['advisor']} & {top2[1]['advisor']} — {_m(paum2)} PAUM at "
                f"{a2c_lo*100:.1f}–{a2c_hi*100:.1f}% A2C. Determine lead-quality vs. routing vs. tracking."
            )

    # NCNM confidence + top channel action.
    chans = ncnm.get("by_channel", []) or []
    if chans:
        widest = max(chans, key=lambda c: c.get("cv", 0))
        if widest.get("cv", 0) > 0.28:
            watch.append(
                f"{widest['channel']} has the widest NCNM confidence band (CV {widest['cv']*100:.1f}%), "
                f"projection {_m(widest.get('projection'))}."
            )
        top_ch = max(chans, key=lambda c: c.get("projection", 0))
        actions.append(
            f"Protect {top_ch['channel']} capacity — largest projected NCNM contributor at "
            f"{_m(top_ch.get('projection'))}."
        )

    return {
        "concerns": concerns,
        "bright_spots": bright,
        "watch": watch,
        "actions": actions,
    }
