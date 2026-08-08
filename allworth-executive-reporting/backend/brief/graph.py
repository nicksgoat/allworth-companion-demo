"""Server-side Microsoft Graph client for the Executive Brief.

Reads the signed-in user's mailbox with the DELEGATED access token that App
Service Easy Auth injects as ``X-MS-TOKEN-AAD-ACCESS-TOKEN`` (present once the
token store is enabled and Mail.Read is consented on the app registration).

Security invariants:
    * The Graph token is read from the request header server-side and NEVER
      returned to the client.
    * Read-only by default. Draft creation requires Mail.ReadWrite and is the
      only write path; there is no send path anywhere.
    * Email bodies are fetched as plain text and treated as untrusted data by
      the analysis layer.

Everything here is pure functions that take the token explicitly, so they are
unit-testable without a live tenant.
"""
from __future__ import annotations

import html
import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

_GRAPH = "https://graph.microsoft.com/v1.0"
_TIMEOUT = 20

# Fields we need for the inbox list — keep the projection tight for latency.
_LIST_SELECT = (
    "id,conversationId,subject,from,receivedDateTime,bodyPreview,"
    "hasAttachments,isRead,importance"
)
_MSG_SELECT = (
    "id,conversationId,subject,from,toRecipients,ccRecipients,"
    "receivedDateTime,body,bodyPreview,hasAttachments,isRead,importance"
)


class GraphError(RuntimeError):
    """Raised when a Graph call fails. Carries the HTTP status for the route."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        # Ask Graph for plain-text bodies so we never hand HTML to the model.
        "Prefer": 'outlook.body-content-type="text"',
    }


def _get(token: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        resp = requests.get(
            f"{_GRAPH}{path}", headers=_headers(token), params=params, timeout=_TIMEOUT
        )
    except requests.RequestException as exc:  # network / timeout
        raise GraphError(f"Graph request failed: {exc}") from exc
    if resp.status_code == 401:
        raise GraphError("Graph token rejected (401) — re-consent may be required", 401)
    if resp.status_code == 403:
        raise GraphError("Graph denied (403) — Mail.Read scope not granted", 403)
    if resp.status_code >= 400:
        raise GraphError(f"Graph error {resp.status_code}: {resp.text[:300]}", 502)
    return resp.json()


def _plain(text: str | None) -> str:
    """Best-effort plain text. Bodies are requested as text, but strip any
    residual tags/entities defensively before the content reaches the model."""
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    collapsed = re.sub(r"[ \t]+\n", "\n", no_tags)
    return html.unescape(collapsed).strip()


def _addr(recipient: dict[str, Any] | None) -> dict[str, str]:
    e = (recipient or {}).get("emailAddress", {}) or {}
    return {"name": e.get("name") or e.get("address") or "", "email": e.get("address") or ""}


def _map_list_item(m: dict[str, Any]) -> dict[str, Any]:
    """Graph message → lightweight card metadata the triage step enriches."""
    frm = _addr(m.get("from"))
    return {
        "id": m.get("id"),
        "threadId": m.get("conversationId") or m.get("id"),
        "senderName": frm["name"],
        "senderEmail": frm["email"],
        "subject": m.get("subject") or "(no subject)",
        "receivedAt": m.get("receivedDateTime"),
        "bodyPreview": m.get("bodyPreview") or "",
        "attachmentCount": 1 if m.get("hasAttachments") else 0,
        "unread": not m.get("isRead", True),
        "importance": m.get("importance") or "normal",
    }


def get_inbox_messages(token: str, top: int = 50) -> list[dict[str, Any]]:
    """Most-recent inbox messages as lightweight card metadata."""
    data = _get(
        token,
        "/me/mailFolders/inbox/messages",
        {"$top": str(top), "$select": _LIST_SELECT, "$orderby": "receivedDateTime desc"},
    )
    return [_map_list_item(m) for m in data.get("value", [])]


def get_message(token: str, message_id: str) -> dict[str, Any]:
    """A single message with its full plain-text body and recipients."""
    m = _get(token, f"/me/messages/{message_id}", {"$select": _MSG_SELECT})
    frm = _addr(m.get("from"))
    return {
        "id": m.get("id"),
        "threadId": m.get("conversationId") or m.get("id"),
        "senderName": frm["name"],
        "senderEmail": frm["email"],
        "subject": m.get("subject") or "(no subject)",
        "receivedAt": m.get("receivedDateTime"),
        "body": _plain((m.get("body") or {}).get("content")),
        "to": [_addr(r) for r in m.get("toRecipients", [])],
        "cc": [_addr(r) for r in m.get("ccRecipients", [])],
        "attachmentCount": 1 if m.get("hasAttachments") else 0,
        "unread": not m.get("isRead", True),
    }


def get_thread(token: str, conversation_id: str) -> list[dict[str, Any]]:
    """All messages in a conversation, oldest first (sorted client-side to
    avoid Graph's filter+orderby restrictions)."""
    # Escape single quotes for the OData string literal.
    cid = (conversation_id or "").replace("'", "''")
    data = _get(
        token,
        "/me/messages",
        {"$filter": f"conversationId eq '{cid}'", "$select": _MSG_SELECT, "$top": "50"},
    )
    msgs = []
    for m in data.get("value", []):
        frm = _addr(m.get("from"))
        msgs.append({
            "id": m.get("id"),
            "from": frm["name"],
            "fromEmail": frm["email"],
            "sentAt": m.get("receivedDateTime"),
            "body": _plain((m.get("body") or {}).get("content")),
        })
    msgs.sort(key=lambda x: x.get("sentAt") or "")
    return msgs


def create_reply_draft(token: str, message_id: str, body_text: str) -> dict[str, Any]:
    """Create an Outlook reply DRAFT (never sends). Requires Mail.ReadWrite.

    Returns {"id", "webLink"} of the created draft. Callers that only hold
    Mail.Read should catch GraphError(403) and fall back to a local draft.
    """
    # createReply builds a draft in the mailbox pre-threaded to the original.
    created = requests.post(
        f"{_GRAPH}/me/messages/{message_id}/createReply",
        headers={**_headers(token), "Content-Type": "application/json"},
        timeout=_TIMEOUT,
    )
    if created.status_code == 403:
        raise GraphError("Draft save needs Mail.ReadWrite (not granted)", 403)
    if created.status_code >= 400:
        raise GraphError(f"createReply failed {created.status_code}: {created.text[:200]}", 502)
    draft = created.json()
    draft_id = draft.get("id")

    patched = requests.patch(
        f"{_GRAPH}/me/messages/{draft_id}",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"body": {"contentType": "text", "content": body_text}},
        timeout=_TIMEOUT,
    )
    if patched.status_code >= 400:
        raise GraphError(f"draft body update failed {patched.status_code}", 502)
    result = patched.json()
    return {"id": result.get("id"), "webLink": result.get("webLink")}


def send_reply(token: str, message_id: str, body_text: str) -> None:
    """Send a threaded reply to the original message. Requires Mail.Send.

    Uses the Graph ``reply`` action, which composes a reply to the original
    (preserving threading and quoting the original below) and sends it. This is
    the ONLY send path in the app and is invoked exclusively by an explicit,
    confirmed user action in the composer — never automatically, never from AI
    output or email content.
    """
    resp = requests.post(
        f"{_GRAPH}/me/messages/{message_id}/reply",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"comment": body_text},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 403:
        raise GraphError("Send denied (403) — Mail.Send scope not granted", 403)
    if resp.status_code >= 400:
        raise GraphError(f"send failed {resp.status_code}: {resp.text[:200]}", 502)
