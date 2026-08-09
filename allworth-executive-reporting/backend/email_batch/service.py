"""Workbook parsing and preview assembly for Advisor Mailer.

The module is deliberately independent of Flask so preview generation can be
tested without authentication or Graph access. Sending remains in routes.py
and always requires an explicit second request from the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from html import escape
from io import BytesIO
import math
import re
from threading import RLock
import time
from typing import Any
from uuid import uuid4

import pandas as pd
from sqlalchemy import text


class EmailBatchError(ValueError):
    """A user-correctable workbook or template error."""


@dataclass
class EmailGroup:
    id: int
    advisors: list[str]
    email: str | None
    cc: list[str]
    row_count: int
    subject: str
    html: str

    @property
    def sendable(self) -> bool:
        return bool(self.email)


@dataclass
class EmailBatch:
    id: str
    subject: str
    advisor_column: str
    total_rows: int
    groups: list[EmailGroup]
    missing_advisors: list[str]
    sender_email: str | None
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    numeric_totals: dict[str, float] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    @property
    def sendable_rows(self) -> int:
        return sum(group.row_count for group in self.groups if group.sendable)


class BatchStore:
    """Small process-local preview store with a bounded lifetime."""

    def __init__(self, ttl_seconds: int = 60 * 60) -> None:
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, EmailBatch] = {}
        self._lock = RLock()

    def put(self, batch: EmailBatch) -> None:
        with self._lock:
            self._purge_locked()
            self._items[batch.id] = batch

    def get(self, batch_id: str) -> EmailBatch | None:
        with self._lock:
            self._purge_locked()
            return self._items.get(batch_id)

    def _purge_locked(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        expired = [key for key, item in self._items.items() if item.created_at < cutoff]
        for key in expired:
            self._items.pop(key, None)


store = BatchStore()

_ADVISOR_HINTS = (
    "primary advisor",
    "advisor name",
    "advisor",
    "wealth advisor",
    "lead advisor",
)
_EMAIL_HINTS = ("advisor email", "email address", "email", "e-mail")


def _column_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).strip().lower()).strip()


def _clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except (TypeError, ValueError):
            pass
    return value


def parse_workbook(content: bytes, filename: str) -> pd.DataFrame:
    if not content:
        raise EmailBatchError("The workbook is empty.")
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "xlsx"
    try:
        if suffix == "csv":
            frame = pd.read_csv(BytesIO(content))
        elif suffix in {"xlsx", "xlsm", "xls"}:
            frame = pd.read_excel(BytesIO(content))
        else:
            raise EmailBatchError("Upload an Excel (.xlsx) or CSV file.")
    except EmailBatchError:
        raise
    except Exception as exc:
        raise EmailBatchError(f"The workbook could not be read: {exc}") from exc
    frame = frame.dropna(how="all").copy()
    if frame.empty:
        raise EmailBatchError("The workbook has headers but no data rows.")
    frame.columns = [str(column).strip() or f"Column {index + 1}" for index, column in enumerate(frame.columns)]
    return frame


def find_advisor_column(frame: pd.DataFrame) -> str:
    keyed = {_column_key(column): str(column) for column in frame.columns}
    for hint in _ADVISOR_HINTS:
        if hint in keyed:
            return keyed[hint]
    for column in frame.columns:
        if "advisor" in _column_key(column):
            return str(column)
    raise EmailBatchError(
        "No advisor column was found. Add a column such as 'Primary Advisor' or 'Advisor'."
    )


def _find_email_column(frame: pd.DataFrame) -> str | None:
    keyed = {_column_key(column): str(column) for column in frame.columns}
    for hint in _EMAIL_HINTS:
        if hint in keyed:
            return keyed[hint]
    return next((str(column) for column in frame.columns if "email" in _column_key(column)), None)


def resolve_advisor_emails(session, advisors: list[str]) -> dict[str, str]:
    """Resolve advisor names through tho.User; callers already degrade safely."""
    wanted = {_column_key(name): name for name in advisors if _clean_text(name)}
    if not wanted:
        return {}
    rows = session.execute(text("SELECT Name, Email FROM tho.[User] WHERE Email IS NOT NULL")).fetchall()
    resolved: dict[str, str] = {}
    for name, email in rows:
        key = _column_key(name)
        if key in wanted and _clean_text(email):
            resolved[wanted[key]] = _clean_text(email)
    return resolved


def _safe_message(body: str | None) -> str:
    value = body or "<p>Please review the accounts below.</p>"
    value = re.sub(r"<script\b[^>]*>.*?</script>", "", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"\son\w+\s*=\s*(['\"]).*?\1", "", value, flags=re.IGNORECASE | re.DOTALL)
    return value


def _table_html(columns: list[str], rows: list[dict[str, Any]]) -> str:
    header = "".join(f"<th>{escape(column)}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{escape(str(row.get(column) if row.get(column) is not None else ''))}</td>" for column in columns)
        body_rows.append(f"<tr>{cells}</tr>")
    return (
        "<table style=\"width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:13px\">"
        f"<thead><tr>{header}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    ).replace("<th>", "<th style=\"padding:8px;text-align:left;background:#173D67;color:#fff;border:1px solid #d9e0e8\">") \
     .replace("<td>", "<td style=\"padding:8px;border:1px solid #d9e0e8\">")


def build_batch(
    content: bytes,
    filename: str,
    email_map: dict[str, str],
    sender_email: str | None,
    body: str | None,
) -> EmailBatch:
    frame = parse_workbook(content, filename)
    advisor_column = find_advisor_column(frame)
    email_column = _find_email_column(frame)
    columns = [str(column) for column in frame.columns]
    subject = filename.rsplit(".", 1)[0].replace("_", " ").replace("-", " ").strip() or "Advisor account review"
    normalized_map = {_column_key(name): email for name, email in email_map.items() if _clean_text(email)}

    raw_rows = [{column: _json_value(value) for column, value in row.items()} for row in frame.to_dict(orient="records")]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    preview_rows: list[dict[str, Any]] = []
    missing: set[str] = set()

    for row in raw_rows:
        advisor = _clean_text(row.get(advisor_column))
        workbook_email = _clean_text(row.get(email_column)) if email_column else ""
        resolved_email = normalized_map.get(_column_key(advisor), "") if advisor else ""
        email = workbook_email or resolved_email
        status = "ready" if advisor and email else ("missing_email" if advisor else "missing_advisor")
        if advisor and not email:
            missing.add(advisor)
        preview_row = dict(row)
        preview_row.update({"__advisor": advisor or None, "__email": email or None, "__group_id": None, "__status": status})
        preview_rows.append(preview_row)
        grouped.setdefault((_column_key(advisor), email.lower()), []).append(preview_row)

    groups: list[EmailGroup] = []
    for group_id, ((_, _), rows) in enumerate(grouped.items(), start=1):
        advisors = sorted({_clean_text(row.get("__advisor")) for row in rows if _clean_text(row.get("__advisor"))})
        email = _clean_text(rows[0].get("__email")) or None
        for row in rows:
            row["__group_id"] = group_id
        table_rows = [{column: row.get(column) for column in columns} for row in rows]
        html = (
            "<div style=\"font-family:Arial,sans-serif;color:#173D67;line-height:1.5\">"
            f"{_safe_message(body)}{_table_html(columns, table_rows)}</div>"
        )
        groups.append(EmailGroup(
            id=group_id,
            advisors=advisors,
            email=email,
            cc=[sender_email] if sender_email else [],
            row_count=len(rows),
            subject=subject,
            html=html,
        ))

    numeric_totals: dict[str, float] = {}
    for column in columns:
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.notna().any() and series.notna().sum() >= max(1, len(series) // 2):
            numeric_totals[column] = float(series.sum())

    batch = EmailBatch(
        id=uuid4().hex,
        subject=subject,
        advisor_column=advisor_column,
        total_rows=len(preview_rows),
        groups=groups,
        missing_advisors=sorted(missing),
        sender_email=sender_email,
        columns=columns,
        rows=preview_rows,
        numeric_totals=numeric_totals,
    )
    store.put(batch)
    return batch
