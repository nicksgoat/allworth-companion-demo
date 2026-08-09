"""Email-batch workflow endpoints.

Upload an Excel workbook, preview one email per advisor, then confirm the send.
Advisor email resolution is best-effort (DataWarehouse optional) so the preview
always renders; sending goes through the shared Microsoft Graph mailer.
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, ValidationError
from werkzeug.exceptions import HTTPException

import auth_middleware
import mailer
from email_batch import service as rc

logger = logging.getLogger(__name__)
bp = Blueprint("email_batch", __name__, url_prefix="/api/email-batch")

MAX_UPLOAD_BYTES = int(
    os.getenv("EMAIL_BATCH_MAX_UPLOAD_BYTES")
    or os.getenv("BOND_ANALYZER_MAX_UPLOAD_BYTES")  # legacy name from the port
    or 25 * 1024 * 1024
)


class ApiError(HTTPException):
    """HTTP error rendered as ``{"detail": ...}`` (the shape the SPA parses)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(description=detail)
        self.code = status_code
        self.detail = detail

    def get_response(self, environ=None, scope=None):  # noqa: ARG002
        response = jsonify({"detail": self.detail})
        response.status_code = self.code
        return response


def api_error(status_code: int, detail: str) -> ApiError:
    return ApiError(status_code, detail)


def _graph_token() -> str | None:
    return request.headers.get("X-MS-TOKEN-AAD-ACCESS-TOKEN") or None


def _parse_reply_to(raw: str | None) -> list[str]:
    """Parse Reply-To input into unique addresses.

    Accepts semicolon, comma, or newline separators.
    """
    if not raw:
        return []
    parts = [p.strip() for p in re.split(r"[;,\n]+", raw) if p and p.strip()]
    return list(dict.fromkeys(parts))


