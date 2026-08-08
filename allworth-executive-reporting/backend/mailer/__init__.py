"""mailer — reusable Microsoft Graph email for any tool, job, or pipeline.

Simple functions, dual identity. Pass ``token`` (an Easy Auth user token) to act
AS the signed-in user; omit it to act app-only (headless automation) against a
service ``mailbox``.

    from mailer import send_email, reply_to, read_inbox

    # headless pipeline (app-only) — sends from a service mailbox:
    send_email(to="cfo@allworthfinancial.com", subject="Nightly report",
               body="Attached figures are ready.", mailbox="automations@allworthfinancial.com")

    # inside an interactive tool (delegated) — sends as the signed-in user:
    send_email(to=[...], subject=..., body=..., token=user_token)

App-only requires APPLICATION Graph permissions (Mail.Send / Mail.Read)
admin-consented on the app registration, the AZURE_CLIENT_ID/SECRET/TENANT app
settings, and a target mailbox (defaults to the MAILER_FROM app setting).

Errors raise ``MailError`` (carrying an HTTP ``status``) so HTTP callers can map
it to a response and pipelines get a clear failure.
"""
from __future__ import annotations

import os
from typing import Any

from . import graph_client as _g
from .graph_client import MailError

__all__ = ["send_email", "reply_to", "read_inbox", "get_message", "get_thread", "MailError"]


def _as_list(v: str | list[str] | None) -> list[str]:
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def _default_mailbox(token: str | None, mailbox: str | None) -> str | None:
    # Delegated calls act on /me and ignore mailbox; app-only falls back to the
    # configured service mailbox when the caller doesn't name one.
    if token:
        return None
    return mailbox or os.getenv("MAILER_FROM") or None


def send_email(
    to: str | list[str],
    subject: str,
    body: str,
    *,
    cc: str | list[str] | None = None,
    html: bool = False,
    token: str | None = None,
    mailbox: str | None = None,
) -> None:
    """Send a new email. Delegated (token) or app-only (mailbox/MAILER_FROM)."""
    recipients = _as_list(to)
    if not recipients:
        raise MailError("send_email requires at least one recipient", 400)
    _g.raw_send(token, _default_mailbox(token, mailbox), subject, body, recipients, _as_list(cc), html)


def reply_to(
    message_id: str,
    body: str,
    *,
    token: str | None = None,
    mailbox: str | None = None,
) -> None:
    """Send a threaded reply to an existing message (needs Mail.Send)."""
    if not message_id or not body.strip():
        raise MailError("reply_to requires message_id and body", 400)
    _g.raw_reply(token, _default_mailbox(token, mailbox), message_id, body)


def read_inbox(
    *,
    token: str | None = None,
    mailbox: str | None = None,
    top: int = 25,
    only_unread: bool = False,
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent inbox messages (metadata + preview)."""
    return _g.raw_list(token, _default_mailbox(token, mailbox), top, only_unread, search)


def get_message(message_id: str, *, token: str | None = None, mailbox: str | None = None) -> dict[str, Any]:
    """Return one message with its full plain-text body."""
    return _g.raw_get(token, _default_mailbox(token, mailbox), message_id)


def get_thread(conversation_id: str, *, token: str | None = None, mailbox: str | None = None) -> list[dict[str, Any]]:
    """Return all messages in a conversation, oldest first."""
    return _g.raw_thread(token, _default_mailbox(token, mailbox), conversation_id)
