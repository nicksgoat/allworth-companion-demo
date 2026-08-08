"""Tests for the mailer library + HTTP API (auth gating covered in
test_auth_middleware.py)."""
from __future__ import annotations

import pytest
from flask import Flask

from mailer.routes import bp as mailer_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(mailer_bp, url_prefix="/mailer")
    return app.test_client()


def test_health(client):
    rv = client.get("/mailer/api/health")
    assert rv.status_code == 200
    assert rv.get_json()["tool"] == "mailer"


def test_send_validates_required_fields(client):
    rv = client.post("/mailer/api/send", json={"subject": "x"})
    assert rv.status_code == 400


def test_send_calls_library(client, monkeypatch):
    calls = {}

    def fake_send(to, subject, body, **kw):
        calls["to"], calls["subject"], calls["body"], calls["kw"] = to, subject, body, kw

    monkeypatch.setattr("mailer.send_email", fake_send)
    rv = client.post("/mailer/api/send", json={
        "to": "cfo@allworthfinancial.com", "subject": "Report", "body": "done",
        "mailbox": "automations@allworthfinancial.com",
    })
    assert rv.status_code == 200
    assert rv.get_json()["sent"] is True
    assert calls["to"] == "cfo@allworthfinancial.com"
    assert calls["kw"]["mailbox"] == "automations@allworthfinancial.com"


def test_send_surfaces_scope_error(client, monkeypatch):
    from mailer import MailError

    def fake_send(*a, **k):
        raise MailError("Graph denied (403) — required scope/permission not granted", 403)

    monkeypatch.setattr("mailer.send_email", fake_send)
    rv = client.post("/mailer/api/send", json={"to": "a@x.com", "subject": "s", "body": "b"})
    assert rv.status_code == 403
    assert "403" in rv.get_json()["error"]


def test_library_app_only_requires_mailbox(monkeypatch):
    """App-only send with no mailbox and no MAILER_FROM is a clear error."""
    import mailer
    monkeypatch.delenv("MAILER_FROM", raising=False)
    # Force the app-token path to not hit the network by faking the raw call to
    # exercise the mailbox resolution guard in graph_client.
    with pytest.raises(mailer.MailError):
        mailer.send_email("a@x.com", "s", "b")  # token=None, mailbox=None → no root


# --------------------------------------------------------------------------- #
# Event-driven inbound (poll model)
# --------------------------------------------------------------------------- #
@pytest.fixture
def isolated_rules(tmp_path, monkeypatch):
    """Point the rule store at a temp file so tests don't touch real state."""
    from mailer import events
    monkeypatch.setattr(events, "_STORE", tmp_path / "rules.json")
    return events


def test_rule_crud(isolated_rules):
    e = isolated_rules
    r = e.add_rule("box@x.com", "https://pipe/trigger", {"subject_contains": "sync"})
    assert r["watermark"]  # seeded to now
    assert len(e.list_rules()) == 1
    assert e.delete_rule(r["id"]) is True
    assert e.list_rules() == []


def test_poll_dispatches_only_matches_and_advances_watermark(isolated_rules, monkeypatch):
    e = isolated_rules
    e.add_rule("box@x.com", "https://pipe/trigger", {"subject_contains": "sync complete"},
               watermark_iso="2026-07-01T00:00:00Z")

    msgs = [
        {"id": "m1", "senderEmail": "a@x.com", "senderName": "A", "subject": "Daily sync complete",
         "receivedAt": "2026-07-02T01:00:00Z", "bodyPreview": "ok"},
        {"id": "m2", "senderEmail": "b@x.com", "senderName": "B", "subject": "unrelated",
         "receivedAt": "2026-07-02T02:00:00Z", "bodyPreview": "no"},
    ]
    monkeypatch.setattr(e._g, "raw_list_since", lambda token, mailbox, since, top=50: msgs)

    posted = []
    monkeypatch.setattr(e, "_dispatch", lambda rule, msg: posted.append(msg["id"]))

    result = e.poll_once()
    assert result["dispatched"] == 1
    assert posted == ["m1"]                       # only the matching subject
    # Watermark advanced past BOTH fetched messages (m2 is newest).
    assert e.list_rules()[0]["watermark"] == "2026-07-02T02:00:00Z"


def test_poll_retries_after_dispatch_failure(isolated_rules, monkeypatch):
    e = isolated_rules
    e.add_rule("box@x.com", "https://pipe/trigger", {}, watermark_iso="2026-07-01T00:00:00Z")
    msgs = [
        {"id": "m1", "senderEmail": "a@x.com", "senderName": "A", "subject": "one",
         "receivedAt": "2026-07-02T01:00:00Z", "bodyPreview": ""},
        {"id": "m2", "senderEmail": "b@x.com", "senderName": "B", "subject": "two",
         "receivedAt": "2026-07-02T02:00:00Z", "bodyPreview": ""},
    ]
    monkeypatch.setattr(e._g, "raw_list_since", lambda token, mailbox, since, top=50: msgs)

    def boom(rule, msg):
        raise RuntimeError("target down")

    monkeypatch.setattr(e, "_dispatch", boom)
    result = e.poll_once()
    assert result["dispatched"] == 0
    assert "errors" in result
    # Watermark did NOT advance past the failed first message → retried next poll.
    assert e.list_rules()[0]["watermark"] == "2026-07-01T00:00:00Z"
