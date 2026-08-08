"""AI executive summary via Azure OpenAI GPT-4.1 — deterministic, viewer-independent.

The narrative is generated purely from the data snapshot (flows + NCNM forecast).
It contains NO viewer identity or role, uses ``temperature=0`` + a fixed ``seed``,
so every viewer of the same refresh sees byte-identical commentary. The caller
generates it ONCE per data refresh and caches it alongside the payload.

Client resolution mirrors the NFBC blueprint: Azure OpenAI key/endpoint/api-version
come from env first, else Key Vault (``allworthsynapse``) via ``nfbc.kv``. If the
model is unavailable, a deterministic rule-based summary is returned so the page
still renders.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_MODEL = os.getenv("EXEC_REPORT_OPENAI_MODEL", "gpt-4.1")
_DEPLOYMENT = os.getenv("EXEC_REPORT_AZURE_OPENAI_DEPLOYMENT", _MODEL)
_DEFAULT_API_VERSION = "2024-10-21"
_TIMEOUT = float(os.getenv("EXEC_REPORT_LLM_TIMEOUT_SECONDS", "60"))
_SEED = int(os.getenv("EXEC_REPORT_LLM_SEED", "42"))

_OPENAI_KV_NAMES = ["azure-openai-api-key", "openaikey", "openai-api-key", "openai-key"]
_AZURE_ENDPOINT_KV_NAMES = ["azure-openai-endpoint"]
_AZURE_APIVERSION_KV_NAMES = ["azure-openai-apiversion", "azure-openai-api-version"]


def _kv_get(names):
    try:
        from nfbc import kv
        return kv.get_secret(names)
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("Executive Report KV lookup unavailable: %s", exc)
        return None


def _resolve_endpoint() -> str | None:
    return os.getenv("AZURE_OPENAI_ENDPOINT") or _kv_get(_AZURE_ENDPOINT_KV_NAMES)


def _resolve_key(prefer_azure: bool) -> str | None:
    order = (("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY") if prefer_azure
             else ("OPENAI_API_KEY", "AZURE_OPENAI_API_KEY"))
    for name in order:
        val = os.getenv(name)
        if val:
            return val
    return _kv_get(_OPENAI_KV_NAMES)


def _resolve_api_version() -> str:
    return (os.getenv("AZURE_OPENAI_API_VERSION")
            or _kv_get(_AZURE_APIVERSION_KV_NAMES)
            or _DEFAULT_API_VERSION)


def _build_client():
    """Return (client, model_id) or (None, None) if unavailable."""
    endpoint = _resolve_endpoint()
    api_key = _resolve_key(prefer_azure=bool(endpoint))
    if not api_key:
        return None, None
    try:
        if endpoint:
            from openai import AzureOpenAI
            client = AzureOpenAI(
                api_key=api_key,
                azure_endpoint=endpoint,
                api_version=_resolve_api_version(),
                timeout=_TIMEOUT,
                max_retries=1,
            )
            return client, _DEPLOYMENT
        from openai import OpenAI
        client = OpenAI(api_key=api_key, timeout=_TIMEOUT, max_retries=1)
        return client, _MODEL
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Executive Report OpenAI client unavailable (%s)", exc)
        return None, None


# ---------------------------------------------------------------------------
# Prompt construction (pure function of the data snapshot)
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a senior wealth-strategy analyst writing the executive summary for the "
    "Allworth Financial CEO flows report. Be specific, evidence-led, and decisive. "
    "The data snapshot describes the entire report page: firm AUM and net flows, "
    "appointments and appointment PAUM, the NCNM end-of-month forecast and its "
    "components/channels, closes booked by advisor, the conversion funnel and A2C "
    "shifts, client engagement pacing, and advisor concentration. Synthesize across "
    "ALL of these — do not focus on only one section. Lead with the AUM/net-flows and "
    "NCNM headlines, then explain what is driving them. Quantify every claim (deltas, "
    "rates, dollar amounts). Structure the summary with these exact bold section "
    "headers, each followed by 1-3 sentences: **Bottom line**, **Evidence**, "
    "**Interpretation**, **Risks / caveats**, **Recommended actions**. Do not invent "
    "numbers beyond the data provided. Use $B/$M/$K and % formatting. Keep the whole "
    "summary under 340 words."
)


def _m(v: float) -> str:
    if v is None:
        return "$0"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e9:
        return f"{sign}${a/1e9:,.1f}B"
    if a >= 1e6:
        return f"{sign}${a/1e6:,.1f}M"
    if a >= 1e3:
        return f"{sign}${a/1e3:,.0f}K"
    return f"${v:,.0f}"


def _pct(v) -> str:
    return "n/a" if v is None else f"{v*100:+.1f}%"


def build_facts(flows: dict, ncnm: dict) -> str:
    k = flows.get("kpis", {})
    cur_y = k.get("current_year")
    prior_y = k.get("prior_year")
    lines = [
        f"Period: YTD through {k.get('ytd_through')} ({cur_y} vs {prior_y}).",
    ]

    # Firm AUM bridge + net flows (top KPI row).
    aum = flows.get("aum")
    if aum:
        lines.append(
            f"BoP AUM (Dec 31 {prior_y}): {_m(aum.get('bop_aum'))}; current AUM "
            f"{_m(aum.get('current_aum'))} ({_pct(aum.get('aum_growth_pct'))} YTD)."
        )
        lines.append(
            f"Net flows YTD: {_m(aum.get('net_flows_current'))} vs "
            f"{_m(aum.get('net_flows_prior'))} prior same-period ({_pct(aum.get('net_flows_yoy_pct'))})."
        )

    lines += [
        f"Appointments YTD: {k.get('appts_current')} vs {k.get('appts_prior')} prior ({_pct(k.get('appts_yoy_pct'))}).",
        f"Appointment PAUM YTD: {_m(k.get('appt_paum_current'))} vs {_m(k.get('appt_paum_prior'))} prior "
        f"({_pct(k.get('appt_paum_yoy_pct'))}).",
    ]

    # Client vs prospect appointment split.
    cvp = flows.get("client_vs_prospect", [])
    if cvp:
        lines.append("Appointments by type: " + "; ".join(
            f"{r['type']} {r['current']} vs {r['prior']} ({_pct(r.get('yoy_pct'))})" for r in cvp
        ) + ".")

    lines.append("")
    lines += [
        f"NCNM end-of-month projection: {_m(ncnm.get('eom_projection'))} "
        f"(MTD actual {_m(ncnm.get('mtd_actual'))} + remaining {_m(ncnm.get('remaining_expected'))}).",
        f"NCNM expected range: {_m(ncnm.get('confidence', {}).get('low'))} - "
        f"{_m(ncnm.get('confidence', {}).get('high'))}.",
    ]
    comps = ncnm.get("by_component", [])
    if comps:
        lines.append("NCNM components: " + "; ".join(
            f"{c['label']} {_m(c['total'])}" for c in comps
        ) + ".")
    chans = ncnm.get("by_channel", [])
    if chans:
        top = sorted(chans, key=lambda c: c.get("projection", 0), reverse=True)[:4]
        lines.append("NCNM by channel: " + "; ".join(
            f"{c['channel']} {_m(c['projection'])}" for c in top
        ) + ".")

    # Trailing monthly NCNM actuals (forecast-vs-actual chart context).
    hist = ncnm.get("monthly_history", [])
    if hist:
        recent = hist[-4:]
        lines.append("Trailing NCNM actuals: " + "; ".join(
            f"{h.get('month')} {_m(h.get('actual'))}" for h in recent
        ) + ".")

    # Closes booked this month by advisor.
    closes = ncnm.get("closes_by_advisor", [])
    if closes:
        top_c = closes[:5]
        lines.append("Closes this month by advisor (PAUM / NCNM to date): " + "; ".join(
            f"{c['advisor']} {_m(c.get('paum'))} / {_m(c.get('ncnm'))}" for c in top_c
        ) + ".")

    lines.append("")
    funnel = flows.get("funnel_by_channel_yoy", [])
    cur_funnel = [r for r in funnel if r.get("year") == cur_y]
    if cur_funnel:
        top_f = sorted(cur_funnel, key=lambda r: r.get("appts", 0), reverse=True)[:4]
        lines.append("Funnel (current YTD) by channel: " + "; ".join(
            f"{r['channel']} {r['appts']} appts, A2C {r['a2c_rate']*100:.1f}%" for r in top_f
        ) + ".")

    # A2C-by-channel YoY movement (hero chart of the exec summary).
    a2c = flows.get("a2c_by_channel_yoy", [])
    if a2c:
        moved = [r for r in a2c if r.get("delta_pp") is not None]
        moved.sort(key=lambda r: abs(r["delta_pp"]), reverse=True)
        if moved:
            lines.append("A2C YoY shifts (pp): " + "; ".join(
                f"{r['channel']} {r['delta_pp']*100:+.1f}pp" for r in moved[:5]
            ) + ".")

    # Client engagement activity + current-month pacing.
    eng = flows.get("engagement")
    if eng:
        lines.append(
            f"Client engagement events: {eng.get('events_current')} vs "
            f"{eng.get('events_prior')} prior ({_pct(eng.get('events_yoy_pct'))}); "
            f"{eng.get('current_month_label')} pace {eng.get('month_pace_current')} vs "
            f"{eng.get('month_pace_prior')} ({_pct(eng.get('month_pace_yoy_pct'))})."
        )

    # Advisor concentration in media/paid channels.
    advisors = flows.get("top_advisors_prospect_paum", [])
    if advisors:
        top_a = advisors[:3]
        lines.append("Top advisors by prospect PAUM (media/paid): " + "; ".join(
            f"{a['advisor']} {_m(a.get('paum'))} at {a.get('a2c_rate', 0)*100:.1f}% A2C" for a in top_a
        ) + ".")

    return "\n".join(lines)


def _fallback_summary(facts: str, flows: dict, ncnm: dict) -> str:
    k = flows.get("kpis", {})
    aum = flows.get("aum") or {}
    eom = ncnm.get("eom_projection", 0)
    appt_delta = _pct(k.get("appts_yoy_pct"))
    paum_delta = _pct(k.get("appt_paum_yoy_pct"))
    nf_line = ""
    if aum:
        nf_line = (
            f"Net flows YTD {_m(aum.get('net_flows_current'))} ({_pct(aum.get('net_flows_yoy_pct'))} YoY); "
            f"AUM {_m(aum.get('bop_aum'))} → {_m(aum.get('current_aum'))} "
            f"({_pct(aum.get('aum_growth_pct'))} YTD). "
        )
    return (
        f"**Bottom line** {nf_line}Appointment volume is {appt_delta} YoY and appointment PAUM is "
        f"{paum_delta} YoY; the model projects {_m(eom)} of NCNM by month end.\n\n"
        f"**Evidence** {k.get('appts_current')} YTD appointments vs {k.get('appts_prior')} prior; "
        f"appointment PAUM {_m(k.get('appt_paum_current'))} vs {_m(k.get('appt_paum_prior'))}. "
        f"NCNM projection {_m(eom)} (MTD {_m(ncnm.get('mtd_actual'))} + remaining "
        f"{_m(ncnm.get('remaining_expected'))}).\n\n"
        f"**Interpretation** Growth is being driven by appointment PAUM mix more than raw volume.\n\n"
        f"**Risks / caveats** Warehouse data refreshes daily; NCNM is a probabilistic forecast with a "
        f"{_m(ncnm.get('confidence', {}).get('low'))}-{_m(ncnm.get('confidence', {}).get('high'))} range.\n\n"
        f"**Recommended actions** Focus advisor capacity on the highest-PAUM channels and protect "
        f"late-stage pipeline expected to fund this month.\n\n"
        f"_(AI model unavailable — deterministic summary generated from the data snapshot.)_"
    )


def generate_summary(flows: dict, ncnm: dict) -> dict:
    """Return {'summary': str, 'model': str, 'source': 'llm'|'fallback'}.

    Pure function of (flows, ncnm) — no viewer context — so the output is
    identical for every viewer of the same refresh.
    """
    facts = build_facts(flows, ncnm)
    client, model_id = _build_client()
    if client is None:
        return {"summary": _fallback_summary(facts, flows, ncnm), "model": None, "source": "fallback"}

    try:
        resp = client.chat.completions.create(
            model=model_id,
            temperature=0,
            seed=_SEED,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": f"Data snapshot:\n\n{facts}"},
            ],
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            return {"summary": _fallback_summary(facts, flows, ncnm), "model": None, "source": "fallback"}
        return {"summary": text, "model": model_id, "source": "llm"}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Executive Report summary generation failed (%s)", exc)
        return {"summary": _fallback_summary(facts, flows, ncnm), "model": None, "source": "fallback"}
