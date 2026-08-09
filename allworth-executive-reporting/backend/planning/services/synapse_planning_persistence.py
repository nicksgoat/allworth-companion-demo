"""Durable PlanEngine persistence in a dedicated Azure Synapse schema.

Salesforce/Tamarac schemas remain source-only. This adapter writes only to the
configured planning schema and includes ``firm_id`` in every read and write.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _json(value) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


def _utcnow() -> str:
    """Client-side UTC timestamp: Synapse rejects function calls inside VALUES
    when the statement also streams long nvarchar(max) parameters."""
    from datetime import UTC, datetime
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _decoded(value, fallback):
    if value in (None, ""): return fallback
    return json.loads(value)


class SynapsePlanningPersistence:
    def __init__(self, engine: Engine, schema: str, firm_id: str):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", schema):
            raise ValueError("invalid SYNAPSE_PLANNING_SCHEMA")
        if not firm_id:
            raise RuntimeError("AUTH_FIRM_ID is required for Synapse planning persistence")
        self.engine = engine
        self.schema = schema
        self.firm_id = firm_id

    def _table(self, name: str) -> str:
        return f"[{self.schema}].[{name}]"

    def load(self):
        with self.engine.connect() as connection:
            households = [SimpleNamespace(id=row.id, name=row.name, firm_id=row.firm_id,
                                          facts=_decoded(row.facts_json, {}))
                          for row in connection.execute(text(
                              f"SELECT id,name,firm_id,facts_json FROM {self._table('households')} "
                              "WHERE firm_id=:firm_id"), {"firm_id": self.firm_id})]
            versions = [SimpleNamespace(id=row.id, household_id=row.household_id,
                                        snapshot=_decoded(row.snapshot_json, {}))
                        for row in connection.execute(text(
                            f"SELECT id,household_id,snapshot_json FROM {self._table('facts_versions')} "
                            "WHERE firm_id=:firm_id"), {"firm_id": self.firm_id})]
            scenarios = [SimpleNamespace(id=row.id, household_id=row.household_id, name=row.name,
                                         base_facts_version_id=row.base_facts_version_id,
                                         overrides=_decoded(row.overrides_json, []),
                                         is_recommended=bool(row.is_recommended))
                         for row in connection.execute(text(
                             f"SELECT id,household_id,name,base_facts_version_id,overrides_json,is_recommended "
                             f"FROM {self._table('scenarios')} WHERE firm_id=:firm_id"),
                             {"firm_id": self.firm_id})]
        return households, versions, scenarios

    def load_portal(self):
        with self.engine.connect() as connection:
            return [SimpleNamespace(id=row.id, payload=_decoded(row.payload_json, {}))
                    for row in connection.execute(text(
                        f"SELECT id,payload_json FROM {self._table('portal_records')} "
                        "WHERE firm_id=:firm_id"), {"firm_id": self.firm_id})]

    def save_household(self, household_id: str, name: str, facts: dict):
        # Synapse dedicated pools reject IF @@ROWCOUNT batches; check the update
        # count client-side and insert when no row matched.
        values = {"id": household_id, "name": name,
                  "firm_id": self.firm_id, "facts": _json(facts), "now": _utcnow()}
        self._upsert(
            text(f"""
                UPDATE {self._table('households')}
                   SET name=:name, facts_json=:facts, updated_at=:now
                 WHERE id=:id AND firm_id=:firm_id
            """),
            text(f"""
                INSERT INTO {self._table('households')}
                    (id,name,firm_id,facts_json,updated_at)
                VALUES (:id,:name,:firm_id,:facts,:now)
            """), values)

    def save_version(self, version_id: str, household_id: str, snapshot: dict):
        values = {"id": version_id, "household_id": household_id,
                  "firm_id": self.firm_id, "snapshot": _json(snapshot), "now": _utcnow()}
        with self.engine.begin() as connection:
            exists = connection.execute(
                text(f"SELECT COUNT(*) FROM {self._table('facts_versions')} "
                     "WHERE id=:id AND firm_id=:firm_id"),
                {"id": version_id, "firm_id": self.firm_id}).scalar()
            if not exists:
                connection.execute(text(f"""
                    INSERT INTO {self._table('facts_versions')}
                        (id,household_id,firm_id,snapshot_json,created_at)
                    VALUES (:id,:household_id,:firm_id,:snapshot,:now)
                """), values)

    def save_scenario(self, record):
        values = {"id": str(record.id), "household_id": str(record.household_id),
                  "firm_id": self.firm_id, "name": record.name,
                  "base": str(record.base_facts_version_id),
                  "overrides": _json(record.overrides),
                  "recommended": 1 if record.is_recommended else 0, "now": _utcnow()}
        self._upsert(
            text(f"""
                UPDATE {self._table('scenarios')}
                   SET name=:name,base_facts_version_id=:base,overrides_json=:overrides,
                       is_recommended=:recommended,updated_at=:now
                 WHERE id=:id AND firm_id=:firm_id
            """),
            text(f"""
                INSERT INTO {self._table('scenarios')}
                    (id,household_id,firm_id,name,base_facts_version_id,overrides_json,
                     is_recommended,created_at,updated_at)
                VALUES (:id,:household_id,:firm_id,:name,:base,:overrides,:recommended,
                        :now,:now)
            """), values)

    def append_audit(self, event: dict):
        self._execute(text(f"""
            INSERT INTO {self._table('audit_log')}
                (id,firm_id,actor,action,entity_id,payload_json,created_at)
            VALUES (:id,:firm_id,:actor,:action,:entity_id,:payload,:now)
        """), {"id": event["id"], "firm_id": self.firm_id,
                 "actor": event["actor"], "action": event["action"],
                 "entity_id": event["entity_id"], "payload": _json(event),
                 "now": _utcnow()})

    def save_portal(self, record: dict):
        values = {"id": record["id"], "household_id": record["household_id"],
                  "firm_id": self.firm_id, "kind": record["kind"],
                  "payload": _json(record), "now": _utcnow()}
        self._upsert(
            text(f"""
                UPDATE {self._table('portal_records')}
                   SET kind=:kind,payload_json=:payload,updated_at=:now
                 WHERE id=:id AND firm_id=:firm_id
            """),
            text(f"""
                INSERT INTO {self._table('portal_records')}
                    (id,household_id,firm_id,kind,payload_json,created_at,updated_at)
                VALUES (:id,:household_id,:firm_id,:kind,:payload,
                        SYSUTCDATETIME(),SYSUTCDATETIME())
            """), values)

    def delete_portal(self, record_id: str):
        self._execute(text(f"DELETE FROM {self._table('portal_records')} "
                           "WHERE id=:id AND firm_id=:firm_id"),
                      {"id": record_id, "firm_id": self.firm_id})

    # -- Publications (spec 28 mart) ------------------------------------------
    # Writes go only to the PlanEngine-owned schema; sfp/tho stay read-only.
    def load_publications(self):
        with self.engine.connect() as connection:
            return [SimpleNamespace(**dict(row._mapping)) for row in connection.execute(
                text(f"""SELECT publication_id,household_id,scenario_id,scenario_name,
                                household_name,facts_version_id,firm_id,
                                source_household_id,status,published_at,published_by,
                                idempotency_key,input_hash,result_hash,summary_json,
                                advisor_note,superseded_by_publication_id,
                                withdrawn_at,withdrawn_by
                         FROM {self._table('published_plans')}
                         WHERE firm_id=:firm_id"""),
                {"firm_id": self.firm_id})]

    def save_publication(self, record: dict):
        """Idempotent upsert of one publication snapshot row."""
        def _dt(value):
            # datetime2 rejects timezone offsets; timestamps are always UTC ISO.
            return str(value).replace("+00:00", "") if value else None

        values = {
            "publication_id": record["publication_id"],
            "firm_id": self.firm_id or record.get("firm_id") or "",
            "household_id": record["household_id"],
            "source_household_id": record.get("source_household_id"),
            "household_name": record["household_name"],
            "facts_version_id": record["facts_version_id"],
            "scenario_id": record["scenario_id"],
            "scenario_name": record["scenario_name"],
            "status": record["status"],
            "published_at": _dt(record["published_at"]),
            "published_by": record["published_by"],
            "superseded_by": record.get("superseded_by"),
            "withdrawn_at": _dt(record.get("withdrawn_at")),
            "withdrawn_by": record.get("withdrawn_by"),
            "idempotency_key": record["idempotency_key"],
            "input_hash": record["input_hash"],
            "result_hash": record["result_hash"],
            "summary": _json(record.get("summary", {})),
            "advisor_note": record.get("advisor_note"),
        }
        self._upsert(
            text(f"""
                UPDATE {self._table('published_plans')}
                   SET status=:status,
                       superseded_by_publication_id=:superseded_by,
                       withdrawn_at=:withdrawn_at, withdrawn_by=:withdrawn_by,
                       advisor_note=:advisor_note
                 WHERE publication_id=:publication_id AND firm_id=:firm_id
            """),
            text(f"""
                INSERT INTO {self._table('published_plans')}
                    (publication_id,firm_id,household_id,source_household_id,
                     household_name,facts_version_id,scenario_id,scenario_name,
                     status,published_at,published_by,
                     superseded_by_publication_id,withdrawn_at,withdrawn_by,
                     idempotency_key,input_hash,result_hash,summary_json,advisor_note)
                VALUES (:publication_id,:firm_id,:household_id,:source_household_id,
                        :household_name,:facts_version_id,:scenario_id,:scenario_name,
                        :status,:published_at,:published_by,
                        :superseded_by,:withdrawn_at,:withdrawn_by,
                        :idempotency_key,:input_hash,:result_hash,:summary,:advisor_note)
            """), values)

    def delete_publications(self, household_id: str):
        self._execute(text(f"DELETE FROM {self._table('published_plans')} "
                           "WHERE household_id=:id AND firm_id=:firm_id"),
                      {"id": household_id, "firm_id": self.firm_id})

    def delete_household(self, household_id: str):
        with self.engine.begin() as connection:
            params = {"id": household_id, "firm_id": self.firm_id}
            for table in ("portal_records", "scenarios", "facts_versions", "households"):
                connection.execute(text(f"DELETE FROM {self._table(table)} "
                                        "WHERE household_id=:id AND firm_id=:firm_id"
                                        if table != "households" else
                                        f"DELETE FROM {self._table(table)} WHERE id=:id AND firm_id=:firm_id"),
                                   params)

    def _execute(self, statement, values):
        with self.engine.begin() as connection:
            connection.execute(statement, values)

    def _upsert(self, update_stmt, insert_stmt, values) -> None:
        """Update-then-insert upsert compatible with Synapse dedicated pools
        (which reject IF @@ROWCOUNT multi-statement batches)."""
        with self.engine.begin() as connection:
            result = connection.execute(update_stmt, values)
            if (result.rowcount or 0) == 0:
                connection.execute(insert_stmt, values)

