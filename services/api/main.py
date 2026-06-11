# Allworth Companion demo backend (FastAPI). Demo-grade by design: no auth,
# in-memory conversation state, synthetic data only.
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")  # before chat reads ANTHROPIC_API_KEY

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

import chat
from data import accounts_for, fmt_usd, portfolio_for, seed, spending_summary
from memory import active_facts, episodes_for, forget_fact, reset_profile
from nudges import nudges_for
from tools import run_tool

app = FastAPI()


@app.get("/api/health")
def health():
    return {"ok": True, "llm": chat.client is not None, "generatedAt": seed["generatedAt"]}


@app.get("/api/clients/{client_id}/dashboard")
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


@app.get("/api/clients/{client_id}/nudges")
def nudges(client_id: str):
    return {"nudges": nudges_for(client_id)}


@app.get("/api/clients/{client_id}/spending")
def spending(client_id: str, months: int = 3):
    return spending_summary(months or 3)


@app.get("/api/clients/{client_id}/portfolio")
def portfolio(client_id: str):
    return portfolio_for()


@app.get("/api/clients/{client_id}/profile")
def profile(client_id: str):
    return {"clientId": client_id, "facts": active_facts(client_id)}


# Governed memory: "Forget this detail" — marks the fact deleted, never erases it.
@app.delete("/api/clients/{client_id}/facts/{fact_id}")
def forget(client_id: str, fact_id: str):
    fact = forget_fact(client_id, fact_id)
    if not fact:
        return JSONResponse(status_code=404, content={"error": "fact not found or not active"})
    return {"ok": True, "fact": fact}


# Proactive greeting for the chat screen — deterministic so Beat 4 never flakes.
@app.get("/api/clients/{client_id}/proactive")
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
                "suggested": chat.suggested_for(session),
            }
    return {
        "message": "Hi Maya — I can help you understand your accounts, spending, plan, or anything "
        "you're weighing. What's on your mind?",
        "basedOn": None,
        "suggested": chat.suggested_for(session),
    }


@app.get("/api/clients/{client_id}/chat-history")
def chat_history(client_id: str, session: str = "wednesday"):
    return {"session": session, "episodes": episodes_for(client_id, session)}


@app.get("/api/advisors/{advisor_id}/book")
def book(advisor_id: str):
    # Maya's nudge count comes from the live rule engine; other households are static.
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


@app.get("/api/advisors/{advisor_id}/clients/{client_id}/brief")
def brief(advisor_id: str, client_id: str):
    data = run_tool("get_advisor_brief", {}, client_id)
    return {**data, "narrative": brief_narrative(data)}


@app.post("/api/chat")
async def post_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = body.get("clientId", "maya")
    session = body.get("session", "wednesday")
    message = body.get("message")
    if not message:
        return JSONResponse(status_code=400, content={"error": "message required"})
    return StreamingResponse(
        chat.stream_chat(client_id, session, message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/demo/reset")
async def demo_reset(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = (body or {}).get("clientId", "maya")
    chat.reset_conversations()
    profile = reset_profile(client_id)
    return {"ok": True, "clientId": client_id, "facts": len(profile["facts"])}


def brief_narrative(d):
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
