"""Event-driven inbound: 'an email triggers the pipeline'.

Poll model (no public webhook, no auth changes): a scheduled, authenticated
caller hits POST /mailer/api/poll every few minutes. For each configured RULE we
read inbox mail received since the rule's watermark (app-only), keep the ones
matching the rule, and POST each to the rule's ``target_url`` (the pipeline's
trigger). Watermark advances only past successfully-dispatched messages, so a
failed dispatch is retried next poll (at-least-once, in order).

Rules are stored as JSON next to this module, mirroring the atomic-write pattern
used elsewhere in the app.

    rule = {
      "id": "...", "mailbox": "automations@allworthfinancial.com",
      "match": {"from_contains": "envestnet.com", "subject_contains": "sync complete"},
      "target_url": "https://<pipeline-trigger>", "watermark": "<iso>", "active": true
    }
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import requests

from . import graph_client as _g

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / ".mailer-state"
_STORE = _DIR / "rules.json"
_lock = Lock()
_DISPATCH_TIMEOUT = 15


def now_iso() -> str:
    """Current UTC time as Graph-compatible ISO 8601. A new rule watermarks
    from now so existing history isn't replayed on first poll."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> list[dict[str, Any]]:
    try:
        with _lock:
            return json.loads(_STORE.read_text("utf-8")) if _STORE.exists() else []
    except Exception:  # pragma: no cover - corrupt store starts empty
        return []


def _save(rules: list[dict[str, Any]]) -> None:
    with _lock:
        _DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(rules, fh, indent=2)
            os.replace(tmp, _STORE)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


def list_rules() -> list[dict[str, Any]]:
    return _load()


def add_rule(mailbox: str, target_url: str, match: dict[str, str] | None,
             watermark_iso: str | None = None) -> dict[str, Any]:
    if not mailbox or not target_url:
        raise ValueError("mailbox and target_url are required")
    rule = {
        "id": uuid.uuid4().hex[:12],
        "mailbox": mailbox,
        "match": match or {},
        "target_url": target_url,
        "watermark": watermark_iso or now_iso(),
        "active": True,
    }
    rules = _load()
    rules.append(rule)
    _save(rules)
    return rule


def delete_rule(rule_id: str) -> bool:
    rules = _load()
    kept = [r for r in rules if r.get("id") != rule_id]
    if len(kept) == len(rules):
        return False
    _save(kept)
    return True


def _matches(match: dict[str, str], msg: dict[str, Any]) -> bool:
    fc = (match.get("from_contains") or "").lower()
    sc = (match.get("subject_contains") or "").lower()
    if fc and fc not in (msg.get("senderEmail", "").lower() + " " + msg.get("senderName", "").lower()):
        return False
    if sc and sc not in msg.get("subject", "").lower():
        return False
    return True


def _dispatch(rule: dict[str, Any], msg: dict[str, Any]) -> None:
    """POST the matched email to the rule's target. Signs with an HMAC of the
    body using MAILER_EVENT_SECRET (if set) so the receiver can verify origin."""
    payload = {
        "rule_id": rule["id"],
        "mailbox": rule["mailbox"],
        "message": {
            "id": msg.get("id"),
            "from": msg.get("senderEmail"),
            "fromName": msg.get("senderName"),
            "subject": msg.get("subject"),
            "receivedAt": msg.get("receivedAt"),
            "preview": msg.get("bodyPreview"),
        },
    }
    raw = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    secret = os.getenv("MAILER_EVENT_SECRET")
    if secret:
        headers["X-Mailer-Signature"] = "sha256=" + hmac.new(
            secret.encode(), raw, hashlib.sha256
        ).hexdigest()
    resp = requests.post(rule["target_url"], data=raw, headers=headers, timeout=_DISPATCH_TIMEOUT)
    if resp.status_code >= 400:
        raise RuntimeError(f"target returned {resp.status_code}: {resp.text[:200]}")


def poll_once() -> dict[str, Any]:
    """Run one polling pass across all active rules. Returns a summary."""
    rules = _load()
    dispatched = 0
    errors: list[str] = []
    changed = False
    for rule in rules:
        if not rule.get("active", True):
            continue
        try:
            new_msgs = _g.raw_list_since(None, rule["mailbox"], rule.get("watermark") or now_iso())
        except Exception as exc:
            errors.append(f"{rule['id']}: list failed: {exc}")
            continue
        # Process oldest→newest; advance watermark only past successes so a
        # failed dispatch is retried on the next poll.
        for msg in new_msgs:
            if _matches(rule.get("match", {}), msg):
                try:
                    _dispatch(rule, msg)
                    dispatched += 1
                except Exception as exc:
                    errors.append(f"{rule['id']}: dispatch failed for {msg.get('id')}: {exc}")
                    break  # stop advancing; retry from here next poll
            rule["watermark"] = msg.get("receivedAt") or rule.get("watermark")
            changed = True
    if changed:
        _save(rules)
    result = {"success": True, "dispatched": dispatched, "rules": len(rules)}
    if errors:
        result["errors"] = errors
    return result
