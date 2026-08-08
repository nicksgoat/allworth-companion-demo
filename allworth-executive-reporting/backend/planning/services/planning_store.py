"""Thread-safe planning repository used by the API service.

The engine is storage-agnostic.  This repository keeps drafts and scenarios
available in a single-process development deployment; production deployments
use the documented Azure Synapse planning schema without changing API or engine
contracts.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any
from uuid import UUID, uuid4

from planengine.models import Facts
from planning.services.planning_persistence import PlanningPersistence


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_patch(document: dict, operations: list[dict]) -> dict:
    result = deepcopy(document)
    for operation in operations:
        op, raw_path = operation.get("op"), operation.get("path", "")
        if op not in {"add", "replace", "remove"} or not raw_path.startswith("/"):
            raise ValueError("invalid JSON Patch operation")
        tokens = [x.replace("~1", "/").replace("~0", "~") for x in raw_path[1:].split("/")]
        cursor: Any = result
        for token in tokens[:-1]:
            cursor = cursor[int(token)] if isinstance(cursor, list) else cursor[token]
        leaf = tokens[-1]
        if op == "remove":
            cursor.pop(int(leaf)) if isinstance(cursor, list) else cursor.pop(leaf)
        elif isinstance(cursor, list):
            if op == "add" and leaf == "-": cursor.append(operation.get("value"))
            elif op == "add": cursor.insert(int(leaf), operation.get("value"))
            else: cursor[int(leaf)] = operation.get("value")
        else:
            if op == "replace" and leaf not in cursor:
                raise ValueError(f"replace target does not exist: {raw_path}")
            cursor[leaf] = operation.get("value")
    return result


@dataclass
class ScenarioRecord:
    id: UUID
    household_id: UUID
    name: str
    base_facts_version_id: UUID
    overrides: list[dict] = field(default_factory=list)
    is_recommended: bool = False
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


class PlanningStore:
    def __init__(self):
        self._lock = RLock()
        self.facts: dict[UUID, Facts] = {}
        self.versions: dict[UUID, list[tuple[UUID, dict]]] = {}
        self.scenarios: dict[UUID, ScenarioRecord] = {}
        self.audit: list[dict] = []
        self.portal: dict[UUID, dict] = {}
        self.persistence = PlanningPersistence.from_environment()
        if self.persistence:
            self._warm_load()

    def _warm_load(self, attempts: int = 3) -> None:
        """Load persisted state, retrying transient warehouse connection blips
        so a single network hiccup at boot cannot disable the whole module."""
        import time

        for attempt in range(1, attempts + 1):
            try:
                households, versions, scenarios = self.persistence.load()
                portal = self.persistence.load_portal()
                break
            except Exception:
                if attempt == attempts:
                    raise
                time.sleep(2 * attempt)
        for row in households: self.facts[UUID(row.id)] = Facts.model_validate(row.facts)
        for row in versions: self.versions.setdefault(UUID(row.household_id), []).append((UUID(row.id), row.snapshot))
        for row in scenarios:
            self.scenarios[UUID(row.id)] = ScenarioRecord(UUID(row.id), UUID(row.household_id), row.name,
                                                           UUID(row.base_facts_version_id), row.overrides,
                                                           row.is_recommended)
        for row in portal:
            self.portal[UUID(row.id)] = row.payload

    def list_households(self) -> list[dict]:
        with self._lock:
            return [{"id": str(hid), "name": facts.name,
                     "people": len(facts.people), "accounts": len(facts.accounts),
                     "source": facts.metadata.get("source", "planning")}
                    for hid, facts in self.facts.items()]

    def create_household(self, payload: dict, actor: str = "system") -> tuple[Facts, list[ScenarioRecord]]:
        facts = Facts.model_validate(payload)
        with self._lock:
            if facts.household_id in self.facts:
                raise ValueError("household already exists")
            self.facts[facts.household_id] = facts
            version = uuid4()
            self.versions[facts.household_id] = [(version, facts.model_dump(mode="json"))]
            current = ScenarioRecord(uuid4(), facts.household_id, "Current Plan", version)
            proposed = ScenarioRecord(uuid4(), facts.household_id, "Proposed Plan", version)
            self.scenarios[current.id] = current; self.scenarios[proposed.id] = proposed
            if self.persistence:
                self.persistence.save_household(str(facts.household_id), facts.name, facts.model_dump(mode="json"))
                self.persistence.save_version(str(version), str(facts.household_id), facts.model_dump(mode="json"))
                self.persistence.save_scenario(current); self.persistence.save_scenario(proposed)
            self._audit(actor, "create", facts.household_id, None, facts.model_dump(mode="json"))
            return facts, [current, proposed]

    def get_facts(self, household_id: UUID) -> Facts:
        with self._lock:
            if household_id not in self.facts:
                raise KeyError(household_id)
            return self.facts[household_id].model_copy(deep=True)

    def patch_facts(self, household_id: UUID, operations: list[dict], actor: str) -> Facts:
        with self._lock:
            old = self.get_facts(household_id).model_dump(mode="json")
            updated = Facts.model_validate(apply_patch(old, operations))
            self.facts[household_id] = updated
            if self.persistence: self.persistence.save_household(str(household_id), updated.name, updated.model_dump(mode="json"))
            self._audit(actor, "patch", household_id, old, updated.model_dump(mode="json"), operations)
            return updated

    def replace_facts(self, household_id: UUID, facts: Facts, actor: str,
                      action: str = "replace") -> Facts:
        """Wholesale facts replacement (used by warehouse actuals sync)."""
        with self._lock:
            old = self.get_facts(household_id).model_dump(mode="json")
            updated = facts.model_copy(deep=True)
            updated.household_id = household_id
            self.facts[household_id] = updated
            if self.persistence: self.persistence.save_household(str(household_id), updated.name, updated.model_dump(mode="json"))
            self._audit(actor, action, household_id, old, updated.model_dump(mode="json"))
            return updated

    def commit(self, household_id: UUID, actor: str) -> UUID:
        with self._lock:
            facts = self.get_facts(household_id)
            version = uuid4()
            self.versions[household_id].append((version, facts.model_dump(mode="json")))
            if self.persistence: self.persistence.save_version(str(version), str(household_id), facts.model_dump(mode="json"))
            for scenario in self.scenarios.values():
                if (scenario.household_id == household_id and
                        (scenario.name == "Current Plan" or not scenario.overrides)):
                    scenario.base_facts_version_id = version
                    if scenario.name == "Current Plan": scenario.overrides = []
                    scenario.updated_at = _now()
                    if self.persistence: self.persistence.save_scenario(scenario)
            self._audit(actor, "commit", household_id, None, {"version_id": str(version)})
            return version

    def scenarios_for(self, household_id: UUID) -> list[ScenarioRecord]:
        return [deepcopy(x) for x in self.scenarios.values() if x.household_id == household_id]

    def get_scenario(self, scenario_id: UUID) -> ScenarioRecord:
        if scenario_id not in self.scenarios:
            raise KeyError(scenario_id)
        return deepcopy(self.scenarios[scenario_id])

    def create_scenario(self, household_id: UUID, name: str, actor: str) -> ScenarioRecord:
        with self._lock:
            if household_id not in self.facts: raise KeyError(household_id)
            if any(x.household_id == household_id and x.name.lower() == name.strip().lower()
                   for x in self.scenarios.values()):
                raise ValueError("scenario name already exists")
            version = self.versions[household_id][-1][0]
            record = ScenarioRecord(uuid4(), household_id, name.strip(), version)
            self.scenarios[record.id] = record
            if self.persistence: self.persistence.save_scenario(record)
            self._audit(actor, "scenario_create", household_id, None, {"scenario_id": str(record.id), "name": record.name})
            return deepcopy(record)

    def promote_scenario(self, scenario_id: UUID, actor: str) -> ScenarioRecord:
        with self._lock:
            record = self.scenarios.get(scenario_id)
            if record is None: raise KeyError(scenario_id)
            for candidate in self.scenarios.values():
                if candidate.household_id == record.household_id:
                    candidate.is_recommended = candidate.id == scenario_id
                    if self.persistence: self.persistence.save_scenario(candidate)
            self._audit(actor, "scenario_promote", record.household_id, None, {"scenario_id": str(scenario_id)})
            return deepcopy(record)

    def scenario_facts(self, scenario_id: UUID) -> Facts:
        scenario = self.get_scenario(scenario_id)
        base = next((snapshot for vid, snapshot in self.versions[scenario.household_id]
                     if vid == scenario.base_facts_version_id), None)
        if base is None:
            raise KeyError(scenario.base_facts_version_id)
        return Facts.model_validate(apply_patch(base, scenario.overrides))

    def patch_scenario(self, scenario_id: UUID, overrides: list[dict], actor: str) -> ScenarioRecord:
        with self._lock:
            record = self.scenarios.get(scenario_id)
            if record is None: raise KeyError(scenario_id)
            if record.name == "Current Plan" and overrides:
                raise ValueError("Current Plan is immutable; apply levers to a working scenario")
            # Validate overrides against the immutable base before accepting.
            base = next(snapshot for vid, snapshot in self.versions[record.household_id]
                        if vid == record.base_facts_version_id)
            Facts.model_validate(apply_patch(base, overrides))
            record.overrides = deepcopy(overrides); record.updated_at = _now()
            if self.persistence: self.persistence.save_scenario(record)
            self._audit(actor, "scenario_overrides", record.household_id, None,
                        {"scenario_id": str(scenario_id), "overrides": overrides})
            return deepcopy(record)

    def delete_household(self, household_id: UUID, actor: str, reason: str) -> dict:
        """Delete all planning state for a household and return purge counts."""
        with self._lock:
            if household_id not in self.facts: raise KeyError(household_id)
            scenario_ids = [sid for sid, row in self.scenarios.items()
                            if row.household_id == household_id]
            version_count = len(self.versions.get(household_id, []))
            portal_ids = [rid for rid, row in self.portal.items()
                          if row["household_id"] == str(household_id)]
            self._audit(actor, "privacy_delete", household_id, None,
                        {"reason": reason, "scenario_count": len(scenario_ids),
                         "facts_version_count": version_count})
            for scenario_id in scenario_ids: self.scenarios.pop(scenario_id, None)
            self.versions.pop(household_id, None)
            for record_id in portal_ids: self.portal.pop(record_id, None)
            self.facts.pop(household_id, None)
            if self.persistence: self.persistence.delete_household(str(household_id))
            return {"facts": 1, "facts_versions": version_count,
                    "scenarios": len(scenario_ids), "portal_records": len(portal_ids)}

    def list_portal(self, household_id: UUID, kind: str) -> list[dict]:
        with self._lock:
            if household_id not in self.facts: raise KeyError(household_id)
            return [deepcopy(row) for row in self.portal.values()
                    if row["household_id"] == str(household_id) and row["kind"] == kind]

    def create_portal(self, household_id: UUID, kind: str, payload: dict, actor: str) -> dict:
        with self._lock:
            if household_id not in self.facts: raise KeyError(household_id)
            now = _now()
            record = {"id": str(uuid4()), "household_id": str(household_id),
                      "kind": kind, "payload": deepcopy(payload), "created_at": now,
                      "updated_at": now, "created_by": actor}
            self.portal[UUID(record["id"])] = record
            if self.persistence: self.persistence.save_portal(record)
            self._audit(actor, f"{kind}_create", household_id, None, record)
            return deepcopy(record)

    def update_portal(self, record_id: UUID, payload: dict, actor: str,
                      household_id: UUID | None = None) -> dict:
        with self._lock:
            record = self.portal.get(record_id)
            if record is None or (household_id is not None and
                                  record["household_id"] != str(household_id)):
                raise KeyError(record_id)
            old = deepcopy(record)
            record["payload"].update(deepcopy(payload)); record["updated_at"] = _now()
            if self.persistence: self.persistence.save_portal(record)
            self._audit(actor, f"{record['kind']}_update", UUID(record["household_id"]), old, record)
            return deepcopy(record)

    def record_event(self, actor: str, action: str, entity_id: UUID,
                     payload: dict | None = None) -> None:
        with self._lock:
            self._audit(actor, action, entity_id, None, payload or {})

    def _audit(self, actor, action, entity_id, old, new, operations=None):
        event = {"id": str(uuid4()), "timestamp": _now(), "actor": actor,
                 "action": action, "entity_id": str(entity_id),
                 "old": old, "new": new, "operations": operations}
        self.audit.append(event)
        if self.persistence: self.persistence.append_audit(event)


store = PlanningStore()
