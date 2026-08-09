"""Rule-based portfolio insight generator.

Produces the AI Summary surface (strengths, risks, concentration
warnings, reinvestment needs, recommendations) from computed analytics.
Deterministic and explainable today; this function is the seam where a
real LLM call can be swapped in later without touching the API or frontend.
"""

from __future__ import annotations

from investments.models.bond import Bond
from investments.services import analytics


def generate_summary(bonds: list[Bond]) -> dict:
    if not bonds:
        return {
            "strengths": [],
            "risks": ["No holdings available to analyze."],
            "concentration_warnings": [],
            "reinvestment_needs": [],
            "recommendations": ["Upload a Tamarac bond export to begin analysis."],
        }

    kpis = analytics.compute_kpis(bonds)
    sectors = analytics.sector_allocation(bonds)
    states = analytics.state_allocation(bonds)
    issuers = analytics.issuer_concentration(bonds, top_n=3)
    calls = analytics.upcoming_calls(bonds)
    maturities = analytics.upcoming_maturities(bonds)
    downgrades = [c for c in analytics.rating_changes(bonds) if c["direction"] == "downgrade"]
    ladder = analytics.ladder_quality_score(bonds)

    strengths: list[str] = []
    risks: list[str] = []
    concentration: list[str] = []
    reinvestment: list[str] = []
    recommendations: list[str] = []

    # Credit quality.
    total = sum(b.effective_market_value() for b in bonds) or 1.0
    ig_share = sum(b.effective_market_value() for b in bonds if b.is_investment_grade is True)
    junk_share = sum(b.effective_market_value() for b in bonds if b.is_investment_grade is False)
    nr_share = sum(b.effective_market_value() for b in bonds if b.is_investment_grade is None)
    rated_share = ig_share + junk_share  # bonds with a known rating
    if kpis["average_rating"] and kpis["average_rating"].startswith(("Aaa", "Aa", "A")):
        if rated_share / total >= 0.5:
            # Average is meaningful — at least half the portfolio has a rating.
            strengths.append(f"High average credit quality ({kpis['average_rating']}).")
        else:
            # Average is computed over a minority; note the coverage gap.
            strengths.append(
                f"Rated holdings average {kpis['average_rating']}, "
                f"though only {rated_share / total:.0%} of the portfolio has a rating."
            )
    if ig_share / total < 0.8:
        parts: list[str] = []
        if junk_share / total >= 0.05:
            parts.append(f"{junk_share / total:.0%} is below investment grade")
        if nr_share / total >= 0.05:
            parts.append(f"{nr_share / total:.0%} is not rated")
        detail = f" ({'; '.join(parts)})" if parts else ""
        risks.append(
            f"Only {ig_share / total:.0%} of market value is investment grade{detail}; "
            "review credit exposure."
        )

    # Diversification / concentration.
    if issuers and issuers[0]["pct"] > 10:
        concentration.append(
            f"Top issuer '{issuers[0]['label']}' is {issuers[0]['pct']:.1f}% of the portfolio."
        )
    # Check whether multiple mid-sized issuers together create hidden concentration.
    if len(issuers) >= 3:
        top3_pct = sum(i["pct"] for i in issuers[:3])
        if top3_pct > 40 and (not issuers or issuers[0]["pct"] <= 10):
            concentration.append(
                f"Top 3 issuers combined represent {top3_pct:.1f}% of the portfolio "
                f"({', '.join(i['label'] for i in issuers[:3])})."
            )
    if sectors and sectors[0]["pct"] > 40:
        concentration.append(
            f"Sector '{sectors[0]['label']}' represents {sectors[0]['pct']:.1f}% of holdings."
        )
    if states and states[0]["label"] != "Unclassified" and states[0]["pct"] > 30:
        concentration.append(
            f"State concentration: {states[0]['label']} is {states[0]['pct']:.1f}% of holdings."
        )

    # Ladder structure.
    if ladder >= 70:
        strengths.append(f"Well-laddered maturity profile (ladder score {ladder:.0f}/100).")
    elif ladder < 50:
        risks.append(f"Maturity ladder is concentrated (ladder score {ladder:.0f}/100).")
        recommendations.append("Spread maturities more evenly to reduce reinvestment-timing risk.")

    # Duration.
    avg_dur = kpis["average_duration"]
    if avg_dur is not None and avg_dur > 8:
        risks.append(f"Elevated interest-rate sensitivity (avg duration {avg_dur:.1f}).")
    elif avg_dur is not None and avg_dur < 2:
        strengths.append(f"Low interest-rate sensitivity (avg duration {avg_dur:.1f}).")
    elif avg_dur is not None:
        strengths.append(
            f"Moderate interest-rate sensitivity (avg duration {avg_dur:.1f})."
        )

    # Reinvestment.
    near_principal = sum(m["market_value"] for m in maturities)
    if near_principal > 0:
        reinvestment.append(
            f"{_money(near_principal)} maturing within 180 days will require reinvestment."
        )
    if calls:
        reinvestment.append(
            f"{len(calls)} bond(s) callable within 90 days "
            f"({_money(sum(c['market_value'] for c in calls))})."
        )

    # Rating changes.
    if downgrades:
        risks.append(f"{len(downgrades)} recent credit downgrade(s) detected.")
        recommendations.append("Review downgraded holdings for potential replacement.")

    # Income.
    if kpis["annual_income"] > 0:
        strengths.append(
            f"Generating {_money(kpis['annual_income'])} of projected annual income "
            f"(avg coupon {kpis['average_coupon'] or 0:.2f}%)."
        )

    if not recommendations:
        recommendations.append("Portfolio structure looks balanced; continue routine monitoring.")

    return {
        "strengths": strengths,
        "risks": risks,
        "concentration_warnings": concentration,
        "reinvestment_needs": reinvestment,
        "recommendations": recommendations,
    }


def _money(value: float) -> str:
    return f"${value:,.0f}"
