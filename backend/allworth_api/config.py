"""Paths and environment for the Allworth demo backend.

Importing this module loads .env, so any module that reads environment
variables (e.g. the Anthropic client) must import config first.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

API_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = API_DIR / "data"
MEMORY_DIR = API_DIR / "memory"

load_dotenv(API_DIR / ".env")


def app_env() -> str:
    """Runtime environment name: development, staging, production, or test."""
    return os.environ.get("APP_ENV", "development").strip().lower() or "development"


def is_production() -> bool:
    return app_env() == "production"


def cors_origins() -> list[str]:
    """Allowed CORS origins.

    Development defaults to permissive CORS for Expo/local web. Production must
    set CORS_ORIGINS to a comma-separated allowlist.
    """
    raw = os.environ.get("CORS_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if origins:
        return origins
    return [] if is_production() else ["*"]


def demo_auth_fallback_enabled() -> bool:
    """Allow unauthenticated demo household fallback outside production."""
    raw = os.environ.get("ALLOW_DEMO_AUTH_FALLBACK")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return not is_production()


def seed_auth_enabled() -> bool:
    """Allow seed-persona email login for demos and local development."""
    raw = os.environ.get("ALLOW_SEED_AUTH")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return not is_production()


def session_secret() -> str:
    """Secret used to sign stateless auth tokens."""
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if secret:
        return secret
    if is_production():
        raise RuntimeError("SESSION_SECRET must be set in production")
    return "dev-only-allworth-session-secret"


def session_ttl_seconds() -> int:
    raw = os.environ.get("SESSION_TTL_SECONDS", "86400")
    try:
        return max(300, int(raw))
    except ValueError:
        return 86400


def profile_memory_enabled() -> bool:
    """Whether learned facts/episodes may be written to local runtime storage."""
    raw = os.environ.get("PROFILE_MEMORY_ENABLED")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return not is_production()


def redis_url() -> str:
    """Connection URL for the conversation-memory store (Fly Upstash Redis).

    When unset, the conversation store falls back to an in-process dict — fine
    for local dev and tests, but not shared across Fly's machines.
    """
    return os.environ.get("REDIS_URL", "").strip()


def chat_memory_ttl_seconds() -> int:
    """How long a conversation thread lives in Redis (default 30 days)."""
    raw = os.environ.get("CHAT_MEMORY_TTL_SECONDS", "2592000")
    try:
        return max(60, int(raw))
    except ValueError:
        return 2592000


def chat_memory_max_messages() -> int:
    """Cap on replayed turns (user+assistant messages) to bound tokens/latency."""
    raw = os.environ.get("CHAT_MEMORY_MAX_MESSAGES", "16")
    try:
        return max(2, int(raw))
    except ValueError:
        return 16


def audit_log_target() -> str:
    """Audit sink: stdout by default in production, file path in development."""
    raw = os.environ.get("AUDIT_LOG_TARGET", "").strip()
    if raw:
        return raw
    return "stdout" if is_production() else str(API_DIR / "audit.log")
