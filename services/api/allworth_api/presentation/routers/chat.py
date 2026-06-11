from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from allworth_api.application.chat_service import stream_chat
from allworth_api.presentation.sse import sse

router = APIRouter()


@router.post("/api/chat")
async def post_chat(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = body.get("clientId", "maya")
    session = body.get("session", "wednesday")
    message = body.get("message")
    if not message:
        return JSONResponse(status_code=400, content={"error": "message required"})

    async def event_stream():
        async for event, data in stream_chat(client_id, session, message):
            yield sse(event, data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
