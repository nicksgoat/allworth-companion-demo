"""Assignment persistence and access-separation tests."""
from __future__ import annotations

import pytest

from admin import store


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "_DIR", tmp_path)
    monkeypatch.setattr(store, "_STATE", tmp_path / "admin_state.json")
    monkeypatch.setattr(store, "_schedule_backup", lambda: None)
    monkeypatch.setattr(store, "_dirty", False)
    return store


def test_assignment_does_not_grant_tools(isolated_store):
    isolated_store.add_user("advisor@example.com", "test")
    assignment = isolated_store.add_assignment(
        "Advisor team", "advisor", ["avantos", "crm"], "test"
    )
    isolated_store.set_user_assignment("advisor@example.com", assignment["id"])
    access = isolated_store.effective_for("advisor@example.com")
    assert access["assignment"]["type"] == "advisor"
    assert access["effective_tools"] == []
    assert access["home_tool_ids"] == []


def test_home_tools_are_intersection_of_assignment_and_access(isolated_store):
    isolated_store.add_user("advisor@example.com", "test")
    assignment = isolated_store.add_assignment(
        "Advisor team", "advisor", ["avantos", "crm"], "test"
    )
    isolated_store.set_user_tools("advisor@example.com", ["crm"])
    isolated_store.set_user_assignment("advisor@example.com", assignment["id"], "005-test")
    access = isolated_store.effective_for("advisor@example.com")
    assert access["home_tool_ids"] == ["crm"]
    assert access["advisor_id_override"] == "005-test"


def test_assignment_cannot_be_deleted_while_in_use(isolated_store):
    isolated_store.add_user("advisor@example.com", "test")
    assignment = isolated_store.add_assignment("Advisor team", "advisor", [], "test")
    isolated_store.set_user_assignment("advisor@example.com", assignment["id"])
    with pytest.raises(ValueError, match="Reassign"):
        isolated_store.remove_assignment(assignment["id"])


def test_old_state_migrates_to_general(isolated_store):
    isolated_store._STATE.write_text(
        '{"users":{"person@example.com":{"email":"person@example.com","tools":[]}},"groups":{},"shares":[]}',
        encoding="utf-8",
    )
    access = isolated_store.effective_for("person@example.com")
    assert access["assignment"]["id"] == "general"
    assert isolated_store.list_users()[0]["assignment_id"] is None


def test_legacy_assignments_migrate_to_versioned_sql_store(isolated_store):
    isolated_store._STATE.write_text(
        '{"users":{},"groups":{},"shares":[],"assignments":{"west":{"id":"west","name":"West Advisors","type":"advisor","home_tool_ids":["crm"]}}}',
        encoding="utf-8",
    )
    assert isolated_store.list_assignments()[1]["id"] == "west"
    assert (isolated_store._DIR / "assignments.sqlite3").exists()


def test_soon_tools_cannot_be_configured_on_assignments(isolated_store):
    assignment = isolated_store.add_assignment("Advisor team", "advisor", ["crm", "heatmaps"], "test")
    assert assignment["home_tool_ids"] == ["crm"]
