"""Plan publication — immutable approved-plan snapshots (spec 28 write-back).

Publishing is distinct from persistence: drafts and scenarios stay in the
operational store, while a *publication* is an immutable, hash-addressed
snapshot of a committed facts version plus its projection summary. Downstream
BI reads publications from the ``pla`` mart
(migrations/002_synapse_plan_publication_schema.sql); this module owns the
lifecycle (published → superseded / withdrawn) and idempotency guarantees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from threading import RLock
from uuid import UUID, uuid4

from planengine.models import Facts, Projection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical(payload) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash(payload) -> str:
    return sha256(_canonical(payload).encode()).hexdigest()


@dataclass
class PublicationRecord:
    publication_id: UUID
    household_id: UUID
    scenario_id: UUID
    scenario_name: str
    household_name: str
    facts_version_id: str
    firm_id: str | None
    source_household_id: str | None
    status: str  # published | superseded | withdrawn
    published_at: str
    published_by: str
    idempotency_key: str
    input_hash: str
    result_hash: str
    summary: dict
    advisor_note: str | None = None
    superseded_by: UUID | None = None
    withdrawn_at: str | None = None
    withdrawn_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "publication_id": str(self.publication_id),
            "household_id": str(self.household_id),
            "scenario_id": str(self.scenario_id),
            "scenario_name": self.scenario_name,
            "household_name": self.household_name,
            "facts_version_id": self.facts_version_id,
            "firm_id": self.firm_id,
            "source_household_id": self.source_household_id,
            "status": self.status,
            "published_at": self.published_at,
            "published_by": self.published_by,
            "idempotency_key": self.idempotency_key,
            "input_hash": self.input_hash,
            "result_hash": self.result_hash,
            "summary": self.summary,
            "advisor_note": self.advisor_note,
            "superseded_by": str(self.superseded_by) if self.superseded_by else None,
            "withdrawn_at": self.withdrawn_at,
            "withdrawn_by": self.withdrawn_by,
        }


def build_summary(projection: Projection) -> dict:
    """Reporting-friendly projection summary stored with each publication."""
    return {
        "start_year": projection.start_year,
        "horizon_years": len(projection.rows),
        "ending_net_worth": str(projection.ending_net_worth),
        "lifetime_taxes": str(projection.lifetime_taxes),
        "first_shortfall_year": projection.first_shortfall_year,
        "warnings": list(projection.warnings),
    }


def _record_from_payload(payload: dict) -> PublicationRecord:
    """Rebuild a record from a persisted ``to_dict`` payload."""
    summary = payload.get("summary")
    if isinstance(summary, str):
        summary = json.loads(summary or "{}")
    return PublicationRecord(
        publication_id=UUID(payload["publication_id"]),
        household_id=UUID(payload["household_id"]),
        scenario_id=UUID(payload["scenario_id"]),
        scenario_name=payload["scenario_name"],
        household_name=payload["household_name"],
        facts_version_id=payload["facts_version_id"],
        firm_id=payload.get("firm_id") or None,
        source_household_id=payload.get("source_household_id"),
        status=payload["status"],
        published_at=str(payload["published_at"]),
        published_by=payload["published_by"],
        idempotency_key=payload["idempotency_key"],
        input_hash=payload["input_hash"],
        result_hash=payload["result_hash"],
        summary=summary or {},
        advisor_note=payload.get("advisor_note"),
        superseded_by=UUID(payload["superseded_by"]) if payload.get("superseded_by") else None,
        withdrawn_at=str(payload["withdrawn_at"]) if payload.get("withdrawn_at") else None,
        withdrawn_by=payload.get("withdrawn_by"))


def _payload_from_warehouse_row(row) -> dict:
    """Map published_plans mart columns to the ``to_dict`` payload shape."""
    return {
        "publication_id": row.publication_id, "household_id": row.household_id,
        "scenario_id": row.scenario_id, "scenario_name": row.scenario_name,
        "household_name": row.household_name,
        "facts_version_id": row.facts_version_id, "firm_id": row.firm_id,
        "source_household_id": row.source_household_id, "status": row.status,
        "published_at": row.published_at, "published_by": row.published_by,
        "idempotency_key": row.idempotency_key, "input_hash": row.input_hash,
        "result_hash": row.result_hash, "summary": row.summary_json,
        "advisor_note": row.advisor_note,
        "superseded_by": row.superseded_by_publication_id,
        "withdrawn_at": row.withdrawn_at, "withdrawn_by": row.withdrawn_by,
    }


class PublicationRegistry:
    """Thread-safe publication lifecycle with idempotent replay.

    Durability follows the planning store's adapter: live Azure Synapse writes
    into the PlanEngine-owned schema (``SYNAPSE_PLANNING_SCHEMA``) when
    ``SYNAPSE_PLANNING_ENABLED=true`` — never the governed sfp/tho source
    tables — with a local SQLite fallback for offline development.
    """

    def __init__(self, persistence=None):
        self._lock = RLock()
        self._records: dict[UUID, PublicationRecord] = {}
        if persistence is None:
            from planning.services.planning_store import store
            persistence = store.persistence
        self.persistence = persistence
        if self.persistence is not None and hasattr(self.persistence, "load_publications"):
            for loaded in self.persistence.load_publications():
                payload = loaded if isinstance(loaded, dict) else _payload_from_warehouse_row(loaded)
                record = _record_from_payload(payload)
                self._records[record.publication_id] = record

    def _persist(self, record: PublicationRecord) -> None:
        if self.persistence is not None and hasattr(self.persistence, "save_publication"):
            self.persistence.save_publication(record.to_dict())

    def publish(self, *, facts: Facts, facts_version_id: str, scenario_id: UUID,
                scenario_name: str, overrides: list[dict], projection: Projection,
                actor: str, firm_id: str | None, advisor_note: str | None = None,
                idempotency_key: str | None = None) -> tuple[PublicationRecord, bool]:
        """Publish a plan snapshot. Returns (record, created).

        Replaying the same idempotency key returns the existing record.
        A new publication supersedes any active one for the same scenario.
        """
        input_hash = _hash({"facts_version_id": facts_version_id,
                            "facts": facts.model_dump(mode="json"),
                            "overrides": overrides})
        result_hash = _hash(build_summary(projection))
        key = idempotency_key or f"{scenario_id}:{input_hash[:16]}:{result_hash[:16]}"
        with self._lock:
            existing = next((r for r in self._records.values()
                             if r.idempotency_key == key), None)
            if existing is not None:
                return existing, False
            record = PublicationRecord(
                publication_id=uuid4(), household_id=facts.household_id,
                scenario_id=scenario_id, scenario_name=scenario_name,
                household_name=facts.name, facts_version_id=facts_version_id,
                firm_id=firm_id,
                source_household_id=facts.metadata.get("source_id"),
                status="published", published_at=_now(), published_by=actor,
                idempotency_key=key, input_hash=input_hash,
                result_hash=result_hash, summary=build_summary(projection),
                advisor_note=advisor_note)
            for prior in self._records.values():
                if (prior.scenario_id == scenario_id and prior.status == "published"):
                    prior.status = "superseded"
                    prior.superseded_by = record.publication_id
                    self._persist(prior)
            self._records[record.publication_id] = record
            self._persist(record)
            return record, True

    def get(self, publication_id: UUID) -> PublicationRecord:
        record = self._records.get(publication_id)
        if record is None:
            raise KeyError(publication_id)
        return record

    def for_household(self, household_id: UUID) -> list[PublicationRecord]:
        with self._lock:
            records = [r for r in self._records.values()
                       if r.household_id == household_id]
        return sorted(records, key=lambda r: r.published_at, reverse=True)

    def withdraw(self, publication_id: UUID, actor: str,
                 reason: str | None = None) -> PublicationRecord:
        with self._lock:
            record = self.get(publication_id)
            if record.status == "withdrawn":
                return record
            record.status = "withdrawn"
            record.withdrawn_at = _now()
            record.withdrawn_by = actor
            if reason:
                record.advisor_note = f"{record.advisor_note or ''}\nWithdrawn: {reason}".strip()
            self._persist(record)
            return record

    def purge_household(self, household_id: UUID) -> int:
        """Privacy delete support: remove all publications for a household."""
        with self._lock:
            doomed = [pid for pid, r in self._records.items()
                      if r.household_id == household_id]
            for pid in doomed:
                del self._records[pid]
            if doomed and self.persistence is not None and hasattr(self.persistence, "delete_publications"):
                self.persistence.delete_publications(str(household_id))
            return len(doomed)


publication_registry = PublicationRegistry()
