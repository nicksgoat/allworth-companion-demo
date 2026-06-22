from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from allworth_api.core.auth import get_current_household
from allworth_api.core.formatting import fmt_usd
from allworth_api.core.nudges import nudges_for
from allworth_api.core.tool_runner import run_tool
from allworth_api.data.advisors import advisor_by_id
from allworth_api.data.seed import seed

router = APIRouter()


@router.get("/api/advisors/{advisor_id}/book")
def book(advisor_id: str, household_id: str = Depends(get_current_household)):
    households = [
        {**h, "openNudges": len(nudges_for(h["clientId"]))} if h["clientId"] == "maya" else h
        for h in seed["book"]
    ]
    return {
        "advisor": advisor_by_id(advisor_id),
        "households": households,
    }


@router.get("/api/advisors/{advisor_id}/clients/{client_id}/brief")
def brief(advisor_id: str, client_id: str, household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    data = run_tool("get_advisor_brief", {}, client_id)
    return {**data, "narrative": brief_narrative(data), "reviewWorkflow": review_workflow(data)}


def brief_narrative(d: dict) -> str:
    nudge = d["openNudges"][0] if d["openNudges"] else None
    lines = [
        (
            f"Maya is weighing a {fmt_usd(d['liquidityEvent']['amount'])} allocation to the "
            f"{d['liquidityEvent']['label'].replace(' allocation', '', 1)} with a "
            f"{d['liquidityEvent']['deadline']} deadline — she has worked through funding sources "
            f"with the assistant and has open questions on liquidity vs. her $9,000/mo income draw."
        ),
        (
            f"Held-away assets detected: {fmt_usd(d['heldAwayDetected'])} across "
            f"{len(d['heldAwayAccounts'])} outside accounts (largest: Fidelity 401(k), "
            f"{fmt_usd(385000)}) — a consolidation conversation may be timely if the IPO "
            f"discussion opens the door."
        ),
        f"Open nudge: {nudge['title'].lower()} ({nudge['headline']})." if nudge else None,
        "She prefers plain-English explanations and is tax-sensitive about her 2015 Apple shares.",
    ]
    return "\n".join(line for line in lines if line)


def review_workflow(d: dict) -> dict:
    client_name = (d.get("client") or {}).get("name", "Client").split(",")[0]
    nudge = d["openNudges"][0] if d["openNudges"] else None
    return {
        "status": "advisor_review_required",
        "summary": (
            f"Prepare {client_name}'s next review around liquidity, spending, held-away assets, "
            "and whether the current plan still fits."
        ),
        "decisionsToReview": [
            {
                "id": "liquidity-event",
                "label": d["liquidityEvent"]["label"],
                "whyItMatters": (
                    f"{fmt_usd(d['liquidityEvent']['amount'])} decision with a "
                    f"{d['liquidityEvent']['deadline']} deadline."
                ),
            },
            {
                "id": "spending-plan",
                "label": "Spending versus income plan",
                "whyItMatters": "Recent spending is above plan and affects goal timing.",
            },
            {
                "id": "held-away-assets",
                "label": "Held-away assets",
                "whyItMatters": (
                    f"{fmt_usd(d['heldAwayDetected'])} detected outside Allworth management."
                ),
            },
        ],
        "talkingPoints": [
            "Confirm whether the liquidity decision still fits the income draw.",
            "Review tax-sensitive funding sources before any sale.",
            "Use plain-English trade-offs and avoid directive recommendations.",
        ],
        "openQuestions": [
            "Which funding source creates the least tax drag?",
            "Does recent spending change the lake house timeline?",
            "Should held-away assets be part of the next planning conversation?",
        ],
        "nextBestAction": (
            f"Discuss {nudge['title'].lower()} and the liquidity event in the next review."
            if nudge
            else "Prepare a focused review agenda before the next client meeting."
        ),
    }
