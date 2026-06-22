"""Rule-based nudge engine. Deterministic — no LLM involved."""

from allworth_api.core.formatting import fmt_usd, js_round
from allworth_api.data.seed import advisor_for_client, portfolio_for, seed_for, spending_summary

FUNDS = {"VTI", "VXUS", "VTEB", "BND", "FXAIX", "FSPSX", "FXNAX", "SPAXX"}


def build_nudges(
    spending: dict,
    positions: list[dict],
    accounts: list[dict],
    advisor_first_name: str = "your advisor",
) -> list[dict]:
    nudges = []
    advisor_cta = f"Discuss with {advisor_first_name}"

    s = spending
    if s["avg3mo"] > s["plan"] * 1.15:
        nudges.append(
            {
                "id": "nudge_spending",
                "type": "spending",
                "title": "Spending is running above plan",
                "headline": f"{s['overPlanPct']}% over plan",
                "body": (
                    f"Your last three months averaged {fmt_usd(s['avg3mo'])}/mo against a "
                    f"{fmt_usd(s['plan'])}/mo plan — about {s['overPlanPct']}% over. Travel and "
                    f"Gifts/Family account for most of the difference. At this pace it's worth "
                    f"checking what it means for the lake house timeline."
                ),
                "cta": "Ask me what this means",
                "advisorCta": advisor_cta,
                "severity": "attention",
            }
        )

    by_account: dict[str, dict] = {}
    for p in positions:
        acct = by_account.setdefault(p["accountId"], {"total": 0, "positions": []})
        acct["total"] += p["value"]
        acct["positions"].append(p)

    for account_id, grp in by_account.items():
        for p in grp["positions"]:
            if p["assetClass"] == "cash" or p["symbol"] == "CASH" or p["symbol"] in FUNDS:
                continue
            weight = p["value"] / grp["total"]
            if weight > 0.2:
                acct = next((a for a in accounts if a["id"] == account_id), None)
                label = (
                    f"your {acct['institution']} account"
                    if acct and acct["group"] == "outside"
                    else (acct["name"] if acct else account_id)
                )
                pct = js_round(weight * 100)
                nudges.append(
                    {
                        "id": f"nudge_conc_{account_id}_{p['symbol']}",
                        "type": "concentration",
                        "title": f"{p['symbol']} is a large share of {label}",
                        "headline": f"{pct}% of the account",
                        "body": (
                            f"{p['name']} makes up about {pct}% of {label} ({fmt_usd(p['value'])}). "
                            f"Single positions this large can swing the whole account. There are ways "
                            f"to reduce concentration over time — some more tax-aware than others."
                        ),
                        "cta": "Ask me about my options",
                        "advisorCta": advisor_cta,
                        "severity": "info",
                    }
                )

    return nudges


def nudges_for(client_id: str) -> list[dict]:
    advisor_first_name = advisor_for_client(client_id)["name"].split(",")[0].split()[0]
    return build_nudges(
        spending_summary(3, client_id),
        portfolio_for(client_id)["positions"],
        seed_for(client_id)["accounts"],
        advisor_first_name,
    )
