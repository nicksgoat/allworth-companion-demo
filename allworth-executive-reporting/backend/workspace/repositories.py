"""Data-access adapters for the connected workspace domain."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from uuid import UUID

from crm.connection import get_db_connection
from planning.services.planning_store import store as planning_store
from workspace.errors import HouseholdIdentifierConflict, WorkspaceDataUnavailable

logger = logging.getLogger(__name__)


class CrmWorkspaceRepository:
    def __init__(self, connection_factory: Callable[[], Any] = get_db_connection):
        self._connection_factory = connection_factory

    def _query(self, statement: str, values: tuple[Any, ...], *, one: bool) -> Any:
        cursor = None
        try:
            cursor = self._connection_factory().cursor()
            cursor.execute(statement, *values)
            return cursor.fetchone() if one else cursor.fetchall()
        except Exception as exc:
            logger.exception("Workspace CRM query failed")
            raise WorkspaceDataUnavailable("Relationship data is temporarily unavailable", detail=str(exc)) from exc
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    logger.warning("Unable to close workspace CRM cursor", exc_info=True)

    def advisor(self, *, email: str | None = None, advisor_id: str | None = None) -> dict[str, Any] | None:
        if advisor_id:
            clause, value, resolution = "User_ID = ?", advisor_id, "override"
        elif email:
            clause, value, resolution = "LOWER(Email) = LOWER(?)", email, "email"
        else:
            return None
        row = self._query(
            "SELECT TOP 1 User_ID,Name,Operational_Region,Title,Email FROM tho.[User] WHERE " + clause,
            (value,), one=True,
        )
        if not row:
            return None
        return {
            "advisor_id": str(row[0] or ""), "name": str(row[1] or ""),
            "region": str(row[2] or ""), "title": str(row[3] or ""),
            "email": str(row[4] or ""), "resolution": resolution,
        }

    @staticmethod
    def _household(row) -> dict[str, Any]:
        return {
            "crm_lead_id": str(row[0] or ""), "salesforce_household_id": str(row[1] or ""),
            "avhhid": str(row[2] or ""), "advisor_id": str(row[3] or ""),
            "aum": float(row[4] or 0), "name": str(row[5] or ""),
            "advisor_name": str(row[6] or ""),
        }

    def household(self, *, lead_id: str | None = None, hhid: str | None = None,
                  avhhid: str | None = None) -> dict[str, Any] | None:
        filters = [("F.LeadId = ?", lead_id), ("F.HHID = ?", hhid), ("F.AVHHID = ?", avhhid)]
        active = [(clause, value) for clause, value in filters if value]
        if not active:
            return None
        rows = self._query(
            "SELECT TOP 2 F.LeadId,F.HHID,F.AVHHID,F.advisorid,F.AUM,D.Name,U.Name "
            "FROM tho.Current_Household_Fact F "
            "LEFT JOIN tho.Current_Household_Demographic D ON D.LeadId=F.LeadId "
            "LEFT JOIN tho.[User] U ON U.User_ID=F.advisorid WHERE " + " AND ".join(clause for clause, _ in active),
            tuple(value for _, value in active), one=False,
        )
        if len(rows) > 1:
            raise HouseholdIdentifierConflict("Household identifiers matched more than one relationship")
        return self._household(rows[0]) if rows else None

    def advisor_book(self, advisor_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT F.LeadId,F.HHID,F.AVHHID,F.advisorid,F.AUM,D.Name,U.Name "
            "FROM tho.Current_Household_Fact F "
            "LEFT JOIN tho.Current_Household_Demographic D ON D.LeadId=F.LeadId "
            "LEFT JOIN tho.[User] U ON U.User_ID=F.advisorid WHERE F.advisorid = ?",
            (advisor_id,), one=False,
        )
        return [self._household(row) for row in rows]


class PlanningWorkspaceRepository:
    def find(self, *, planning_id: str | None = None, lead_id: str | None = None,
             hhid: str | None = None, avhhid: str | None = None):
        try:
            parsed_id = UUID(planning_id) if planning_id else None
        except ValueError:
            return None
        try:
            # Resolve each supplied source independently. Older planning records
            # may contain only one upstream identifier; requiring every CRM ID
            # to be present would turn a valid exact join into a false miss.
            lookups = (
                {"planning_id": parsed_id} if parsed_id else None,
                {"crm_lead_id": lead_id} if lead_id else None,
                {"source_id": hhid} if hhid else None,
                {"avhhid": avhhid} if avhhid else None,
            )
            matches = [planning_store.find_facts(**lookup) for lookup in lookups if lookup]
            resolved = {match.household_id: match for match in matches if match is not None}
            if len(resolved) > 1:
                raise HouseholdIdentifierConflict("Planning identifiers refer to different households")
            return next(iter(resolved.values()), None)
        except ValueError as exc:
            raise HouseholdIdentifierConflict("Planning identifiers are not unique", detail=str(exc)) from exc

    def for_advisor(self, advisor_id: str):
        return planning_store.facts_for_advisor(advisor_id)
