import pydantic
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from allworth_api.config import demo_auth_fallback_enabled
from allworth_api.core.auth import authenticate, authenticate_email, get_session, invalidate

router = APIRouter()


def _bearer_token(request: Request, token: str = "") -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return token


class LoginRequest(BaseModel):
    model_config = {"populate_by_name": True}

    household_id: str = pydantic.Field(alias="householdId")
    passcode: str


class EmailLoginRequest(BaseModel):
    email: str


@router.post("/api/auth/login")
def login(body: LoginRequest):
    """Authenticate a household with passcode (demo mode)."""
    if not demo_auth_fallback_enabled():
        return JSONResponse(status_code=404, content={"error": "Not found"})
    session = authenticate(body.household_id, body.passcode)
    if not session:
        return JSONResponse(status_code=401, content={"error": "Invalid credentials"})
    return {
        "token": session.token,
        "householdId": session.household_id,
    }


@router.post("/api/auth/login/email")
def login_email(body: EmailLoginRequest):
    """Authenticate by client email — looks up household in Synapse.

    No password required for demo. The email is matched against
    Contact_Demographic to resolve the household (AVHHID).
    """
    if not body.email or not body.email.strip():
        return JSONResponse(status_code=400, content={"error": "Email is required"})

    session = authenticate_email(body.email)
    if not session:
        return JSONResponse(
            status_code=401,
            content={"error": "Email not found. Check spelling or contact your advisor."},
        )
    return {
        "token": session.token,
        "householdId": session.household_id,
        "email": session.email,
        "contactName": session.contact_name,
    }


@router.get("/api/auth/me")
def me(request: Request, token: str = ""):
    """Get current session info from a bearer token (passed as query param or header)."""
    session = get_session(_bearer_token(request, token))
    if not session:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    return {
        "householdId": session.household_id,
        "email": session.email,
        "contactName": session.contact_name,
    }


@router.post("/api/auth/logout")
def logout(request: Request, token: str = ""):
    """Invalidate a session token."""
    invalidate(_bearer_token(request, token))
    return {"ok": True}
