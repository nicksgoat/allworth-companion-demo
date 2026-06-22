"""API contract tests for the Allworth demo backend.

Runs in-process against the real FastAPI app in mock (seed) mode — no running
server, no API key.

Run:  cd backend && uv run --with pytest --with httpx python -m pytest tests
"""

from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.config import (
    cors_origins,
    demo_auth_fallback_enabled,
    runtime_config_status,
    seed_auth_enabled,
)
from allworth_api.core import chat_service
from allworth_api.core.auth import get_current_household, get_session
from allworth_api.core.observability import hash_household_id
from allworth_api.core.rate_limit import reset_rate_limits
from allworth_api.core.routing import route_intent
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
    assert "SESSION_SECRET is required in production" in runtime_config_status()["errors"]


def test_azure_openai_config_reports_missing_deployment_settings(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "azure_openai")
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)

    errors = runtime_config_status()["errors"]
    assert "AZURE_OPENAI_ENDPOINT is required for azure_openai" in errors
    assert "AZURE_OPENAI_API_KEY is required for azure_openai" in errors


def test_production_live_mode_requires_entra_auth(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.setenv("SYNAPSE_SERVER", "synapse.example")
    monkeypatch.setenv("SESSION_SECRET", "prod-secret")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("LLM_PROVIDER", "azure_openai")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("LLM_CHAT_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_EXTRACT_MODEL", "gpt-4o")
    monkeypatch.setenv("AUTH_PROVIDER", "stateless")
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    monkeypatch.delenv("ENTRA_CLIENT_ID", raising=False)
    monkeypatch.delenv("ENTRA_AUDIENCE", raising=False)

    errors = runtime_config_status()["errors"]
    assert "AUTH_PROVIDER=entra is required for production DATA_MODE=live" in errors

    monkeypatch.setenv("AUTH_PROVIDER", "entra")
    errors = runtime_config_status()["errors"]
    assert "ENTRA_TENANT_ID is required for AUTH_PROVIDER=entra" in errors
    assert "ENTRA_CLIENT_ID is required for AUTH_PROVIDER=entra" in errors
    assert "ENTRA_AUDIENCE is required for AUTH_PROVIDER=entra" in errors


def test_production_profile_memory_requires_governed_durable_store(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "prod-secret")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("PROFILE_MEMORY_ENABLED", "true")
    monkeypatch.setenv("PROFILE_MEMORY_STORE", "local_json")
    monkeypatch.delenv("PROFILE_MEMORY_GOVERNANCE_ACK", raising=False)

    errors = runtime_config_status()["errors"]
    assert "PROFILE_MEMORY_ENABLED=true in production requires a durable PROFILE_MEMORY_STORE" in errors
    assert (
        "PROFILE_MEMORY_ENABLED=true in production requires PROFILE_MEMORY_GOVERNANCE_ACK=true"
        in errors
    )

    monkeypatch.setenv("PROFILE_MEMORY_STORE", "postgres")
    monkeypatch.setenv("PROFILE_MEMORY_GOVERNANCE_ACK", "true")
    errors = runtime_config_status()["errors"]
    assert "PROFILE_MEMORY_ENABLED=true in production requires a durable PROFILE_MEMORY_STORE" not in errors


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


def test_health_live_and_ready_reflect_runtime_config(monkeypatch) -> None:
    assert client.get("/api/health/live").json()["ok"] is True

    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.delenv("SYNAPSE_SERVER", raising=False)
    monkeypatch.delenv("ALLOW_SEED_FALLBACK_IN_LIVE", raising=False)
    ready = client.get("/api/health/ready")
    assert ready.status_code == 503
    assert "DATA_MODE=live requires SYNAPSE_SERVER" in ready.json()["detail"]["config"]["errors"]
    monkeypatch.setenv("DATA_MODE", "mock")


def test_live_mode_without_synapse_does_not_silently_use_seed(monkeypatch) -> None:
    monkeypatch.setenv("DATA_MODE", "live")
    monkeypatch.delenv("SYNAPSE_SERVER", raising=False)
    monkeypatch.delenv("ALLOW_SEED_FALLBACK_IN_LIVE", raising=False)

    try:
        _resolve_hh("maya")
    except RuntimeError as err:
        assert "Synapse is not configured" in str(err)
    else:
        raise AssertionError("live mode without Synapse should fail unless fallback is explicit")
    finally:
        monkeypatch.setenv("DATA_MODE", "mock")


def test_email_login_works_in_mock_mode() -> None:
    # The Sign-In screen uses email login — it must resolve against seed in mock
    # mode (case-insensitive), or the demo can't get past the login screen.
    r = client.post("/api/auth/login/email", json={"email": "NICOLE@demo.com"})
    assert r.status_code == 200
    body = r.json()
    assert body["householdId"] == "maya"
    assert body["contactName"] == "Maya Tran"
    bad = client.post("/api/auth/login/email", json={"email": "nobody@nowhere.com"})
    assert bad.status_code == 401


def test_demo_passcode_login_is_hidden_when_demo_fallback_disabled(monkeypatch) -> None:
    monkeypatch.setenv("ALLOW_DEMO_AUTH_FALLBACK", "false")
    r = client.post("/api/auth/login", json={"householdId": "maya", "passcode": "demo"})
    assert r.status_code == 404


def test_signed_auth_token_scopes_protected_routes(monkeypatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret-for-stateless-auth")
    r = client.post("/api/auth/login/email", json={"email": "nicole@demo.com"})
    assert r.status_code == 200
    token = r.json()["token"]
    assert get_session(token).household_id == "maya"

    authed = client.get("/api/clients/maya/dashboard", headers={"Authorization": f"Bearer {token}"})
    assert authed.status_code == 200


def test_request_logging_uses_signed_token_household_and_returns_request_id(
    monkeypatch,
    caplog,
) -> None:
    monkeypatch.setenv("SESSION_SECRET", "test-secret-for-stateless-auth")
    token = client.post("/api/auth/login/email", json={"email": "nicole@demo.com"}).json()["token"]

    with caplog.at_level(logging.INFO, logger="allworth_api.request"):
        r = client.get(
            "/api/clients/maya/dashboard",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Id": "req_test_123",
            },
        )

    assert r.status_code == 200
    assert r.headers["X-Request-Id"] == "req_test_123"

    request_logs = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "allworth_api.request" and '"event":"request"' in record.message
    ]
    dashboard_log = next(log for log in request_logs if log["path"] == "/api/clients/maya/dashboard")
    assert dashboard_log["request_id"] == "req_test_123"
    assert dashboard_log["household_hash"] == hash_household_id("maya")
    assert dashboard_log["status"] == 200
    assert dashboard_log["latency_ms"] >= 0

    tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
    assert get_session(tampered) is None


