"""Jira REST API v3 client — read tickets + write comment/transition.

Basic auth against Atlassian Cloud. The v2 ``/search`` endpoint returns 410
Gone, so queries use ``/rest/api/3/search/jql``.

Credentials resolution order:
  1. ``JIRA_EMAIL`` / ``JIRA_API_TOKEN`` env vars (local dev override)
  2. Azure Key Vault ``allworthsynapse`` — secrets ``jiraemail`` / ``jiraapitoken``
     (same vault SFP2 uses; App Service managed identity already has access)

The backend is headless, so the claude.ai Atlassian MCP connector is NOT
available here — Basic auth only.
"""

from __future__ import annotations

import base64
import logging
import os
from threading import Lock
from typing import Any

import requests

logger = logging.getLogger(__name__)

_JIRA_URL = os.getenv("JIRA_URL", "https://allworthfinancial.atlassian.net").rstrip("/")
_TIMEOUT = 20

# Key Vault fallback config (mirrors sfp2/salesforce_client.py).
_KV_NAME = os.getenv("JIRA_KEY_VAULT_NAME", "allworthsynapse")
_KV_URL = f"https://{_KV_NAME}.vault.azure.net/"
_KV_SECRET_EMAIL = os.getenv("JIRA_KV_SECRET_EMAIL", "jiraemail")
_KV_SECRET_TOKEN = os.getenv("JIRA_KV_SECRET_TOKEN", "jiraapitoken")

_creds_cache: dict[str, str] = {}
_creds_lock = Lock()
_kv_last_error: str | None = None  # most recent KV failure reason for diag


def _load_from_keyvault() -> tuple[str, str] | None:
    """Pull (email, token) from Key Vault. Returns None if SDK or auth fails."""
    global _kv_last_error
    try:
        from azure.identity import (  # type: ignore
            ChainedTokenCredential,
            ClientSecretCredential,
            DefaultAzureCredential,
            ManagedIdentityCredential,
        )
        from azure.keyvault.secrets import SecretClient  # type: ignore
    except Exception as exc:
        _kv_last_error = f"azure SDK import failed: {type(exc).__name__}: {exc}"
        logger.info("Jira KV fallback unavailable (%s)", _kv_last_error)
        return None

    creds: list[Any] = []
    msi_client_id = os.getenv("AZURE_MSI_CLIENT_ID")
    if msi_client_id:
        creds.append(ManagedIdentityCredential(client_id=msi_client_id))
    else:
        creds.append(ManagedIdentityCredential())
    cid, csec, tid = (
        os.getenv("AZURE_CLIENT_ID"),
        os.getenv("AZURE_CLIENT_SECRET"),
        os.getenv("AZURE_TENANT_ID"),
    )
    if cid and csec and tid:
        creds.append(ClientSecretCredential(tid, cid, csec))
    creds.append(DefaultAzureCredential(
        exclude_environment_credential=True,
        exclude_managed_identity_credential=True,
    ))

    try:
        client = SecretClient(vault_url=_KV_URL, credential=ChainedTokenCredential(*creds))
        email = client.get_secret(_KV_SECRET_EMAIL).value or ""
        token = client.get_secret(_KV_SECRET_TOKEN).value or ""
    except Exception as exc:
        _kv_last_error = f"{type(exc).__name__}: {exc}"
        logger.warning("Jira Key Vault lookup failed: %s", _kv_last_error)
        return None
    if not email or not token:
        _kv_last_error = (
            f"secrets returned empty (email_len={len(email)}, "
            f"token_len={len(token)}; check secret names "
            f"'{_KV_SECRET_EMAIL}' / '{_KV_SECRET_TOKEN}' in vault {_KV_NAME})"
        )
        logger.warning("Jira KV: %s", _kv_last_error)
        return None
    _kv_last_error = None
    return email, token


