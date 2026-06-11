from fastapi import APIRouter, Request

from allworth_api.application.chat_service import reset_conversations
from allworth_api.application.memory_service import reset_profile
from allworth_api.infrastructure.anthropic_client import client
from allworth_api.infrastructure.seed import seed

router = APIRouter()


@router.get("/api/health")
def health():
    return {"ok": True, "llm": client is not None, "generatedAt": seed["generatedAt"]}


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
