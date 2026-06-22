"""Paths and environment for the Allworth demo backend.

Importing this module loads .env, so any module that reads environment
variables (e.g. the Anthropic client) must import config first.
"""

import os
from pathlib import Path
from typing import Any

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


def bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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


def profile_memory_store() -> str:
    return os.environ.get("PROFILE_MEMORY_STORE", "local_json").strip().lower() or "local_json"


def memory_governance_acknowledged() -> bool:
    return bool_env("PROFILE_MEMORY_GOVERNANCE_ACK", False)


def auth_provider() -> str:
    return os.environ.get("AUTH_PROVIDER", "seed" if not is_production() else "stateless").strip().lower()


def audit_log_target() -> str:
    """Audit sink: stdout by default in production, file path in development."""
    raw = os.environ.get("AUDIT_LOG_TARGET", "").strip()
    if raw:
        return raw
    return "stdout" if is_production() else str(API_DIR / "audit.log")


def data_mode() -> str:
    return os.environ.get("DATA_MODE", "mock").strip().lower() or "mock"


def allow_seed_fallback_in_live() -> bool:
    """Emergency/dev escape hatch for live data failures."""
    return bool_env("ALLOW_SEED_FALLBACK_IN_LIVE", False)


def llm_provider_name() -> str:
    return os.environ.get("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"


def llm_chat_max_tokens() -> int:
    return _int_env("LLM_CHAT_MAX_TOKENS", 2048, minimum=256)


def llm_extract_max_tokens() -> int:
    return _int_env("LLM_EXTRACT_MAX_TOKENS", 1024, minimum=128)


def llm_timeout_seconds() -> float:
    return float(_int_env("LLM_TIMEOUT_SECONDS", 45, minimum=5))


def llm_max_retries() -> int:
    return _int_env("LLM_MAX_RETRIES", 1, minimum=0)


def rate_limit_enabled() -> bool:
    return bool_env("RATE_LIMIT_ENABLED", is_production())


def rate_limit_window_seconds() -> int:
    return _int_env("RATE_LIMIT_WINDOW_SECONDS", 60, minimum=1)


def rate_limit_per_window() -> int:
    return _int_env("RATE_LIMIT_PER_WINDOW", 60, minimum=1)


def chat_rate_limit_per_window() -> int:
    return _int_env("CHAT_RATE_LIMIT_PER_WINDOW", 12, minimum=1)


def chat_memory_enabled() -> bool:
    return bool_env("CHAT_MEMORY_ENABLED", bool(redis_url()))


def _int_env(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def runtime_config_status() -> dict[str, Any]:
    """Validate deployment-critical runtime settings without mutating state."""
    errors: list[str] = []
    warnings: list[str] = []
    provider_name = llm_provider_name()

    if is_production():
        if not os.environ.get("SESSION_SECRET", "").strip():
            errors.append("SESSION_SECRET is required in production")
        if not cors_origins():
            errors.append("CORS_ORIGINS must be set in production")
        if audit_log_target() != "stdout" and not os.environ.get("AUDIT_LOG_TARGET"):
            warnings.append("AUDIT_LOG_TARGET should normally be stdout in production")
        if data_mode() == "mock":
            warnings.append("DATA_MODE=mock is using seeded demo data")

    if provider_name not in {"anthropic", "openai", "azure_openai"}:
        errors.append(f"Unsupported LLM_PROVIDER '{provider_name}'")

    if provider_name == "azure_openai":
        if not os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip():
            errors.append("AZURE_OPENAI_ENDPOINT is required for azure_openai")
        if not os.environ.get("AZURE_OPENAI_API_KEY", "").strip():
            errors.append("AZURE_OPENAI_API_KEY is required for azure_openai")
    elif provider_name == "openai":
        if not os.environ.get("OPENAI_API_KEY", "").strip():
            warnings.append("OPENAI_API_KEY is not set; chat will be unavailable")
    elif provider_name == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY", "").strip():
        warnings.append("ANTHROPIC_API_KEY is not set; chat will be unavailable")

    if not os.environ.get("LLM_CHAT_MODEL", "").strip():
        warnings.append("LLM_CHAT_MODEL is not set; provider default will be used")
    if not os.environ.get("LLM_EXTRACT_MODEL", "").strip():
        warnings.append("LLM_EXTRACT_MODEL is not set; provider default will be used")

    if data_mode() == "live" and not os.environ.get("SYNAPSE_SERVER", "").strip():
        message = "DATA_MODE=live requires SYNAPSE_SERVER"
        if allow_seed_fallback_in_live():
            warnings.append(message)
        else:
            errors.append(message)

    auth_name = auth_provider()
    if auth_name not in {"seed", "stateless", "entra"}:
        errors.append(f"Unsupported AUTH_PROVIDER '{auth_name}'")
    if is_production() and data_mode() == "live":
        if auth_name != "entra":
            errors.append("AUTH_PROVIDER=entra is required for production DATA_MODE=live")
        if auth_name == "entra":
            if not os.environ.get("ENTRA_TENANT_ID", "").strip():
                errors.append("ENTRA_TENANT_ID is required for AUTH_PROVIDER=entra")
            if not os.environ.get("ENTRA_CLIENT_ID", "").strip():
                errors.append("ENTRA_CLIENT_ID is required for AUTH_PROVIDER=entra")
            if not os.environ.get("ENTRA_AUDIENCE", "").strip():
                errors.append("ENTRA_AUDIENCE is required for AUTH_PROVIDER=entra")

    memory_store = profile_memory_store()
    if profile_memory_enabled() and is_production():
        if memory_store in {"", "local", "local_json", "json", "file"}:
            errors.append(
                "PROFILE_MEMORY_ENABLED=true in production requires a durable PROFILE_MEMORY_STORE"
            )
        if not memory_governance_acknowledged():
            errors.append(
                "PROFILE_MEMORY_ENABLED=true in production requires PROFILE_MEMORY_GOVERNANCE_ACK=true"
            )

    if chat_memory_enabled() and not redis_url():
        errors.append("CHAT_MEMORY_ENABLED=true requires REDIS_URL")

    return {
        "ok": not errors,
        "env": app_env(),
        "dataMode": data_mode(),
        "llmProvider": provider_name,
        "authProvider": auth_name,
        "chatMemory": {
            "enabled": chat_memory_enabled(),
            "backend": "redis" if redis_url() else None,
            "ttlSeconds": chat_memory_ttl_seconds(),
            "maxMessages": chat_memory_max_messages(),
        },
        "profileMemory": {
            "enabled": profile_memory_enabled(),
            "store": memory_store,
            "governanceAcknowledged": memory_governance_acknowledged(),
        },
        "errors": errors,
        "warnings": warnings,
    }


def validate_startup_config() -> None:
    status = runtime_config_status()
    if is_production() and not status["ok"]:
        joined = "; ".join(status["errors"])
        raise RuntimeError(f"Invalid production configuration: {joined}")
