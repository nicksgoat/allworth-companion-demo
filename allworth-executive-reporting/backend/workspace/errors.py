"""Structured workspace-domain errors exposed by the HTTP adapter."""

from __future__ import annotations


class WorkspaceError(Exception):
    status_code = 500
    code = "workspace_error"

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class WorkspaceDataUnavailable(WorkspaceError):
    status_code = 503
    code = "workspace_data_unavailable"


class HouseholdIdentifierConflict(WorkspaceError):
    status_code = 409
    code = "household_identifier_conflict"
