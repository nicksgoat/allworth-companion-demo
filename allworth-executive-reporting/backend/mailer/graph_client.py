"""Low-level Microsoft Graph mail calls, dual-auth.

One code path serves two identities:

* Delegated  — pass ``token`` (the Easy Auth user token). Acts AS the signed-in
  user against ``/me``. This is what the interactive Executive Brief uses.
* App-only   — omit ``token``. Acquires an application token via client
  credentials (AZURE_CLIENT_ID/SECRET/TENANT) and acts against
  ``/users/{mailbox}``. This is what headless pipelines/automation use; it
  requires APPLICATION Graph permissions (Mail.Send / Mail.Read) admin-consented
  on the app registration and, for send/read, a target ``mailbox``.

Callers should use the friendly wrappers in ``mailer/__init__.py`` rather than
this module directly.
"""
from __future__ import annotations

import html
import os
import re
import time
from typing import Any

import requests

_GRAPH = "https://graph.microsoft.com/v1.0"
_TIMEOUT = 20

# Cache the app-only token until shortly before expiry.
_app_tok: dict[str, Any] = {"value": None, "exp": 0.0}


class MailError(RuntimeError):
    """A Graph mail call failed. Carries the HTTP status for the caller."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _app_token() -> str:
    """Application (client-credentials) Graph token, cached until ~expiry."""
    now = time.time()
    if _app_tok["value"] and now < _app_tok["exp"] - 120:
        return _app_tok["value"]
    tenant = os.getenv("AZURE_TENANT_ID") or os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID") or os.getenv("ENTRA_CLIENT_ID")
    secret = os.getenv("AZURE_CLIENT_SECRET")
    if not (tenant and client_id and secret):
        raise MailError(
            "App-only mail requires AZURE_TENANT_ID/CLIENT_ID/CLIENT_SECRET", 500
        )
    try:
        from azure.identity import ClientSecretCredential

        cred = ClientSecretCredential(tenant, client_id, secret)
        tok = cred.get_token("https://graph.microsoft.com/.default")
    except Exception as exc:  # pragma: no cover - env/credential errors
        raise MailError(f"app-only token acquisition failed: {exc}", 500) from exc
    _app_tok["value"] = tok.token
    _app_tok["exp"] = tok.expires_on
    return tok.token


def _headers(token: str | None) -> dict[str, str]:
    bearer = token or _app_token()
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json",
        "Prefer": 'outlook.body-content-type="text"',
    }


def _root(token: str | None, mailbox: str | None) -> str:
    """`/me` for delegated; `/users/{mailbox}` for app-only."""
    if token:
        return "/me"
    if not mailbox:
        raise MailError("app-only mail requires a 'mailbox' (e.g. automations@allworthfinancial.com)", 400)
    return f"/users/{mailbox}"


def _request(method: str, path: str, token: str | None, **kw) -> requests.Response:
    try:
        resp = requests.request(
            method, f"{_GRAPH}{path}", headers=_headers(token), timeout=_TIMEOUT, **kw
        )
    except requests.RequestException as exc:
        raise MailError(f"Graph request failed: {exc}") from exc
    if resp.status_code == 401:
        raise MailError("Graph token rejected (401)", 401)
    if resp.status_code == 403:
        raise MailError("Graph denied (403) — required scope/permission not granted", 403)
    if resp.status_code >= 400:
        raise MailError(f"Graph error {resp.status_code}: {resp.text[:300]}", 502)
    return resp


def plain(text: str | None) -> str:
    """Best-effort plain text from a (possibly HTML) body."""
    if not text:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", " ", text)).strip()


def addr(recipient: dict[str, Any] | None) -> dict[str, str]:
    e = (recipient or {}).get("emailAddress", {}) or {}
    return {"name": e.get("name") or e.get("address") or "", "email": e.get("address") or ""}


def _recipients(values: list[str] | None) -> list[dict[str, Any]]:
    return [{"emailAddress": {"address": v}} for v in (values or []) if v]


# --------------------------------------------------------------------------- #
# Raw operations (used by the friendly wrappers)
# --------------------------------------------------------------------------- #
def raw_send(token: str | None, mailbox: str | None, subject: str, body: str,
             to: list[str], cc: list[str] | None, html_body: bool,
             reply_to: list[str] | None = None) -> None:
    message: dict[str, Any] = {
        "subject": subject,
        "body": {"contentType": "html" if html_body else "text", "content": body},
        "toRecipients": _recipients(to),
        "ccRecipients": _recipients(cc),
    }
    reply_recipients = _recipients(reply_to)
    if reply_recipients:
        message["replyTo"] = reply_recipients
    payload = {"message": message, "saveToSentItems": True}
    _request("POST", f"{_root(token, mailbox)}/sendMail", token, json=payload)


def raw_reply(token: str | None, mailbox: str | None, message_id: str, comment: str) -> None:
    _request(
        "POST", f"{_root(token, mailbox)}/messages/{message_id}/reply", token,
        json={"comment": comment},
    )


def raw_list(token: str | None, mailbox: str | None, top: int,
             only_unread: bool, search: str | None) -> list[dict[str, Any]]:
    params: dict[str, str] = {
        "$top": str(top),
        "$select": "id,conversationId,subject,from,receivedDateTime,bodyPreview,hasAttachments,isRead,importance",
        "$orderby": "receivedDateTime desc",
    }
    if only_unread:
        params["$filter"] = "isRead eq false"
    if search:
        # $search can't combine with $orderby; drop ordering when searching.
        params.pop("$orderby", None)
        params["$search"] = f'"{search}"'
    data = _request("GET", f"{_root(token, mailbox)}/mailFolders/inbox/messages", token, params=params).json()
    out = []
    for m in data.get("value", []):
        f = addr(m.get("from"))
        out.append({
            "id": m.get("id"),
            "threadId": m.get("conversationId") or m.get("id"),
            "senderName": f["name"],
            "senderEmail": f["email"],
            "subject": m.get("subject") or "(no subject)",
            "receivedAt": m.get("receivedDateTime"),
            "bodyPreview": m.get("bodyPreview") or "",
            "attachmentCount": 1 if m.get("hasAttachments") else 0,
            "unread": not m.get("isRead", True),
            "importance": m.get("importance") or "normal",
        })
    return out


def raw_list_since(token: str | None, mailbox: str | None, since_iso: str,
                   top: int = 50) -> list[dict[str, Any]]:
    """Inbox messages received strictly after ``since_iso`` (ISO 8601 UTC),
    oldest first — the primitive the event poller uses to find new mail."""
    params = {
        "$filter": f"receivedDateTime gt {since_iso}",
        "$orderby": "receivedDateTime asc",
        "$top": str(top),
        "$select": "id,conversationId,subject,from,receivedDateTime,bodyPreview,hasAttachments,isRead",
    }
    data = _request("GET", f"{_root(token, mailbox)}/mailFolders/inbox/messages", token, params=params).json()
    out = []
    for m in data.get("value", []):
        f = addr(m.get("from"))
        out.append({
            "id": m.get("id"),
            "threadId": m.get("conversationId") or m.get("id"),
            "senderName": f["name"],
            "senderEmail": f["email"],
            "subject": m.get("subject") or "(no subject)",
            "receivedAt": m.get("receivedDateTime"),
            "bodyPreview": m.get("bodyPreview") or "",
            "attachmentCount": 1 if m.get("hasAttachments") else 0,
            "unread": not m.get("isRead", True),
        })
    return out


def raw_get(token: str | None, mailbox: str | None, message_id: str) -> dict[str, Any]:
    sel = "id,conversationId,subject,from,toRecipients,ccRecipients,receivedDateTime,body,bodyPreview,hasAttachments,isRead"
    m = _request("GET", f"{_root(token, mailbox)}/messages/{message_id}", token, params={"$select": sel}).json()
    f = addr(m.get("from"))
    return {
        "id": m.get("id"),
        "threadId": m.get("conversationId") or m.get("id"),
        "senderName": f["name"],
        "senderEmail": f["email"],
        "subject": m.get("subject") or "(no subject)",
        "receivedAt": m.get("receivedDateTime"),
        "body": plain((m.get("body") or {}).get("content")),
        "to": [addr(r) for r in m.get("toRecipients", [])],
        "cc": [addr(r) for r in m.get("ccRecipients", [])],
        "attachmentCount": 1 if m.get("hasAttachments") else 0,
        "unread": not m.get("isRead", True),
    }


def raw_thread(token: str | None, mailbox: str | None, conversation_id: str) -> list[dict[str, Any]]:
    cid = (conversation_id or "").replace("'", "''")
    sel = "id,conversationId,subject,from,receivedDateTime,body"
    data = _request(
        "GET", f"{_root(token, mailbox)}/messages", token,
        params={"$filter": f"conversationId eq '{cid}'", "$select": sel, "$top": "50"},
    ).json()
    msgs = []
    for m in data.get("value", []):
        f = addr(m.get("from"))
        msgs.append({
            "id": m.get("id"),
            "from": f["name"],
            "fromEmail": f["email"],
            "sentAt": m.get("receivedDateTime"),
            "body": plain((m.get("body") or {}).get("content")),
        })
    msgs.sort(key=lambda x: x.get("sentAt") or "")
    return msgs
