from __future__ import annotations

from flask import Flask

from email_batch import service as rc
from email_batch.routes import _parse_reply_to
from email_batch.routes import bp


def _build_batch(sender_email: str | None = "sender@allworthfinancial.com") -> rc.EmailBatch:
    group = rc.EmailGroup(
        id=1,
        advisors=["Advisor One"],
        email="advisor.one@allworthfinancial.com",
        cc=[sender_email] if sender_email else [],
        row_count=1,
        subject="Advisor Mail",
        html="<p>Hello</p>",
    )
    return rc.EmailBatch(
        id="batch123",
        subject="Advisor Mail",
        advisor_column="Primary Advisor",
        total_rows=1,
        groups=[group],
        missing_advisors=[],
        sender_email=sender_email,
    )


def test_parse_reply_to_accepts_semicolon_and_dedupes():
    parsed = _parse_reply_to(
        " first@allworthfinancial.com ; second@allworthfinancial.com;first@allworthfinancial.com\nthird@allworthfinancial.com "
    )
    assert parsed == [
        "first@allworthfinancial.com",
        "second@allworthfinancial.com",
        "third@allworthfinancial.com",
    ]


def test_send_accepts_semicolon_separated_reply_to(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(bp)
    client = app.test_client()

    batch = _build_batch()
    monkeypatch.setattr("email_batch.routes.rc.store.get", lambda _batch_id: batch)
    monkeypatch.setattr(
        "email_batch.routes.auth_middleware.easy_auth_user",
        lambda _req: {"email": "signedin@allworthfinancial.com"},
    )

    captured: dict[str, object] = {}

    def fake_send_email(to, subject, body, **kw):
        captured["to"] = to
        captured["subject"] = subject
        captured["reply_to"] = kw.get("reply_to")
        captured["cc"] = kw.get("cc")

    monkeypatch.setattr("email_batch.routes.mailer.send_email", fake_send_email)

    rv = client.post(
        "/api/email-batch/send",
        json={
            "batch_id": batch.id,
            "group_ids": [1],
            "reply_to": "one@allworthfinancial.com; two@allworthfinancial.com ;three@allworthfinancial.com",
        },
        headers={"X-MS-TOKEN-AAD-ACCESS-TOKEN": "fake-token"},
    )

    assert rv.status_code == 200
    assert captured["to"] == "advisor.one@allworthfinancial.com"
    assert captured["subject"] == "Advisor Mail"
    assert captured["reply_to"] == [
        "one@allworthfinancial.com",
        "two@allworthfinancial.com",
        "three@allworthfinancial.com",
    ]
    assert captured["cc"] == [
        "one@allworthfinancial.com",
        "two@allworthfinancial.com",
        "three@allworthfinancial.com",
    ]


def test_send_falls_back_to_sender_email_as_reply_to(monkeypatch):
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(bp)
    client = app.test_client()

    batch = _build_batch(sender_email="owner@allworthfinancial.com")
    monkeypatch.setattr("email_batch.routes.rc.store.get", lambda _batch_id: batch)
    monkeypatch.setattr(
        "email_batch.routes.auth_middleware.easy_auth_user",
        lambda _req: {"email": "signedin@allworthfinancial.com"},
    )

    captured: dict[str, object] = {}

    def fake_send_email(to, subject, body, **kw):
        captured["reply_to"] = kw.get("reply_to")

    monkeypatch.setattr("email_batch.routes.mailer.send_email", fake_send_email)

    rv = client.post(
        "/api/email-batch/send",
        json={
            "batch_id": batch.id,
            "group_ids": [1],
        },
        headers={"X-MS-TOKEN-AAD-ACCESS-TOKEN": "fake-token"},
    )

    assert rv.status_code == 200
    assert captured["reply_to"] == ["owner@allworthfinancial.com"]
