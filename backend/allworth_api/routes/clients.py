from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from allworth_api.core.auth import get_current_household, get_session_for_household
from allworth_api.core.chat_service import suggested_for
from allworth_api.core.memory import active_facts, episodes_for, forget_fact
from allworth_api.core.nudges import nudges_for
from allworth_api.data.household import (
    get_accounts,
    get_client_persona,
    get_dashboard_data,
    get_net_worth_history,
    get_portfolio,
    get_spending,
)
from allworth_api.data.seed import seed

router = APIRouter()


@router.get("/api/clients/{client_id}/dashboard")
def dashboard(client_id: str, household_id: str = Depends(get_current_household)):
    # Enforce: requested client_id must match authenticated household
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    d = get_dashboard_data(client_id)
    a = d["accounts"]
    s = d["spending"]
    advisor = seed["personas"]["advisors"][0]
    return {
        "client": d["client"],
        "advisor": advisor,
        "netWorth": a["netWorth"],
        "netWorthHistory": d["net_worth_history"],
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
def nudges(client_id: str, household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    return {"nudges": nudges_for(client_id)}


@router.get("/api/clients/{client_id}/spending")
def spending(client_id: str, months: int = 3, household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    return get_spending(client_id, months or 3)


@router.get("/api/clients/{client_id}/portfolio")
def portfolio(client_id: str, household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    return get_portfolio(client_id)


@router.get("/api/clients/{client_id}/profile")
def profile(client_id: str, household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    return {"clientId": client_id, "facts": active_facts(client_id)}


@router.delete("/api/clients/{client_id}/facts/{fact_id}")
def forget(client_id: str, fact_id: str):
    fact = forget_fact(client_id, fact_id)
    if not fact:
        return JSONResponse(status_code=404, content={"error": "fact not found or not active"})
    return {"ok": True, "fact": fact}


@router.get("/api/clients/{client_id}/proactive")
def proactive(client_id: str, session: str = "wednesday"):
    # Resolve the client's first name from their auth session or persona
    auth_sess = get_session_for_household(client_id)
    if auth_sess and auth_sess.contact_name:
        first_name = auth_sess.contact_name.split(",")[0].split()[0]
    else:
        persona = get_client_persona(client_id)
        first_name = (persona or {}).get("name", "there").split(",")[0].split()[0]

    if session == "wednesday":
        return {
            "message": (
                f"Welcome back, {first_name}. I've refreshed your full picture — plan, portfolio, and "
                "goals. A couple of things stand out worth a closer look. Where would you like to start?"
            ),
            "basedOn": None,
            "suggested": suggested_for(session),
        }
    return {
        "message": (
            f"Hi {first_name} — I can pull your whole financial picture together: run a retirement "
            "projection, check how your portfolio is tracking to its target, or look at your goals. "
            "What would you like to dig into?"
        ),
        "basedOn": None,
        "suggested": suggested_for(session),
    }


@router.get("/api/clients/{client_id}/chat-history")
def chat_history(client_id: str, session: str = "wednesday"):
    return {"episodes": episodes_for(client_id, session)}
