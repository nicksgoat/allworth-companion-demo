from fastapi import APIRouter, HTTPException, Query, Request

from allworth_api.config import is_production
from allworth_api.core.system_status import (
    audit_tail_entries,
    health_status,
    reset_demo_state,
    route_intent_status,
)

router = APIRouter()


@router.get("/api/health")
def health():
    return health_status()


@router.get("/api/route-intent")
def get_route_intent(q: str = Query(..., description="Natural-language query to route")):
    """Signal-based intent routing: suggests which tool(s) best match a query."""
    if is_production():
        raise HTTPException(status_code=404, detail="Not found")
    return route_intent_status(q)


@router.get("/api/audit/tail")
def audit_tail(n: int = Query(20, ge=1, le=200)):
    """Return the last N audit log entries."""
    if is_production():
        raise HTTPException(status_code=404, detail="Not found")
    return audit_tail_entries(n)


@router.post("/api/demo/reset")
async def demo_reset(request: Request):
    if is_production():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = (body or {}).get("clientId", "maya")
    return reset_demo_state(client_id)
