"""System status and admin helpers for system routes."""

from __future__ import annotations

import json
from typing import Any

from allworth_api.config import app_env, data_mode, runtime_config_status
from allworth_api.core.audit import AUDIT_PATH
from allworth_api.core.chat_service import reset_conversations
from allworth_api.core.memory import reset_profile
from allworth_api.core.routing import route_intent
from allworth_api.data.llm import _PROVIDER_NAME, provider
from allworth_api.data.redis_client import reachability_status as redis_reachability_status
from allworth_api.data.seed import current_seed
from allworth_api.data.synapse import is_available as synapse_available


def health_status() -> dict[str, Any]:
    config = runtime_config_status()
    return {
        "ok": config["ok"],
        "env": app_env(),
        "llm": provider is not None,
        "llmProvider": _PROVIDER_NAME if provider else None,
        "synapse": synapse_available() and data_mode() == "live",
        "generatedAt": current_seed()["generatedAt"],
        "readiness": config,
    }


def liveness_status() -> dict[str, Any]:
    return {"ok": True, "service": "allworth-companion-api"}


def readiness_status() -> dict[str, Any]:
    config = runtime_config_status()
    redis_status = redis_reachability_status() if config["chatMemory"]["enabled"] else {
        "configured": False,
        "reachable": True,
        "error": None,
    }
    checks = {
        "config": config["ok"],
        "llmConfigured": provider is not None,
        "synapseConfigured": data_mode() != "live" or synapse_available(),
        "redisReachable": redis_status["reachable"],
    }
    return {
        "ok": all(checks.values()),
        "checks": checks,
        "config": config,
        "redis": redis_status,
        "llmProvider": _PROVIDER_NAME if provider else None,
        "dataMode": data_mode(),
    }


def route_intent_status(query: str) -> dict[str, Any]:
    matches = route_intent(query)
    return {
        "query": query,
        "matches": [{"tool": m.tool, "score": m.score, "signals": m.signals} for m in matches],
    }


def audit_tail_entries(n: int) -> dict[str, Any]:
    if AUDIT_PATH is None or not AUDIT_PATH.exists():
        return {"entries": []}

    lines = AUDIT_PATH.read_text().strip().splitlines()
    entries = []
    for line in lines[-n:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return {"entries": entries}


def reset_demo_state(client_id: str) -> dict[str, Any]:
    reset_conversations()
    profile = reset_profile(client_id)
    return {"ok": True, "clientId": client_id, "facts": len(profile["facts"])}