def test_household_scoping_covers_profile_chat_and_advisor_routes() -> None:
    app.dependency_overrides[get_current_household] = lambda: "maya"
    try:
        assert client.get("/api/clients/other/profile").status_code == 403
        assert client.get("/api/clients/other/proactive").status_code == 403
        assert client.get("/api/clients/other/chat-history").status_code == 403
        assert client.delete("/api/clients/other/facts/fact_1").status_code == 403
        assert client.get("/api/advisors/dana/clients/other/brief").status_code == 403
    finally:
        app.dependency_overrides = {}


def test_advisor_brief_includes_review_workflow() -> None:
    app.dependency_overrides[get_current_household] = lambda: "maya"
    try:
        response = client.get("/api/advisors/nicole/clients/maya/brief")
    finally:
        app.dependency_overrides = {}

    assert response.status_code == 200
    workflow = response.json()["reviewWorkflow"]
    assert workflow["status"] == "advisor_review_required"
    assert len(workflow["decisionsToReview"]) >= 3
    assert any(item["id"] == "held-away-assets" for item in workflow["decisionsToReview"])
    assert workflow["talkingPoints"]
    assert workflow["openQuestions"]
    assert "directive" in " ".join(workflow["talkingPoints"]).lower()


def test_app_level_rate_limit_for_tool_routes(monkeypatch) -> None:
    reset_rate_limits()
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_WINDOW", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    payload = {"initial_value": 100_000, "years": 1, "n_simulations": 10}
    try:
        assert client.post("/tools/simulate", json=payload).status_code == 200
        assert client.post("/tools/simulate", json=payload).status_code == 200
        limited = client.post("/tools/simulate", json=payload)
        assert limited.status_code == 429
        assert limited.headers["X-RateLimit-Remaining"] == "0"
    finally:
        reset_rate_limits()
        monkeypatch.delenv("RATE_LIMIT_ENABLED", raising=False)


