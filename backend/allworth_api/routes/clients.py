from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from allworth_api.config import data_mode
from allworth_api.core.auth import get_current_household, get_session_for_household
from allworth_api.core.chat_service import suggested_for
from allworth_api.core.conversation_store import load_turns
from allworth_api.core.memory import active_facts, episodes_for, forget_fact
from allworth_api.core.nudges import nudges_for
from allworth_api.data.household import (
    get_client_persona,
    get_dashboard_data,
    get_portfolio,
    get_spending,
)
from allworth_api.data.seed import advisor_for_client, seed_for
from allworth_api.financial_tools.performance import period_performance_from_values

router = APIRouter()


@router.get("/api/clients/{client_id}/dashboard")
def dashboard(client_id: str, household_id: str = Depends(get_current_household)):
    # Enforce: requested client_id must match authenticated household
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    d = get_dashboard_data(client_id)
    a = d["accounts"]
    s = d["spending"]
    seed = seed_for(client_id)
    advisor = advisor_for_client(client_id)
    mode = data_mode()
    is_live = mode == "live"
    return {
        "client": d["client"],
        "advisor": advisor,
        "netWorth": a["netWorth"],
        "netWorthHistory": d["net_worth_history"],
        "performanceCashFlows": d.get("performance_cash_flows", []),
        "performance": {
            "netWorth": period_performance_from_values(
                d["net_worth_history"], d.get("performance_cash_flows", [])
            ),
        },
        "allworthTotal": a["allworthTotal"],
        "heldAwayTotal": a["heldAwayTotal"],
        "liabilitiesTotal": a["liabilitiesTotal"],
        "accounts": {"allworth": a["allworth"], "outside": a["outside"]},
        "spending": {"avg3mo": s["avg3mo"], "plan": s["plan"], "overPlanPct": s["overPlanPct"]},
        "nudges": nudges_for(client_id),
        "liquidityEvent": seed["liquidityEvent"],
        "dataStatus": {
            "mode": mode,
            "label": "Live data" if is_live else "Synthetic demo data",
            "generatedAt": seed["generatedAt"],
            # Only surface asOf when it's an actual date — the seed's
            # placeholder ("deterministic") otherwise renders as the footer
            # copy "synthetic data, as of deterministic".
            "asOf": seed["generatedAt"] if any(c.isdigit() for c in str(seed["generatedAt"])) else None,
            "isSynthetic": not is_live,
            "isStale": False,
        },
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
def forget(client_id: str, fact_id: str, household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    fact = forget_fact(client_id, fact_id)
    if not fact:
        return JSONResponse(status_code=404, content={"error": "fact not found or not active"})
    return {"ok": True, "fact": fact}


@router.get("/api/clients/{client_id}/proactive")
def proactive(client_id: str, session: str = "wednesday", household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
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
            "suggested": suggested_for(session, client_id),
        }
    return {
        "message": (
            f"Hi {first_name} — I can pull your financial picture together, run scenarios, compare "
            "trade-offs, or score progress toward a goal. What would you like to dig into?"
        ),
        "basedOn": None,
        "suggested": suggested_for(session, client_id),
    }


@router.get("/api/clients/{client_id}/meeting-notes")
def meeting_notes(client_id: str, household_id: str = Depends(get_current_household)):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    return {"clientId": client_id, "notes": seed_for(client_id).get("meeting_notes", [])}


@router.get("/api/clients/{client_id}/chat-history")
def chat_history(
    client_id: str,
    session: str = "wednesday",
    household_id: str = Depends(get_current_household),
):
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    return {"episodes": episodes_for(client_id, session)}


@router.get("/api/clients/{client_id}/conversation")
async def conversation(
    client_id: str,
    session: str = "wednesday",
    household_id: str = Depends(get_current_household),
):
    """The stored thread, oldest first, including advisor interjections.

    Unlike chat-history (episodes, disabled when profile memory is off), this
    reads the Redis-backed conversation store, so it works in production. The
    client app polls it to surface advisor interjections; the advisor view
    renders it as the live transcript. Advisor turns are stored with a
    prefixed `content` for the LLM but expose their clean `displayText` here.
    """
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    turns = await load_turns(client_id, session)
    messages = []
    for seq, turn in enumerate(turns):
        if turn.get("kind") == "advisor":
            messages.append(
                {
                    "seq": seq,
                    "id": turn.get("id"),
                    "role": "advisor",
                    "text": turn.get("displayText") or "",
                    "advisorId": turn.get("advisorId"),
                    "advisorName": turn.get("advisorName"),
                    "ts": turn.get("ts"),
                }
            )
        else:
            messages.append(
                {
                    "seq": seq,
                    "id": None,
                    "role": turn.get("role"),
                    "text": turn.get("content") or "",
                    "ts": None,
                }
            )
    return {"messages": messages}
