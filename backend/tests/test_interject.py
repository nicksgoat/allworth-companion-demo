"""Advisor interjection: POST into a client thread, read back via /conversation.

Runs in-process in mock mode like test_api.py — the conversation store uses its
in-process fallback (no REDIS_URL), so each test seeds/clears its own thread.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from allworth_api.app import app
from allworth_api.core import conversation_store

client = TestClient(app)

SESSION = "wednesday"


def _clear(client_id: str) -> None:
    asyncio.get_event_loop().run_until_complete(conversation_store.clear(client_id))


def test_interject_appears_in_conversation_with_attribution() -> None:
    _clear("maya")
    res = client.post(
        "/api/advisors/clients/maya/interject",
        json={"session": SESSION, "text": "Hi Maya — saw your IPO question, let's talk Friday."},
    )
    assert res.status_code == 200
    posted = res.json()["message"]
    assert posted["role"] == "advisor"
    assert posted["advisorName"] == "Nicole Mayer"
    assert posted["id"]

    convo = client.get(f"/api/clients/maya/conversation?session={SESSION}").json()["messages"]
    assert len(convo) == 1
    msg = convo[0]
    # The clean display text comes back — not the LLM-facing prefixed content.
    assert msg["text"] == "Hi Maya — saw your IPO question, let's talk Friday."
    assert msg["role"] == "advisor"
    assert msg["id"] == posted["id"]
    assert msg["advisorName"] == "Nicole Mayer"
    _clear("maya")


def test_interject_orders_after_existing_turns_and_feeds_llm_history() -> None:
    _clear("maya")
    asyncio.get_event_loop().run_until_complete(
        conversation_store.append_turns(
            "maya",
            SESSION,
            [
                {"role": "user", "content": "What is my net worth?"},
                {"role": "assistant", "content": "Your net worth is $2,746,000."},
            ],
        )
    )
    client.post(
        "/api/advisors/clients/maya/interject",
        json={"session": SESSION, "text": "Nice question — bring this to our review."},
    )

    convo = client.get(f"/api/clients/maya/conversation?session={SESSION}").json()["messages"]
    assert [m["role"] for m in convo] == ["user", "assistant", "advisor"]
    assert convo[2]["seq"] == 2

    # The stored turn the model replays is user-role with clear attribution.
    turns = asyncio.get_event_loop().run_until_complete(
        conversation_store.load_turns("maya", SESSION)
    )
    assert turns[2]["role"] == "user"
    assert turns[2]["content"].startswith("[Message from Nicole Mayer, the client's advisor")
    assert "bring this to our review" in turns[2]["content"]
    _clear("maya")


def test_interject_rejects_empty_text() -> None:
    res = client.post(
        "/api/advisors/clients/maya/interject",
        json={"session": SESSION, "text": "   "},
    )
    assert res.status_code == 400


def test_interject_uses_the_clients_assigned_advisor() -> None:
    # kenny's advisor is Kyle, not Nicole.
    _clear("kenny")
    res = client.post(
        "/api/advisors/clients/kenny/interject",
        json={"session": SESSION, "text": "Kenny — quick note on NVDA."},
    )
    assert res.status_code == 200
    assert res.json()["message"]["advisorId"] == "kyle"
    _clear("kenny")