def _credentials() -> tuple[str, str]:
    """Resolve (email, token), preferring env vars, falling back to Key Vault."""
    with _creds_lock:
        if _creds_cache:
            return _creds_cache["email"], _creds_cache["token"]

        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        if not (email and token):
            kv = _load_from_keyvault()
            if kv:
                email, token = kv
        if email and token:
            _creds_cache["email"] = email
            _creds_cache["token"] = token
        return email, token


class JiraError(RuntimeError):
    """Raised when a Jira write (comment/transition) fails."""


def configured() -> bool:
    email, token = _credentials()
    return bool(email and token)


def diagnostics() -> dict:
    """Surface credential source for /health — useful when the queue is empty."""
    has_env = bool(os.getenv("JIRA_EMAIL") and os.getenv("JIRA_API_TOKEN"))
    source = "env" if has_env else None
    if not has_env:
        kv = _load_from_keyvault()
        source = "keyvault" if kv else ("kv_error" if _kv_last_error else "missing")
    return {
        "configured": configured(),
        "source": source,
        "url": _JIRA_URL,
        "key_vault": _KV_NAME,
        "kv_secret_email": _KV_SECRET_EMAIL,
        "kv_secret_token": _KV_SECRET_TOKEN,
        "kv_error": _kv_last_error,
    }


def _headers() -> dict[str, str]:
    email, token = _credentials()
    cred = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {cred}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _adf_to_text(node: Any) -> str:
    """Recursively extract plain text from Atlassian Document Format."""
    if node is None:
        return ""
    if isinstance(node, list):
        return "".join(_adf_to_text(n) for n in node)
    if isinstance(node, dict):
        if node.get("type") == "text":
            return node.get("text", "")
        if node.get("type") == "hardBreak":
            return "\n"
        return _adf_to_text(node.get("content", []))
    return str(node)


def _text_to_adf(text: str) -> dict:
    """Minimal plain-text → ADF doc (one paragraph per line). Invalid ADF = 400."""
    lines = (text or "").split("\n")
    content = []
    for line in lines:
        para: dict[str, Any] = {"type": "paragraph", "content": []}
        if line:
            para["content"] = [{"type": "text", "text": line}]
        content.append(para)
    if not content:
        content = [{"type": "paragraph", "content": []}]
    return {"type": "doc", "version": 1, "content": content}


# ── reads ─────────────────────────────────────────────────────────────────


# Open-status whitelist — projects use a wide variety of in-flight statuses.
_OPEN_STATUSES = [
    "Approval", "Backlog", "In Progress", "Escalated", "Delayed",
    "Initiatives", "Open", "Pending", "Pending Team Support", "Projects",
    "Reopened", "Selected for Development", "Waiting for customer",
    "Waiting for support", "Work in progress",
]


