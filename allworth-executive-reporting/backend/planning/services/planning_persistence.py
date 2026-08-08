"""Local SQLite persistence used by tests and offline development.

Production persistence is provided by ``SynapsePlanningPersistence``. This
small adapter remains injectable so persistence behavior can be tested without
writing to the live warehouse.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase): pass


class HouseholdRow(Base):
    __tablename__ = "planning_households"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    firm_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    facts: Mapped[dict] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FactsVersionRow(Base):
    __tablename__ = "facts_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("planning_households.id", ondelete="CASCADE"), index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ScenarioRow(Base):
    __tablename__ = "planning_scenarios"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("planning_households.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_facts_version_id: Mapped[str] = mapped_column(ForeignKey("facts_versions.id"), nullable=False)
    overrides: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False)


class AuditRow(Base):
    __tablename__ = "planning_audit_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PortalRecordRow(Base):
    __tablename__ = "planning_portal_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[str] = mapped_column(ForeignKey("planning_households.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PublicationRow(Base):
    __tablename__ = "planning_publications"
    publication_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    household_id: Mapped[str] = mapped_column(String(36), index=True)
    firm_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlanningPersistence:
    def __init__(self, url: str):
        self.engine = create_engine(url, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)

    @classmethod
    def from_environment(cls):
        enabled = (os.getenv("SYNAPSE_PLANNING_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}
        if enabled:
            from planning.db import get_engine
            from planning.services.synapse_planning_persistence import (
                SynapsePlanningPersistence,
            )
            return SynapsePlanningPersistence(
                get_engine(),
                (os.getenv("SYNAPSE_PLANNING_SCHEMA") or "planengine").strip(),
                (os.getenv("AUTH_FIRM_ID") or "").strip(),
            )
        # Local SQLite durability so plans survive restarts without Synapse.
        raw = (os.getenv("PLANNING_LOCAL_DB") or "").strip()
        if raw.lower() in {"0", "false", "no", "off"}:
            return None
        if "://" in raw:
            return cls(raw)
        if not raw and "pytest" in sys.modules:  # keep tests hermetic by default
            return None
        state_dir = Path(__file__).resolve().parent.parent / ".planning-state"
        state_dir.mkdir(exist_ok=True)
        return cls(f"sqlite:///{state_dir / 'planning.db'}")

    def load(self) -> tuple[list[HouseholdRow], list[FactsVersionRow], list[ScenarioRow]]:
        with Session(self.engine) as session:
            return (list(session.query(HouseholdRow)), list(session.query(FactsVersionRow)),
                    list(session.query(ScenarioRow)))

    def load_portal(self) -> list[PortalRecordRow]:
        with Session(self.engine) as session:
            return list(session.query(PortalRecordRow))

    def save_household(self, household_id: str, name: str, facts: dict):
        with Session(self.engine) as session:
            firm_id = (facts.get("metadata", {}).get("_security", {}).get("firm_id"))
            session.merge(HouseholdRow(id=household_id, name=name, firm_id=firm_id,
                                       facts=facts)); session.commit()

    def save_version(self, version_id: str, household_id: str, snapshot: dict):
        with Session(self.engine) as session:
            session.merge(FactsVersionRow(id=version_id, household_id=household_id, snapshot=snapshot)); session.commit()

    def save_scenario(self, record):
        with Session(self.engine) as session:
            session.merge(ScenarioRow(id=str(record.id), household_id=str(record.household_id),
                                      name=record.name, base_facts_version_id=str(record.base_facts_version_id),
                                      overrides=record.overrides, is_recommended=record.is_recommended)); session.commit()

    def append_audit(self, event: dict):
        with Session(self.engine) as session:
            session.add(AuditRow(id=event["id"], actor=event["actor"], action=event["action"],
                                 entity_id=event["entity_id"], payload=event)); session.commit()

    def save_portal(self, record: dict):
        with Session(self.engine) as session:
            session.merge(PortalRecordRow(id=record["id"], household_id=record["household_id"],
                                          kind=record["kind"], payload=record)); session.commit()

    def load_publications(self) -> list[dict]:
        with Session(self.engine) as session:
            return [row.payload for row in session.query(PublicationRow)]

    def save_publication(self, record: dict):
        with Session(self.engine) as session:
            session.merge(PublicationRow(publication_id=record["publication_id"],
                                         household_id=record["household_id"],
                                         firm_id=record.get("firm_id"), payload=record)); session.commit()

    def delete_publications(self, household_id: str):
        with Session(self.engine) as session:
            session.query(PublicationRow).filter_by(household_id=household_id).delete(); session.commit()

    def delete_portal(self, record_id: str):
        with Session(self.engine) as session:
            row = session.get(PortalRecordRow, record_id)
            if row: session.delete(row)
            session.commit()

    def delete_household(self, household_id: str):
        with Session(self.engine) as session:
            # Explicit deletes keep local test behavior deterministic.
            scenario_ids = session.query(ScenarioRow).filter_by(household_id=household_id).all()
            for row in scenario_ids: session.delete(row)
            portal_rows = session.query(PortalRecordRow).filter_by(household_id=household_id).all()
            for row in portal_rows: session.delete(row)
            versions = session.query(FactsVersionRow).filter_by(household_id=household_id).all()
            for row in versions: session.delete(row)
            household = session.get(HouseholdRow, household_id)
            if household: session.delete(household)
            session.commit()
