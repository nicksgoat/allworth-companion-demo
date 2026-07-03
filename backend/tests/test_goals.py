"""Goals endpoints: funded-status GET and live goal-plan POST + merge."""

from __future__ import annotations

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.core import client_store

client = TestClient(app)


def _reset_plans(client_id: str) -> None:
    client_store._mem_plans.pop(client_id, None)


def test_goals_returns_funded_status() -> None:
    _reset_plans("maya")
    res = client.get("/api/clients/maya/goals")
    assert res.status_code == 200
    data = res.json()
    assert "goals" in data and "summary" in data
    lake = next(g for g in data["goals"] if g["label"] == "Lake house")
    assert lake["target"] == 350000
    assert lake["fundedPct"] > 0
    assert "monthlyContributionToClose" in lake


def test_goals_forbidden_for_other_household() -> None:
    res = client.get("/api/clients/kenny/goals")
    assert res.status_code == 403


def test_save_goal_plan_and_merge() -> None:
    _reset_plans("maya")
    res = client.post(
        "/api/clients/maya/goals/goal_lake/plan",
        json={"monthly": 4500, "years": 4},
    )
    assert res.status_code == 200
    assert res.json()["plan"]["monthly"] == 4500

    data = client.get("/api/clients/maya/goals").json()
    lake = next(g for g in data["goals"] if g["id"] == "goal_lake")
    assert lake["committedMonthly"] == 4500
    assert lake["committedYears"] == 4
    assert "projectedWithPlan" in lake
    # $4,500/mo over 4 years closes a ~$210k gap comfortably.
    assert lake["onTrackWithPlan"] is True
    assert lake["status"] == "on_track"
    _reset_plans("maya")


def test_save_goal_plan_validations() -> None:
    assert (
        client.post("/api/clients/maya/goals/goal_lake/plan", json={"monthly": 0, "years": 4}).status_code
        == 400
    )
    assert (
        client.post("/api/clients/maya/goals/nope/plan", json={"monthly": 100, "years": 4}).status_code
        == 404
    )
