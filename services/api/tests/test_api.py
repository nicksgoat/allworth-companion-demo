from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_routes_roth_question() -> None:
    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "Should I do a Roth conversion this year?"}]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "roth_conversion"
    assert payload["result"]["cards"]
    assert "advisor" in payload["answer"].lower()


def test_portfolio_tax_loss_harvesting() -> None:
    response = client.post(
        "/api/tools/portfolio/run",
        json={
            "analysis": "tax_loss_harvesting",
            "portfolio": [
                {"symbol": "VXUS", "value": 200000, "cost_basis": 250000, "target_weight": 0.2}
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["tool"] == "tax_loss_harvesting"
    assert payload["data"]["candidates"][0]["symbol"] == "VXUS"


def test_planning_validation_rejects_bad_age() -> None:
    response = client.post(
        "/api/tools/planning/run",
        json={"analysis": "retirement_readiness", "household": {"primary_age": 8}},
    )
    assert response.status_code == 422

