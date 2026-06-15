"""API contract + chat-routing regression tests for the Allworth demo backend.

Runs in-process against the real FastAPI app in mock (seed) mode — no running
server, no API key. The chat tests are the regression guard for the scripted
flow: a clicked question must land on the matching answer, never an unrelated one.

Run:  cd backend && uv run --with pytest --with httpx python -m pytest tests
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.data.household import _resolve_hh

client = TestClient(app)


# ── Data-source switch ───────────────────────────────────────────────────────


def test_defaults_to_mock_mode() -> None:
    # The whole demo must serve seed data unless DATA_MODE=live is set.
    assert _resolve_hh("maya") is None
    assert client.get("/api/health").json()["synapse"] is False


# ── Screen data is grounded (and matches what the chat will claim) ───────────


def test_dashboard_grounded() -> None:
    d = client.get("/api/clients/maya/dashboard").json()
    assert d["netWorth"] == 2_746_000
    assert d["client"]["name"].startswith("Maya")
    assert d["allworthTotal"] == 2_445_000


def test_spending_over_plan() -> None:
    s = client.get("/api/clients/maya/spending").json()
    assert s["avg3mo"] == 16_500
    assert s["plan"] == 14_000
    assert s["overPlanPct"] == 18


def test_portfolio_has_robinhood_concentration() -> None:
    p = client.get("/api/clients/maya/portfolio").json()
    rh = [x for x in p["positions"] if x["accountId"] == "acct_rh"]
    nvda = next(x for x in rh if x["symbol"] == "NVDA")
    total = sum(x["value"] for x in rh)
    assert round(nvda["value"] / total * 100) == 54


def test_proactive_opening_chips() -> None:
    for session in ("monday", "wednesday"):
        r = client.get(f"/api/clients/maya/proactive?session={session}").json()
        assert len(r["suggested"]) >= 2  # opening chips are seeded


# ── Chat routing regression guard ────────────────────────────────────────────


def _ask(message: str, session: str) -> tuple[str, list[str]]:
    """POST a chat turn and reconstruct the assistant text + final sources from SSE."""
    r = client.post("/api/chat", json={"clientId": "maya", "session": session, "message": message})
    assert r.status_code == 200
    text, sources = [], []
    for line in r.text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "delta" in obj:
            text.append(obj["delta"])
        if "sources" in obj:
            sources = obj.get("sources") or []
    return "".join(text), sources


# (message, session, signature phrase that must appear in the answer)
ROUTING_CASES = [
    # The original bug: a spending question must NOT return the IPO script.
    ("I know we've been spending more — what does that mean for my plan?", "wednesday", "spending has crept up"),
    ("What are my options for the concentrated position you flagged?", "wednesday", "NVIDIA is about 54"),
    ("What's my net worth?", "monday", "whole picture"),
    ("How am I invested?", "monday", "actually invested"),
    ("Am I on track for the lake house?", "monday", "goals against where"),
    ("Should I sell my Apple shares?", "monday", "lay out the tax side"),
    ("Should I do a Roth conversion?", "monday", "Roth conversion is one"),
    ("Honestly, just tell me what to do", "monday", "straight about how I work"),
    ("What would $200K into the SpaceX IPO mean for me?", "monday", "actually mean for you"),
    ("Where did we land on the SpaceX IPO?", "wednesday", "Last time you were weighing"),
    ("What changed since I was last here?", "wednesday", "what's changed since Monday"),
    ("hello there", "monday", "Allworth Companion"),  # off-topic -> graceful greeting
]


def test_chat_routing_regression_guard() -> None:
    failures = []
    for message, session, signature in ROUTING_CASES:
        text, _ = _ask(message, session)
        if signature not in text:
            failures.append(f"{message!r} ({session}) did not route to {signature!r}")
    assert not failures, "Chat misrouted:\n" + "\n".join(failures)


def test_spending_question_is_not_ipo() -> None:
    # Belt-and-suspenders on the exact bug Steven reported.
    text, sources = _ask(
        "I know we've been spending more the last few months — what does that mean for my plan?",
        "wednesday",
    )
    assert "spending has crept up" in text
    assert "SpaceX IPO" not in text
    assert sources == ["Spending", "Financial plan"]
