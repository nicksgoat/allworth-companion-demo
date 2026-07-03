import hashlib
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from allworth_api.config import data_mode
from allworth_api.core.auth import get_current_household, get_session_for_household
from allworth_api.core.chat_service import suggested_for
from allworth_api.core.client_store import append_request, save_goal_plan
from allworth_api.core.conversation_store import load_turns
from allworth_api.core.formatting import iso_now
from allworth_api.core.tool_runner import run_tool
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


# ── Goals (live goal planning) ────────────────────────────────────────────


@router.get("/api/clients/{client_id}/goals")
def goals(client_id: str, household_id: str = Depends(get_current_household)):
    """Funded-status view of the client's plan goals, incl. saved live plans.

    Same computation the chat tool uses (analyze_goal_funding), so the Goals
    sheet, the chat widget, and the model's answers all agree.
    """
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    return run_tool("analyze_goal_funding", {}, client_id)


class GoalPlanRequest(BaseModel):
    monthly: float = 0
    years: int = 0


@router.post("/api/clients/{client_id}/goals/{goal_id}/plan")
def save_goal_plan_route(
    client_id: str,
    goal_id: str,
    body: GoalPlanRequest,
    household_id: str = Depends(get_current_household),
):
    """Save the client's chosen funding plan for a goal ("adjustable live goal")."""
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    if body.monthly <= 0 or body.years <= 0:
        return JSONResponse(status_code=400, content={"error": "monthly and years are required"})
    known = {g["id"] for g in seed_for(client_id)["plan"].get("goals", [])}
    if goal_id not in known:
        return JSONResponse(status_code=404, content={"error": "Unknown goal"})
    plan = {"monthly": body.monthly, "years": body.years, "ts": iso_now()}
    save_goal_plan(client_id, goal_id, plan)
    return {"goalId": goal_id, "plan": plan}


# ── Advisor concierge: availability + requests ───────────────────────────

_SLOT_CANDIDATES = [
    ("09:00", "9:00 AM"),
    ("10:30", "10:30 AM"),
    ("11:15", "11:15 AM"),
    ("13:00", "1:00 PM"),
    ("14:00", "2:00 PM"),
    ("15:15", "3:15 PM"),
    ("16:30", "4:30 PM"),
]


@router.get("/api/clients/{client_id}/availability")
def availability(client_id: str, household_id: str = Depends(get_current_household)):
    """Synthetic Calendly-style availability for the client's advisor.

    Next 10 business days, 3-5 slots each. Deterministic per advisor+date
    (md5-seeded) so the grid is stable across refreshes and machines.
    """
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    advisor = advisor_for_client(client_id)
    days = []
    day = date.today() + timedelta(days=1)
    while len(days) < 10:
        if day.weekday() < 5:
            digest = hashlib.md5(f"{advisor['id']}:{day.isoformat()}".encode()).digest()
            count = 3 + digest[0] % 3  # 3-5 slots
            picks = sorted(
                range(len(_SLOT_CANDIDATES)),
                key=lambda i: digest[1 + i % 14],
            )[:count]
            slots = [
                {
                    "iso": f"{day.isoformat()}T{_SLOT_CANDIDATES[i][0]}",
                    "display": _SLOT_CANDIDATES[i][1],
                }
                for i in sorted(picks)
            ]
            days.append(
                {
                    "dateISO": day.isoformat(),
                    "label": day.strftime("%a %-d"),
                    "longLabel": day.strftime("%A, %B %-d"),
                    "slots": slots,
                }
            )
        day += timedelta(days=1)
    return {"advisor": advisor, "days": days}


class ClientRequest(BaseModel):
    kind: str = "booking"  # "booking" | "topic"
    slotISO: str = ""
    slotDisplay: str = ""
    topic: str = ""


@router.post("/api/clients/{client_id}/requests")
def create_request(
    client_id: str,
    body: ClientRequest,
    household_id: str = Depends(get_current_household),
):
    """Book a meeting or send a topic request — lands in the advisor's view."""
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    if body.kind not in ("booking", "topic"):
        return JSONResponse(status_code=400, content={"error": "kind must be booking or topic"})
    if body.kind == "booking" and not body.slotDisplay:
        return JSONResponse(status_code=400, content={"error": "slotDisplay is required"})
    if body.kind == "topic" and not body.topic.strip():
        return JSONResponse(status_code=400, content={"error": "topic is required"})
    persona = get_client_persona(client_id)
    record = {
        "id": uuid.uuid4().hex[:12],
        "kind": body.kind,
        "slotISO": body.slotISO,
        "slotDisplay": body.slotDisplay,
        "topic": body.topic.strip(),
        "clientId": client_id,
        "clientName": (persona or {}).get("name", client_id),
        "status": "requested",
        "ts": iso_now(),
    }
    append_request(client_id, record)
    return {"request": record}