def test_app_level_rate_limit_for_feedback_route(monkeypatch, caplog) -> None:
    reset_rate_limits()
    monkeypatch.setenv("SESSION_SECRET", "test-secret-for-stateless-auth")
    token = client.post("/api/auth/login/email", json={"email": "nicole@demo.com"}).json()["token"]
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_PER_WINDOW", "2")
    monkeypatch.setenv("RATE_LIMIT_WINDOW_SECONDS", "60")
    payload = {
        "clientId": "maya",
        "conversationId": "maya:wednesday",
        "messageId": "msg_limit",
        "rating": "positive",
        "sources": ["Client context"],
        "toolCalls": ["get_client_context"],
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        assert client.post("/api/chat/feedback", json=payload, headers=headers).status_code == 200
        assert client.post("/api/chat/feedback", json=payload, headers=headers).status_code == 200
        with caplog.at_level(logging.INFO, logger="allworth_api.rate_limit"):
            limited = client.post("/api/chat/feedback", json=payload, headers=headers)

        assert limited.status_code == 429
        assert limited.headers["X-RateLimit-Remaining"] == "0"
        logs = [
            json.loads(record.message)
            for record in caplog.records
            if record.name == "allworth_api.rate_limit"
        ]
        assert logs[-1]["event"] == "rate_limit"
        assert logs[-1]["path"] == "/api/chat/feedback"
        assert logs[-1]["household_hash"] == hash_household_id("maya")
    finally:
        reset_rate_limits()
        monkeypatch.delenv("RATE_LIMIT_ENABLED", raising=False)


# ── Screen data is grounded (and matches what the chat will claim) ───────────


def test_dashboard_grounded() -> None:
    d = client.get("/api/clients/maya/dashboard").json()
    assert d["netWorth"] == 2_746_000
    assert d["client"]["name"].startswith("Maya")
    assert d["allworthTotal"] == 2_445_000
    assert d["performance"]["netWorth"]["method"] == "modified_dietz"
    assert d["performance"]["netWorth"]["return_pct"] > 0
    assert d["performance"]["netWorth"]["calculation"]["formula"] == (
        "(ending_value - outflow) / (beginning_value + inflow)"
    )
    assert d["performance"]["netWorth"]["inflow"] >= 0
    assert d["performance"]["netWorth"]["outflow"] > 0
    assert d["performance"]["netWorth"]["ratio"] == round(
        d["performance"]["netWorth"]["adjusted_ending_value"]
        / d["performance"]["netWorth"]["adjusted_beginning_value"],
        6,
    )
    assert d["dataStatus"]["label"] == "Synthetic demo data"
    assert d["dataStatus"]["isSynthetic"] is True


def test_spending_over_plan() -> None:
    s = client.get("/api/clients/maya/spending").json()
    assert s["avg3mo"] == 16_500
    assert s["plan"] == 14_000
    assert s["overPlanPct"] == 18


def test_portfolio_has_robinhood_concentration() -> None:
    p = client.get("/api/clients/maya/portfolio").json()
    assert "taxLots" not in p
    rh = [x for x in p["positions"] if x["accountId"] == "acct_rh"]
    nvda = next(x for x in rh if x["symbol"] == "NVDA")
    total = sum(x["value"] for x in rh)
    assert round(nvda["value"] / total * 100) == 54
    aapl = next(x for x in p["positions"] if x["accountId"] == "acct_trust" and x["symbol"] == "AAPL")
    assert aapl["averageCostBasis"] > 0
    assert aapl["costBasis"] > 0
    assert "longTermUnrealizedGain" in aapl
    assert "shortTermUnrealizedGain" in aapl


def test_proactive_opening_chips() -> None:
    for session in ("monday", "wednesday"):
        r = client.get(f"/api/clients/maya/proactive?session={session}").json()
        assert len(r["suggested"]) >= 2  # opening chips are seeded
        assert r["suggested"] != [
            "Am I on track for retirement?",
            "Can I afford a $50,000 car?",
            "What would rebalancing to 70/30 look like?",
        ]
        assert any("spending" in s.lower() or "nvda" in s.lower() for s in r["suggested"])


def test_chat_suggestions_follow_latest_user_question() -> None:
    assert chat_service.suggested_for("monday", "maya") == [
        "How does this spending affect my plan?",
        "What are my options for NVDA?",
        "What are my options for TSLA?",
    ]
    assert chat_service.contextual_suggestions(
        {"Monte Carlo simulation"},
        "monday",
        "Am I on track for retirement?",
    ) == [
        "What improves my odds the most?",
        "What if I retire one year later?",
        "How bad is the downside case?",
    ]
    assert chat_service.contextual_suggestions(
        {"Monte Carlo simulation"},
        "monday",
        "Can I afford a $50,000 car?",
    ) == [
        "How would paying cash affect retirement odds?",
        "Which funding source creates the least tax drag?",
        "What monthly payment would still fit the plan?",
    ]
    assert chat_service.contextual_suggestions(
        {"Mock rebalance"},
        "monday",
        "What would rebalancing to 70/30 look like?",
    ) == [
        "Show the tax impact of moving to 70/30",
        "Which holdings would be sold first?",
        "What if we limit realized gains?",
    ]


def test_chat_memory_sanitizes_stale_advisor_names() -> None:
    assert (
        chat_service._sanitize_advisor_references(
            "We ended with a list of questions to bring to Dana before the deadline.",
            "Nicole Mayer",
        )
        == "We ended with a list of questions to bring to Nicole before the deadline."
    )
    assert chat_service._sanitize_messages(
        [{"role": "assistant", "content": "Dana can review this."}],
        "Nicole Mayer",
    ) == [{"role": "assistant", "content": "Nicole can review this."}]


def test_chat_repairs_missing_advisor_handoff() -> None:
    repaired, suffix = chat_service._ensure_advisor_handoff(
        "The main change is that spending is still running above plan.",
        "Nicole Mayer",
    )
    already_ok, no_suffix = chat_service._ensure_advisor_handoff(
        "Nicole can review how spending affects the plan.",
        "Nicole Mayer",
    )

    assert "pressure-testing with Nicole" in repaired
    assert suffix
    assert already_ok == "Nicole can review how spending affects the plan."
    assert no_suffix == ""


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


def test_chat_feedback_accepts_household_scoped_quality_signal(caplog) -> None:
    app.dependency_overrides[get_current_household] = lambda: "maya"
    try:
        with caplog.at_level(logging.INFO, logger="allworth_api.feedback"):
            ok = client.post(
                "/api/chat/feedback",
                headers={"X-Request-Id": "req_feedback_123"},
                json={
                    "clientId": "maya",
                    "conversationId": "maya:wednesday",
                    "messageId": "msg_1",
                    "rating": "positive",
                    "sources": ["Client context"],
                    "toolCalls": ["get_client_context"],
                    "quality": {
                        "vision_score": 92,
                        "missing": [],
                        "safety_flags": [],
                    },
                },
            )
        denied = client.post(
            "/api/chat/feedback",
            json={"clientId": "other", "messageId": "msg_1", "rating": "positive"},
        )
        invalid = client.post(
            "/api/chat/feedback",
            json={"clientId": "maya", "messageId": "msg_1", "rating": "maybe"},
        )
        assert ok.status_code == 200
        assert ok.json()["ok"] is True
        assert ok.json()["feedback"]["request_id"] == "req_feedback_123"
        assert ok.json()["feedback"]["quality"]["vision_score"] == 92
        feedback_logs = [
            json.loads(record.message)
            for record in caplog.records
            if record.name == "allworth_api.feedback"
        ]
        assert feedback_logs[-1]["event"] == "chat_feedback"
        assert feedback_logs[-1]["request_id"] == "req_feedback_123"
        assert feedback_logs[-1]["vision_score"] == 92
        assert feedback_logs[-1]["source_count"] == 1
        assert denied.status_code == 403
        assert invalid.status_code == 400
    finally:
        app.dependency_overrides = {}


def test_financial_intent_routing_prefers_schema_governed_tools() -> None:
    rebalance_matches = [m.tool for m in route_intent("rebalance my AWF Core-Satellite 60/40 model")]
    simulate_matches = [m.tool for m in route_intent("can i afford a car in retirement")]
    continuity_matches = [m.tool for m in route_intent("what changed since last time?")]

    assert rebalance_matches[0] == "rebalance"
    assert "simulate" in simulate_matches
    assert continuity_matches[0] == "get_client_profile"
