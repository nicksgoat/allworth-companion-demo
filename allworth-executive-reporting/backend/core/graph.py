"""Shared Microsoft Graph HTTP layer.

Both Graph clients in this backend — ``mailer/graph_client.py`` (dual-auth
send/reply/read) and ``brief/graph.py`` (delegated, read-only) — were each
re-implementing the same request wrapper, status-code→exception mapping, header
construction and body-to-text helpers. That low-level layer lives here now.

Each caller keeps its own exception type (``MailError`` / ``GraphError``) by
passing it as ``error_cls``; the type only needs a ``(message, status)``
constructor. Auth differences (app-token fallback vs delegated bearer) stay in
the callers — this module never acquires tokens.
"""

from __future__ import annotations

import html
import re
from typing import Any

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_TIMEOUT = 20


class GraphError(RuntimeError):
    """A Graph call failed. Carries the HTTP ``status`` for the route layer."""

    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def headers(bearer: str) -> dict[str, str]:
    """Standard Graph headers. Bodies are requested as plain text so HTML never
    reaches downstream analysis."""
    return {
        "Authorization": f"Bearer {bearer}",
        "Accept": "application/json",
        "Prefer": 'outlook.body-content-type="text"',
    }


def call(
    method: str,
    path: str,
    *,
    headers: dict[str, str],
    error_cls: type = GraphError,
    timeout: int = DEFAULT_TIMEOUT,
    base: str = GRAPH_BASE,
    **kw: Any,
) -> requests.Response:
    """Perform a Graph request and map failures onto ``error_cls``.

    ``path`` is appended to ``base`` unless it is already an absolute URL. Maps
    401/403 to their own messages and any other >=400 to a generic error, each
    raised as ``error_cls(message, status)``.
    """
    url = path if path.startswith("http") else f"{base}{path}"
    try:
        resp = requests.request(method, url, headers=headers, timeout=timeout, **kw)
    except requests.RequestException as exc:
        raise error_cls(f"Graph request failed: {exc}") from exc
    if resp.status_code == 401:
        raise error_cls("Graph token rejected (401)", 401)
    if resp.status_code == 403:
        raise error_cls("Graph denied (403) — required scope/permission not granted", 403)
    if resp.status_code >= 400:
        raise error_cls(f"Graph error {resp.status_code}: {resp.text[:300]}", 502)
    return resp


def get_json(
    path: str,
    *,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
    error_cls: type = GraphError,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """GET ``path`` and return the parsed JSON body."""
    return call(
        "GET", path, headers=headers, params=params, error_cls=error_cls, timeout=timeout
    ).json()


def plain(text: str | None) -> str:
    """Best-effort plain text from a possibly-HTML body. Bodies are already
    requested as text; this strips any residual tags/entities defensively."""
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    collapsed = re.sub(r"[ \t]+\n", "\n", no_tags)
    return html.unescape(collapsed).strip()


def addr(recipient: dict[str, Any] | None) -> dict[str, str]:
    """Flatten a Graph recipient into ``{"name", "email"}``."""
    e = (recipient or {}).get("emailAddress", {}) or {}
    return {"name": e.get("name") or e.get("address") or "", "email": e.get("address") or ""}
