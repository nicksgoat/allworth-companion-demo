from fastapi import APIRouter
from fastapi.responses import JSONResponse

from allworth_api.application.chat_service import suggested_for
from allworth_api.application.insights import nudges_for
from allworth_api.application.memory_service import active_facts, episodes_for, forget_fact
from allworth_api.infrastructure.seed import accounts_for, portfolio_for, seed, spending_summary

router = APIRouter()


@router.get("/api/clients/{client_id}/dashboard")
def dashboard(client_id: str):
    a = accounts_for()
    s = spending_summary(3)
    return {
        "client": next((c for c in seed["personas"]["clients"] if c["id"] == client_id), None),
        "advisor": seed["personas"]["advisors"][0],
        "netWorth": a["netWorth"],
        "netWorthHistory": seed["netWorthHistory"],
        "allworthTotal": a["allworthTotal"],
        "heldAwayTotal": a["heldAwayTotal"],
        "liabilitiesTotal": a["liabilitiesTotal"],
        "accounts": {"allworth": a["allworth"], "outside": a["outside"]},
        "spending": {"avg3mo": s["avg3mo"], "plan": s["plan"], "overPlanPct": s["overPlanPct"]},
        "nudges": nudges_for(client_id),
        "liquidityEvent": seed["liquidityEvent"],
        "disclaimer": seed["disclaimer"],
    }


@router.get("/api/clients/{client_id}/nudges")
def nudges(client_id: str):
    return {"nudges": nudges_for(client_id)}


@router.get("/api/clients/{client_id}/spending")
def spending(client_id: str, months: int = 3):
    return spending_summary(months or 3)


@router.get("/api/clients/{client_id}/portfolio")
def portfolio(client_id: str):
    return portfolio_for()


@router.get("/api/clients/{client_id}/profile")
def profile(client_id: str):
    return {"clientId": client_id, "facts": active_facts(client_id)}


# Governed memory: "Forget this detail" — marks the fact deleted, never erases it.
@router.delete("/api/clients/{client_id}/facts/{fact_id}")
def forget(client_id: str, fact_id: str):
    fact = forget_fact(client_id, fact_id)
    if not fact:
        return JSONResponse(status_code=404, content={"error": "fact not found or not active"})
    return {"ok": True, "fact": fact}


# Proactive greeting for the chat screen — deterministic so Beat 4 never flakes.
@router.get("/api/clients/{client_id}/proactive")
def proactive(client_id: str, session: str = "wednesday"):
    if session == "wednesday":
        facts = active_facts(client_id)
        ipo = next((f for f in facts if f["category"] == "liquidity_events"), None)
        if ipo:
            return {
                "message": (
                    "Welcome back, Maya. Last time you were weighing $200K into the SpaceX IPO — "
                    "your deadline is Sunday, June 15. Want to pick up where we left off, or look "
                    "at something else?"
                ),
                "basedOn": {
                    "fact": ipo["fact"],
                    "source_quote": ipo["source_quote"],
                    "learned_at": ipo["learned_at"],
                },
                "suggested": suggested_for(session),
            }
    return {
        "message": "Hi Maya — I can help you understand your accounts, spending, plan, or anything "
        "you're weighing. What's on your mind?",
        "basedOn": None,
        "suggested": suggested_for(session),
    }


@router.get("/api/clients/{client_id}/chat-history")
def chat_history(client_id: str, session: str = "wednesday"):
    return {"session": session, "episodes": episodes_for(client_id, session)}
