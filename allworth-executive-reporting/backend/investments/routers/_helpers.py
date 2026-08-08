"""Shared router helpers (Flask)."""

from __future__ import annotations

from contextlib import contextmanager

from flask import jsonify
from werkzeug.exceptions import HTTPException

from investments.services.store import Portfolio


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


@contextmanager
def db_session():
    """Request-scoped DB session; 503 with a helpful detail when unconfigured."""
    from investments.db import get_session_factory

    try:
        session = get_session_factory()()
    except (RuntimeError, ValueError) as exc:
        raise api_error(503, str(exc)) from exc
    try:
        yield session
    finally:
        try:
            session.close()
        except Exception:
            # Synapse can emit rollback errors when no transaction exists.
            pass


def to_summary(portfolio: Portfolio) -> dict:
    return {
        "id": portfolio.id,
        "name": portfolio.name,
        "source_filename": portfolio.source_filename,
        "holdings": len(portfolio.bonds),
        "accounts": portfolio.account_ids,
        "created_at": portfolio.created_at.isoformat(),
    }
