"""Advisor concierge: availability grid + booking/topic requests round trip."""

from __future__ import annotations

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.core import client_store

client = TestClient(app)


def _reset(client_id: str) -> None:
    client_store._mem_requests.pop(client_id, None)


def test_availability_shape_and_stability() -> None:
    a = client.get("/api/clients/maya/availability").json()
    b = client.get("/api/clients/maya/availability").json()
    assert a == b  # deterministic per advisor+date
    assert len(a["days"]) == 10
    for day in a["days"]:
        assert 3 <= len(day["slots"]) <= 5
        for slot in day["slots"]:
            assert slot["iso"].startswith(day["dateISO"])
            assert slot["display"]


def test_booking_round_trip_to_advisor_view() -> None:
    _reset("maya")
    day = client.get("/api/clients/maya/availability").json()["days"][0]
    slot = day["slots"][0]
    res = client.post(
        "/api/clients/maya/requests",
        json={
            "kind": "booking",
            "slotISO": slot["iso"],
            "slotDisplay": f"{day['longLabel']} · {slot['display']}",
        },
    )
    assert res.status_code == 200
    rec = res.json()["request"]
    assert rec["status"] == "requested"
    assert rec["clientName"].startswith("Maya")

    inbox = client.get("/api/advisors/clients/maya/requests").json()["requests"]
    assert inbox[0]["id"] == rec["id"]
    _reset("maya")


def test_topic_request_and_validation() -> None:
    _reset("maya")
    ok = client.post(
        "/api/clients/maya/requests",
        json={"kind": "topic", "topic": "Roth conversion timing"},
    )
    assert ok.status_code == 200
    assert (
        client.post("/api/clients/maya/requests", json={"kind": "topic", "topic": "  "}).status_code
        == 400
    )
    assert (
        client.post("/api/clients/maya/requests", json={"kind": "booking"}).status_code == 400
    )
    assert (
        client.post("/api/clients/maya/requests", json={"kind": "other"}).status_code == 400
    )
    _reset("maya")
