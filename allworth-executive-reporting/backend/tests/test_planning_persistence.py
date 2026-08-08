"""Planning store durability — plans must survive a process restart.

Run:
    python -m pytest tests/test_planning_persistence.py -v
"""

import os

os.environ.setdefault("AUTH_DISABLE", "1")

from planning.services.planning_store import PlanningStore

DRAFT = {
    "name": "Durability Household",
    "people": [{"role": "client", "first_name": "Pat", "last_name": "Durable",
                "date_of_birth": "1980-01-01"}],
    "accounts": [], "income": [], "expenses": [], "assumptions": {},
}


def _sqlite_store(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PLANNING_LOCAL_DB", f"sqlite:///{tmp_path / 'planning.db'}")


def test_household_survives_restart(tmp_path, monkeypatch):
    _sqlite_store(tmp_path, monkeypatch)
    first = PlanningStore()
    facts, scenarios = first.create_household(dict(DRAFT))
    assert len(scenarios) == 2

    reborn = PlanningStore()  # simulates a fresh process
    names = [row["name"] for row in reborn.list_households()]
    assert "Durability Household" in names
    assert len(reborn.scenarios) == 2
    assert reborn.get_facts(facts.household_id).name == "Durability Household"


def test_portal_records_survive_restart(tmp_path, monkeypatch):
    _sqlite_store(tmp_path, monkeypatch)
    first = PlanningStore()
    facts, _ = first.create_household(dict(DRAFT))
    record = first.create_portal(facts.household_id, "tasks", {"title": "Call client"}, "tester")

    reborn = PlanningStore()
    rows = reborn.list_portal(facts.household_id, "tasks")
    assert [row["id"] for row in rows] == [record["id"]]
    assert rows[0]["payload"] == {"title": "Call client"}


def test_delete_household_purges_persistence(tmp_path, monkeypatch):
    _sqlite_store(tmp_path, monkeypatch)
    first = PlanningStore()
    facts, _ = first.create_household(dict(DRAFT))
    first.delete_household(facts.household_id, "tester", "cleanup")

    reborn = PlanningStore()
    assert reborn.list_households() == []


def test_pytest_default_is_hermetic(monkeypatch):
    monkeypatch.delenv("PLANNING_LOCAL_DB", raising=False)
    assert PlanningStore().persistence is None
