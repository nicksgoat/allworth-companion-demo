"""API contract tests for the Allworth demo backend.

Runs in-process against the real FastAPI app in mock (seed) mode — no running
server, no API key.

Run:  cd backend && uv run --with pytest --with httpx python -m pytest tests
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.config import cors_origins, demo_auth_fallback_enabled, seed_auth_enabled
from allworth_api.core import chat_service
from allworth_api.core.auth import get_current_household, get_session
from allworth_api.data.household import _resolve_hh

client = TestClient(app)


# ── Data-source switch ───────────────────────────────────────────────────────


def test_defaults_to_mock_mode() -> None:
    # The whole demo must serve seed data unless DATA_MODE=live is set.
    assert _resolve_hh("maya") is None
    assert client.get("/api/health").json()["synapse"] is False


def test_production_defaults_disable_demo_fallback_and_wildcard_cors(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ALLOW_DEMO_AUTH_FALLBACK", raising=False)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    assert demo_auth_fallback_enabled() is False
    assert seed_auth_enabled() is False
    assert cors_origins() == []


def test_production_requires_auth_and_hides_admin_routes(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ALLOW_DEMO_AUTH_FALLBACK", raising=False)

    app.dependency_overrides = {}
    r = client.get("/api/clients/maya/dashboard")
    assert r.status_code == 401

    app.dependency_overrides[get_current_household] = lambda: "maya"
    try:
        assert client.get("/api/route-intent", params={"q": "retirement"}).status_code == 404
        assert client.get("/api/audit/tail").status_code == 404
        assert client.post("/api/demo/reset", json={"clientId": "maya"}).status_code == 404
    finally:
        app.dependency_overrides = {}
        monkeypatch.setenv("APP_ENV", "development")


def test_email_login_works_in_mock_mode() -> None:
    # The Sign-In screen uses email login — it must resolve against seed in mock
    # mode (case-insensitive), or the demo can't get past the login screen.
    r = client.post("/api/auth/login/email", json={"email": "MAYA@example.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["householdId"] == "maya"
    assert body["contactName"] == "Maya Tran"
    bad = client.post("/api/auth/login/email", json={"email": "nobody@nowhere.com"})
    assert bad.status_code == 401


def test_signed_auth_token_scopes_protected_routes(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret-for-stateless-auth")
    r = client.post("/api/auth/login/email", json={"email": "maya@example.com"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert get_session(token).household_id == "maya"

    authed = client.get("/api/clients/maya/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200

    tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
    assert get_session(tampered) is None


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


def test_chat_returns_error_when_llm_provider_unavailable() -> None:
    previous_provider = chat_service.provider
    chat_service.provider = None
    try:
        r = client.post(
            "/api/chat",
            json={"clientId": "maya", "session": "monday", "message": "Can I afford a car?"},
        )
        assert r.status_code == 200
        assert "event: error" in r.text
        assert "temporarily unavailable" in r.text
    finally:
        chat_service.provider = previous_provider