def _is_same_email(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().lower() == b.strip().lower()


@bp.get("/status")
def status() -> dict:
    """Capability report the frontend reads on load (mirrors Executive Brief)."""
    token = _graph_token()
    mailbox_fallback = bool(os.getenv("MAILER_FROM", "").strip())
    return {
        "graph_token_available": bool(token),
        "mailbox_fallback": mailbox_fallback,
        "ready": bool(token) or mailbox_fallback,
        "user": auth_middleware.easy_auth_user(request),
    }


# Graph mail calls are network-bound; parallelize batch sends without hammering
# the API (Graph throttles around 4 concurrent requests per mailbox).
_SEND_CONCURRENCY = 4


class GroupPreview(BaseModel):
    id: int
    advisors: list[str]
    email: str | None
    cc: list[str]
    row_count: int
    subject: str
    html: str
    sendable: bool


class PreviewResponse(BaseModel):
    batch_id: str
    subject: str
    sender_email: str | None
    advisor_column: str
    total_rows: int
    sendable_rows: int
    columns: list[str]
    rows: list[dict]
    numeric_totals: dict[str, float]
    groups: list[GroupPreview]
    missing_advisors: list[str]
    warnings: list[str]


class SendRequest(BaseModel):
    batch_id: str
    group_ids: list[int] | None = None
    group_cc: dict[str, list[str]] | None = None
    reply_to: str | None = None
    subject: str | None = None


class SendResult(BaseModel):
    group_id: int
    email: str | None
    advisors: list[str]
    sent: bool
    error: str | None = None


class SendResponse(BaseModel):
    sent_count: int
    failed_count: int
    skipped_count: int
    results: list[SendResult]


def _resolve_email_map(advisors: list[str]) -> dict[str, str]:
    """Open a short-lived DB session for the advisor lookup; degrade to empty."""
    try:
        # Deliberate reuse of the investments DW engine (same warehouse).
        from investments.db import get_session_factory

        session = get_session_factory()()
    except Exception:  # noqa: BLE001 - DW not configured/reachable
        return {}
    try:
        return rc.resolve_advisor_emails(session, advisors)
    finally:
        try:
            session.close()
        except Exception:  # noqa: BLE001
            pass


def _to_group_preview(group: rc.EmailGroup) -> GroupPreview:
    return GroupPreview(
        id=group.id,
        advisors=group.advisors,
        email=group.email,
        cc=group.cc,
        row_count=group.row_count,
        subject=group.subject,
        html=group.html,
        sendable=group.sendable,
    )


@bp.post("/preview")
def preview() -> dict:
    file = request.files.get("file")
    if file is None:
        raise api_error(400, "A file upload named 'file' is required.")
    content = file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise api_error(413, "File exceeds the maximum upload size.")
    body = request.form.get("body")

    caller = auth_middleware.easy_auth_user(request)
    sender_email = str(caller.get("email")) if caller and caller.get("email") else None

    try:
        # Peek at advisors first so the DW lookup can be scoped, then build.
        frame = rc.parse_workbook(content, file.filename or "upload.xlsx")
        advisor_col = rc.find_advisor_column(frame)
        advisors = [str(a).strip() for a in frame[advisor_col].dropna().tolist() if str(a).strip()]
        email_map = _resolve_email_map(advisors)
        batch = rc.build_batch(content, file.filename or "upload.xlsx", email_map, sender_email, body)
    except rc.EmailBatchError as exc:
        raise api_error(400, str(exc)) from exc

    warnings: list[str] = []
    if not sender_email:
        warnings.append(
            "You are not signed in, so emails will have no CC or Reply-To. Sign in so replies "
            "route back to you."
        )
    if not email_map:
        warnings.append(
            "Advisor emails could not be loaded from the DataWarehouse. Only rows with an "
            "Email column will be sendable."
        )
    if batch.missing_advisors:
        warnings.append(
            f"{len(batch.missing_advisors)} advisor(s) have no email address and will be skipped."
        )

    return PreviewResponse(
        batch_id=batch.id,
        subject=batch.subject,
        sender_email=batch.sender_email,
        advisor_column=batch.advisor_column,
        total_rows=batch.total_rows,
        sendable_rows=batch.sendable_rows,
        columns=batch.columns,
        rows=batch.rows,
        numeric_totals=batch.numeric_totals,
        groups=[_to_group_preview(g) for g in batch.groups],
        missing_advisors=batch.missing_advisors,
        warnings=warnings,
    ).model_dump()


@bp.post("/send")
def send() -> dict:
    try:
        payload = SendRequest.model_validate(request.get_json(force=True, silent=False) or {})
    except ValidationError as exc:
        raise api_error(422, str(exc)) from exc

    batch = rc.store.get(payload.batch_id)
    if batch is None:
        raise api_error(
            404,
            "Batch not found or expired. Re-upload the workbook to preview again.",
        )

    caller = auth_middleware.easy_auth_user(request)
    caller_label = str(caller.get("email")) if caller else "app-token"

    # Prefer delegated send (as the signed-in user) using the Easy Auth Graph
    # token injected by App Service's token store. Falls back to app-only via
    # MAILER_FROM when the token store isn't enabled (local dev, dev slot).
    graph_token = _graph_token()
    mailbox = None if graph_token else (os.getenv("MAILER_FROM", "").strip() or None)
    if not graph_token and not mailbox:
        raise api_error(
            503,
            "Advisor Mailer is not configured: enable the Easy Auth token store "
            "(Mail.Send permission) or set the MAILER_FROM app setting as a "
            "fallback service mailbox.",
        )

    # Reply-To: user's input → batch sender email → signed-in caller (no-op for
    # delegated since the reply-to is already the sender's own mailbox).
    if (payload.reply_to or "").strip():
        reply_to = _parse_reply_to(payload.reply_to)
    else:
        fallback_reply_to = batch.sender_email or (
            str(caller.get("email")) if caller and caller.get("email") else None
        )
        reply_to = [fallback_reply_to] if fallback_reply_to else []

    selected = payload.group_ids
    group_cc_map = payload.group_cc or {}
    subject_override = (payload.subject or "").strip() or None
    results: list[SendResult] = []
    skipped = 0

    to_send = []
    for group in batch.groups:
        if selected is not None and group.id not in selected:
            continue
        if not group.sendable or not group.email:
            skipped += 1
            results.append(
                SendResult(
                    group_id=group.id,
                    email=group.email,
                    advisors=group.advisors,
                    sent=False,
                    error="No email address resolved for this advisor.",
                )
            )
            continue
        to_send.append(group)

    def _send_one(group) -> SendResult:
        extra_cc = [e.strip() for e in group_cc_map.get(str(group.id), []) if e and e.strip()]
        group_base_cc = [c for c in (group.cc or []) if c and c.strip()]
        sender_email = batch.sender_email

        if reply_to:
            non_sender_group_cc = [
                c for c in group_base_cc if not _is_same_email(c, sender_email)
            ]
            base_cc = [*reply_to, *non_sender_group_cc]
        else:
            base_cc = group_base_cc

        cc = [
            c
            for c in dict.fromkeys([*base_cc, *extra_cc])
            if c and not _is_same_email(c, group.email)
        ]
        subject = subject_override or group.subject
        try:
            mailer.send_email(
                group.email,
                subject,
                group.html,
                cc=cc or None,
                html=True,
                reply_to=reply_to or None,
                token=graph_token,
                mailbox=mailbox,
            )
            logger.info(
                "Email-batch email sent to %s (advisors=%s, caller=%s)",
                group.email,
                group.advisors,
                caller_label,
            )
            return SendResult(group_id=group.id, email=group.email, advisors=group.advisors, sent=True)
        except mailer.MailError as exc:
            logger.warning("Email-batch email failed for %s: %s", group.email, exc)
            return SendResult(
                group_id=group.id,
                email=group.email,
                advisors=group.advisors,
                sent=False,
                error=str(exc),
            )

    if to_send:
        with ThreadPoolExecutor(max_workers=min(_SEND_CONCURRENCY, len(to_send))) as pool:
            results.extend(pool.map(_send_one, to_send))

    sent = sum(1 for r in results if r.sent)
    failed = sum(1 for r in results if not r.sent) - skipped

    return SendResponse(
        sent_count=sent,
        failed_count=failed,
        skipped_count=skipped,
        results=results,
    ).model_dump()
