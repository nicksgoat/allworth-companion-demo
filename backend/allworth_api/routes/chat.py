from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse

from allworth_api.core.auth import get_current_household
from allworth_api.core.chat_service import stream_chat
from allworth_api.core.feedback import record_response_feedback
from allworth_api.sse import sse

router = APIRouter()


@router.post("/api/chat")
async def post_chat(request: Request, household_id: str = Depends(get_current_household)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = body.get("clientId", household_id)
    # Enforce household scoping — can only chat as your own household
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    session = body.get("session", "wednesday")
    conversation_id = body.get("conversationId") or body.get("conversation_id")
    message = body.get("message")
    if not message:
        return JSONResponse(status_code=400, content={"error": "message required"})

    async def event_stream():
        async for event, data in stream_chat(client_id, session, message, conversation_id):
            yield sse(event, data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/api/chat/feedback")
async def post_chat_feedback(request: Request, household_id: str = Depends(get_current_household)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    client_id = body.get("clientId", household_id)
    if client_id != household_id:
        return JSONResponse(status_code=403, content={"error": "Access denied for this household"})
    rating = body.get("rating")
    if rating not in {"positive", "negative"}:
        return JSONResponse(status_code=400, content={"error": "rating must be positive or negative"})
    return record_response_feedback(
        client_id=client_id,
        conversation_id=body.get("conversationId", ""),
        message_id=body.get("messageId", ""),
        rating=rating,
        sources=body.get("sources") or [],
        tool_calls=body.get("toolCalls") or [],
        suggestions=body.get("suggestions") or [],
        answer_preview=body.get("answerPreview") or "",
        quality=body.get("quality") or {},
        request_id=getattr(request.state, "request_id", None),
    )
