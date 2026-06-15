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
import logging
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, Request

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


# In-memory session store (demo-scale; production would use Redis/DB)
_sessions: dict[str, HouseholdSession] = {}

# Demo credentials — maps household_id to a simple passcode
# Used as fallback when Synapse is unavailable or for local testing
_DEMO_CREDENTIALS: dict[str, str] = {
    "maya": "demo",
    "hh_castillo": "demo",
    "hh_raman": "demo",
}


def _lookup_email_in_synapse(email: str) -> dict[str, Any] | None:
    """Look up a client by email in Synapse Contact_Demographic.

    Returns dict with household_id (AVHHID), contact_name, role, email
    or None if not found / Synapse unavailable.
    """
    from allworth_api.data.synapse import is_available, _query

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
    session = HouseholdSession(household_id=household_id, token=token)
    _sessions[token] = session
    return session


def _lookup_email_in_seed(email: str) -> dict[str, Any] | None:
    """Mock-mode email lookup: resolve a demo email against the seed personas.

    Mirrors _lookup_email_in_synapse so the same email login screen works in both
    mock and live mode — flipping DATA_MODE doesn't change how you sign in.
    """
    from allworth_api.data.seed import seed

    target = email.strip().lower()
    for c in seed["personas"]["clients"]:
        if (c.get("email") or "").lower() == target:
            return {"household_id": c["id"], "contact_name": c["name"], "email": c.get("email"), "role": "Primary"}
    return None


def authenticate_email(email: str) -> HouseholdSession | None:
    """Authenticate by client email address.

    Live mode resolves the email in Synapse Contact_Demographic (AVHHID); mock mode
    falls back to the seed personas. No password required for demo — the email is the
    identity proof (in production this would be SSO/Entra validated).

    Returns HouseholdSession on success, None if email not found.
    """
    result = _lookup_email_in_synapse(email) or _lookup_email_in_seed(email)
    if not result:
        return None

    household_id = str(result["household_id"])
    token = _generate_token(household_id)
    session = HouseholdSession(
        household_id=household_id,
        token=token,
        email=email.strip().lower(),
        contact_name=result.get("contact_name"),
    )
    _sessions[token] = session
    logger.info(f"Email login: {email} → household {household_id} ({result.get('contact_name')})")
    return session


def get_session(token: str) -> HouseholdSession | None:
    """Look up a session by token."""
    return _sessions.get(token)


def invalidate(token: str) -> bool:
    """Remove a session (logout)."""
    return _sessions.pop(token, None) is not None


def get_session_for_household(household_id: str) -> HouseholdSession | None:
    """Find the most recent session for a given household_id."""
    for s in reversed(list(_sessions.values())):
        if s.household_id == household_id:
            return s
    return None


def _generate_token(household_id: str) -> str:
    """Generate a secure session token."""
    raw = f"{household_id}:{secrets.token_hex(32)}:{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()


# ── FastAPI dependency ───────────────────────────────────────────────────


async def get_current_household(request: Request) -> str:
    """FastAPI dependency that extracts and validates the household from the request.

    Checks Authorization header (Bearer token) or falls back to query param
    for demo convenience. Returns the household_id.
    """
    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        session = get_session(token)
        if session:
            return session.household_id

    # Fallback: X-Household-Id header (for demo/dev without full login)
    household_header = request.headers.get("X-Household-Id", "")
    if household_header:
        return household_header

    # Final fallback for backward compat during dev
    return "maya"