def search_nfbc_tickets(status_filter: str = "open") -> list[dict]:
    """Search NFBC tickets. status_filter: 'open' | 'closed' | 'all'."""
    if not configured():
        return []

    jql_parts = [
        'project IN (AR, AI)',
        'labels = NFBC_Adjustment',
        'type != Epic',
    ]
    if status_filter == "open":
        quoted = ", ".join(f'"{s}"' for s in _OPEN_STATUSES)
        jql_parts.append(f"status IN ({quoted})")
    elif status_filter == "closed":
        jql_parts.append('statusCategory = Done')
    jql = " AND ".join(jql_parts) + " ORDER BY created DESC"

    try:
        resp = requests.get(
            f"{_JIRA_URL}/rest/api/3/search/jql",
            headers=_headers(),
            params={
                "jql": jql,
                "maxResults": 50,
                "fields": "summary,status,assignee,reporter,created,priority,labels",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("Jira search failed: %s", exc)
        raise JiraError(f"Jira search failed: {exc}") from exc

    tickets = []
    for issue in data.get("issues", []):
        f = issue.get("fields", {})
        tickets.append({
            "key": issue["key"],
            "summary": f.get("summary", ""),
            "status": (f.get("status") or {}).get("name", ""),
            "assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
            "reporter": (f.get("reporter") or {}).get("displayName", ""),
            "created": (f.get("created", "") or "")[:10],
            "priority": (f.get("priority") or {}).get("name", ""),
        })
    return tickets


def get_ticket_detail(key: str) -> dict | None:
    """Full detail for a single issue, with ADF rendered to text."""
    if not configured():
        return None
    try:
        resp = requests.get(
            f"{_JIRA_URL}/rest/api/3/issue/{key}",
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        issue = resp.json()
    except Exception as exc:
        logger.error("Jira issue fetch failed: %s", exc)
        return None

    f = issue.get("fields", {})
    return {
        "key": issue["key"],
        "summary": f.get("summary", ""),
        "status": (f.get("status") or {}).get("name", ""),
        "assignee": (f.get("assignee") or {}).get("displayName", "Unassigned"),
        "reporter": (f.get("reporter") or {}).get("displayName", ""),
        "created": (f.get("created", "") or "")[:10],
        "updated": (f.get("updated", "") or "")[:10],
        "priority": (f.get("priority") or {}).get("name", ""),
        "description": _adf_to_text(f.get("description")),
        "labels": f.get("labels", []),
        "comments": [
            {
                "author": (c.get("author") or {}).get("displayName", ""),
                "body": _adf_to_text(c.get("body")),
                "created": (c.get("created", "") or "")[:10],
            }
            for c in (f.get("comment", {}) or {}).get("comments", [])
        ],
    }


# ── writes ──────────────────────────────────────────────────────────────────


def add_comment(key: str, text: str) -> dict:
    """Post a comment. Raises JiraError on failure."""
    if not configured():
        raise JiraError(
            "Jira not configured: set JIRA_EMAIL/JIRA_API_TOKEN env vars or "
            "ensure App Service managed identity has Key Vault Secrets User "
            "on allworthsynapse vault."
        )
    try:
        resp = requests.post(
            f"{_JIRA_URL}/rest/api/3/issue/{key}/comment",
            headers=_headers(),
            json={"body": _text_to_adf(text)},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        body = resp.json()
        return {"ok": True, "id": body.get("id")}
    except Exception as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        logger.error("Jira add_comment failed for %s: %s %s", key, exc, detail)
        raise JiraError(f"add_comment failed: {exc}") from exc


def get_transitions(key: str) -> list[dict]:
    """Available transitions: [{id, name, to_status}]."""
    if not configured():
        raise JiraError("Jira not configured")
    try:
        resp = requests.get(
            f"{_JIRA_URL}/rest/api/3/issue/{key}/transitions",
            headers=_headers(),
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.error("Jira get_transitions failed for %s: %s", key, exc)
        raise JiraError(f"get_transitions failed: {exc}") from exc
    return [
        {
            "id": t.get("id"),
            "name": t.get("name", ""),
            "to_status": (t.get("to") or {}).get("name", ""),
        }
        for t in data.get("transitions", [])
    ]


def transition_issue(key: str, transition_id: str | None = None,
                     target_status: str = "Done") -> dict:
    """Transition an issue. If no id given, resolve one whose target status or
    name matches `target_status` (case-insensitive). Raises JiraError on failure."""
    if not configured():
        raise JiraError("Jira not configured")

    if transition_id is None:
        transitions = get_transitions(key)
        target = target_status.strip().lower()
        match = next(
            (t for t in transitions
             if t["to_status"].strip().lower() == target or t["name"].strip().lower() == target),
            None,
        )
        if not match:
            available = ", ".join(f"{t['name']}→{t['to_status']}" for t in transitions) or "none"
            raise JiraError(
                f"No transition to '{target_status}' for {key}. Available: {available}"
            )
        transition_id = match["id"]

    try:
        resp = requests.post(
            f"{_JIRA_URL}/rest/api/3/issue/{key}/transitions",
            headers=_headers(),
            json={"transition": {"id": transition_id}},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        return {"ok": True, "to": target_status, "transition_id": transition_id}
    except Exception as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        logger.error("Jira transition failed for %s: %s %s", key, exc, detail)
        raise JiraError(f"transition failed: {exc}") from exc
