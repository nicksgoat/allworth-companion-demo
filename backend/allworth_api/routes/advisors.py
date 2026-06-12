from fastapi import APIRouter

from allworth_api.core.formatting import fmt_usd
from allworth_api.core.nudges import nudges_for
from allworth_api.core.tool_runner import run_tool
from allworth_api.data.seed import seed

router = APIRouter()


@router.get("/api/advisors/{advisor_id}/book")
def book(advisor_id: str):
    households = [
        {**h, "openNudges": len(nudges_for(h["clientId"]))} if h["clientId"] == "maya" else h
        for h in seed["book"]
    ]
    return {
        "advisor": next(
            (a for a in seed["personas"]["advisors"] if a["id"] == advisor_id),
            seed["personas"]["advisors"][0],
        ),
        "households": households,
    }


@router.get("/api/advisors/{advisor_id}/clients/{client_id}/brief")
def brief(advisor_id: str, client_id: str):
    data = run_tool("get_advisor_brief", {}, client_id)
    return {**data, "narrative": brief_narrative(data)}


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
