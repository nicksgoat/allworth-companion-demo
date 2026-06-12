from fastapi import APIRouter
from fastapi.responses import JSONResponse
import pydantic
from pydantic import BaseModel

from allworth_api.core.auth import authenticate, authenticate_email, get_session, invalidate

router = APIRouter()


class LoginRequest(BaseModel):
    model_config = {"populate_by_name": True}

    household_id: str = pydantic.Field(alias="householdId")
    passcode: str


class EmailLoginRequest(BaseModel):
    email: str


@router.post("/api/auth/login")
def login(body: LoginRequest):
    """Authenticate a household with passcode (demo mode)."""
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
def me(token: str = ""):
    """Get current session info from a bearer token (passed as query param or header)."""
    session = get_session(token)
    if not session:
        return JSONResponse(status_code=401, content={"error": "Not authenticated"})
    return {
        "householdId": session.household_id,
        "email": session.email,
        "contactName": session.contact_name,
    }


@router.post("/api/auth/logout")
def logout(token: str = ""):
    """Invalidate a session token."""
    invalidate(token)
    return {"ok": True}
