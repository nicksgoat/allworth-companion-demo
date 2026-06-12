from fastapi import APIRouter, Query, Request

from allworth_api.core.audit import AUDIT_PATH
from allworth_api.core.chat_service import reset_conversations
from allworth_api.core.memory import reset_profile
from allworth_api.core.routing import route_intent
from allworth_api.data.llm import provider, _PROVIDER_NAME
from allworth_api.data.seed import seed
from allworth_api.data.synapse import is_available as synapse_available

router = APIRouter()


@router.get("/api/health")
def health():
    return {
        "ok": True,
        "llm": provider is not None,
        "llmProvider": _PROVIDER_NAME if provider else None,
        "synapse": synapse_available(),
        "generatedAt": seed["generatedAt"],
    }


@router.get("/api/route-intent")
def get_route_intent(q: str = Query(..., description="Natural-language query to route")):
    """Signal-based intent routing: suggests which tool(s) best match a query."""
    matches = route_intent(q)
    return {
        "query": q,
        "matches": [{"tool": m.tool, "score": m.score, "signals": m.signals} for m in matches],
    }


@router.get("/api/audit/tail")
def audit_tail(n: int = Query(20, ge=1, le=200)):
    """Return the last N audit log entries."""
    if not AUDIT_PATH.exists():
        return {"entries": []}
    import json

    lines = AUDIT_PATH.read_text().strip().splitlines()
    recent = lines[-n:]
    entries = []
    for line in recent:
        try:
            entries.append(json.loads(line))
        except Exception:
            continue
    return {"entries": entries}


@router.post("/api/demo/reset")
async def demo_reset(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = (body or {}).get("clientId", "maya")
    reset_conversations()
    profile = reset_profile(client_id)
    return {"ok": True, "clientId": client_id, "facts": len(profile["facts"])}
