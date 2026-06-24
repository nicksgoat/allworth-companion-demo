"""Household authentication — scopes all API access to one household.

Supports two login modes:
1. **Email login** (production path): Looks up the client's email in
   Contact_Demographic to resolve their household (AVHHID). No password
   required for demo; in production this would validate via Entra ID/SSO.
2. **Demo login** (legacy): Uses hardcoded household_id + passcode pairs.

Each login returns a session token tied to a household_id (AVHHID).
All downstream routes use get_current_household() to enforce data isolation.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request

from allworth_api.config import (
    demo_auth_fallback_enabled,
    seed_auth_enabled,
    session_secret,
    session_ttl_seconds,
)

logger = logging.getLogger(__name__)


@dataclass
class HouseholdSession:
    """An authenticated session tied to a specific household."""
    household_id: str
    token: str
    email: str | None = None
    contact_name: str | None = None
    advisor_id: str | None = None
    created_at: float = field(default_factory=time.time)


# Demo credentials — maps household_id to a simple passcode
# Used as fallback when Synapse is unavailable or for local testing
_DEMO_CREDENTIALS: dict[str, str] = {
    "maya": "demo",
    "kenny": "demo",
    "hh_castillo": "demo",
    "hh_raman": "demo",
}


def _lookup_email_in_synapse(email: str) -> dict[str, Any] | None:
    """Look up a client by email in Synapse Contact_Demographic.

    Returns dict with household_id (AVHHID), contact_name, role, email
    or None if not found / Synapse unavailable.
    """
    from allworth_api.data.synapse import _query, is_available

    if not is_available():
        return None

    try:
        rows = _query(
            """
            SELECT TOP 1
                cd.[email],
                cd.[contact_name],
                cd.[primary_or_secondary] AS role,
                hf.[avhhid] AS household_id
            FROM [tho].[Contact_Demographic] cd
            INNER JOIN [tho].[hh_fact] hf ON cd.[hh_id] = hf.[HHID]
            WHERE LOWER(cd.[email]) = LOWER(?)
              AND hf.[avhhid] IS NOT NULL
            ORDER BY
                CASE cd.[primary_or_secondary] WHEN 'Primary' THEN 0 ELSE 1 END
            """,
            (email.strip(),),
        )
        return rows[0] if rows else None
    except Exception as e:
        logger.warning(f"Synapse email lookup failed: {e}")
        return None


def authenticate(household_id: str, passcode: str) -> HouseholdSession | None:
    """Validate credentials and create a session (demo mode).

    Returns a HouseholdSession on success, None on failure.
    """
    expected = _DEMO_CREDENTIALS.get(household_id)
    if expected is None or not secrets.compare_digest(passcode, expected):
        return None

    token = _generate_token(household_id)
    return HouseholdSession(household_id=household_id, token=token)


def _lookup_email_in_seed(email: str) -> dict[str, Any] | None:
    """Mock-mode email lookup: resolve a demo email against the seed personas.

    Mirrors _lookup_email_in_synapse so the same email login screen works in both
    mock and live mode — flipping DATA_MODE doesn't change how you sign in.
    """
    from allworth_api.data.seed import all_client_personas

    target = email.strip().lower()
    for c in all_client_personas():
        if (c.get("email") or "").lower() == target:
            return {
                "household_id": c["id"],
                "contact_name": c["name"],
                "email": c.get("email"),
                "role": "Primary",
            }
    return None


def authenticate_email(email: str) -> HouseholdSession | None:
    """Authenticate by client email address.

    Live mode resolves the email in Synapse Contact_Demographic (AVHHID); mock mode
    falls back to the seed personas. No password required for demo — the email is the
    identity proof (in production this would be SSO/Entra validated).

    Returns HouseholdSession on success, None if email not found.
    """
    result = _lookup_email_in_synapse(email)
    if not result and seed_auth_enabled():
        result = _lookup_email_in_seed(email)
    if not result:
        return None

    household_id = str(result["household_id"])
    session = HouseholdSession(
        household_id=household_id,
        token=_generate_token(
            household_id,
            email=email.strip().lower(),
            contact_name=result.get("contact_name"),
        ),
        email=email.strip().lower(),
        contact_name=result.get("contact_name"),
    )
    logger.info(f"Email login: {email} → household {household_id} ({result.get('contact_name')})")
    return session


def get_session(token: str) -> HouseholdSession | None:
    """Validate and decode a stateless session token."""
    payload = _verify_token(token)
    if not payload:
        return None
    return HouseholdSession(
        household_id=str(payload["household_id"]),
        token=token,
        email=payload.get("email"),
        contact_name=payload.get("contact_name"),
        advisor_id=payload.get("advisor_id"),
        created_at=float(payload.get("iat", 0)),
    )


def invalidate(token: str) -> bool:
    """Stateless tokens cannot be revoked locally; clients discard them on logout."""
    return bool(get_session(token))


def get_session_for_household(household_id: str) -> HouseholdSession | None:
    """No process-local session index exists in stateless mode."""
    return None


def _b64url(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64url(data: str) -> bytes:
    return urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    digest = hmac.new(session_secret().encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
    return _b64url(digest)


def _generate_token(
    household_id: str,
    *,
    email: str | None = None,
    contact_name: str | None = None,
    advisor_id: str | None = None,
) -> str:
    """Generate a signed, stateless bearer token."""
    now = int(time.time())
    payload = {
        "household_id": household_id,
        "email": email,
        "contact_name": contact_name,
        "advisor_id": advisor_id,
        "iat": now,
        "exp": now + session_ttl_seconds(),
        "nonce": secrets.token_urlsafe(16),
    }
    payload_part = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{payload_part}.{_sign(payload_part)}"


def _verify_token(token: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    payload_part, signature = token.rsplit(".", 1)
    expected = _sign(payload_part)
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_unb64url(payload_part))
    except (json.JSONDecodeError, ValueError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if not payload.get("household_id"):
        return None
    return payload


# ── FastAPI dependency ───────────────────────────────────────────────────


async def get_current_household(request: Request) -> str:
    """FastAPI dependency that extracts and validates the household from the request.

    Checks Authorization header (Bearer token) or falls back to query param
    for demo convenience. Returns the household_id.
    """
    from allworth_api.data.seed import set_current_client

    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        session = get_session(token)
        if session:
            set_current_client(session.household_id)
            return session.household_id

    if demo_auth_fallback_enabled():
        # Fallback: X-Household-Id header (for demo/dev without full login)
        household_header = request.headers.get("X-Household-Id", "")
        if household_header:
            set_current_client(household_header)
            return household_header

        # Final fallback for backward compat during dev
        set_current_client("maya")
        return "maya"

    raise HTTPException(status_code=401, detail="Authentication required")
