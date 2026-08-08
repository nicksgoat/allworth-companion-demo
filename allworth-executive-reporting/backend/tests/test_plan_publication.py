"""Tests for the plan publication lifecycle (spec 28 write-back).

Run from the backend/ directory:

    python -m pytest tests/test_plan_publication.py -v
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

os.environ["AUTH_DISABLE"] = "1"

from planning.routes import bp as planning_bp
from planning.services.planning_store import store
from planning.services.publication import publication_registry


HOUSEHOLD_PAYLOAD = {
    "name": "Publication Household",
    "people": [{"role": "client", "date_of_birth": "1960-01-01",
                "retirement_age": 65, "assumed_age_of_death": 90}],
    "accounts": [{"kind": "taxable", "name": "Brokerage", "value": 750000,
                  "growth_rate": "0.05"}],
    "expenses": [{"name": "Living", "kind": "living", "amount": 60000,
                  "starts": {"kind": "immediately"}, "ends": {"kind": "client_death"}}],
    "assumptions": {"start_year": 2026},
}


@pytest.fixture()
def client():
    from flask import Flask

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(planning_bp, url_prefix="/api/v1", name="planning_pub")
    return app.test_client()


@pytest.fixture()
def household(client):
    response = client.post("/api/v1/households", json=HOUSEHOLD_PAYLOAD)
    body = response.get_json()
    household_id = body["household_id"]
    yield household_id
    try:
        store.delete_household(__import__("uuid").UUID(household_id), "tests", "cleanup")
    except KeyError:
        pass
    publication_registry.purge_household(__import__("uuid").UUID(household_id))


def _scenario(client, household_id, name="Proposed Plan"):
    scenarios = client.get(f"/api/v1/households/{household_id}/scenarios").get_json()["scenarios"]
    return next(s["id"] for s in scenarios if s["name"] == name)


class TestPublishLifecycle:
    def test_publish_creates_immutable_snapshot(self, client, household):
        scenario_id = _scenario(client, household)
        response = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                               json={"advisor_note": "Approved in review meeting"})
        assert response.status_code == 201, response.get_json()
        body = response.get_json()
        assert body["status"] == "published"
        assert len(body["input_hash"]) == 64 and len(body["result_hash"]) == 64
        assert body["summary"]["ending_net_worth"]
        assert body["advisor_note"] == "Approved in review meeting"

    def test_idempotent_replay_returns_same_record(self, client, household):
        scenario_id = _scenario(client, household)
        first = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                            json={"idempotency_key": "review-2026-08"})
        replay = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                             json={"idempotency_key": "review-2026-08"})
        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.get_json()["publication_id"] == first.get_json()["publication_id"]

    def test_new_publication_supersedes_prior(self, client, household):
        scenario_id = _scenario(client, household)
        first = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                            json={"idempotency_key": "v1"}).get_json()
        # Change the scenario so the input hash differs.
        client.patch(f"/api/v1/scenarios/{scenario_id}/overrides",
                     json={"overrides": [{"op": "replace",
                                          "path": "/expenses/0/amount",
                                          "value": "65000"}]})
        second = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                             json={"idempotency_key": "v2"}).get_json()
        listing = client.get(f"/api/v1/households/{household}/publications").get_json()
        by_id = {p["publication_id"]: p for p in listing["publications"]}
        assert by_id[first["publication_id"]]["status"] == "superseded"
        assert by_id[first["publication_id"]]["superseded_by"] == second["publication_id"]
        assert by_id[second["publication_id"]]["status"] == "published"

    def test_withdraw(self, client, household):
        scenario_id = _scenario(client, household)
        published = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                                json={}).get_json()
        withdrawn = client.post(
            f"/api/v1/publications/{published['publication_id']}/withdraw",
            json={"reason": "stale assumptions"}).get_json()
        assert withdrawn["status"] == "withdrawn"
        assert "stale assumptions" in (withdrawn["advisor_note"] or "")

    def test_unknown_publication_404(self, client, household):
        assert client.post(f"/api/v1/publications/{uuid4()}/withdraw",
                           json={}).status_code == 404

    def test_input_hash_tracks_facts_changes(self, client, household):
        scenario_id = _scenario(client, household)
        first = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                            json={"idempotency_key": "a"}).get_json()
        client.patch(f"/api/v1/scenarios/{scenario_id}/overrides",
                     json={"overrides": [{"op": "replace",
                                          "path": "/expenses/0/amount",
                                          "value": "72000"}]})
        second = client.post(f"/api/v1/scenarios/{scenario_id}/publish",
                             json={"idempotency_key": "b"}).get_json()
        assert first["input_hash"] != second["input_hash"]
        assert first["result_hash"] != second["result_hash"]

    def test_privacy_delete_purges_publications(self, client, household):
        scenario_id = _scenario(client, household)
        client.post(f"/api/v1/scenarios/{scenario_id}/publish", json={})
        import time
        started = client.post(f"/api/v1/households/{household}/delete",
                              json={"confirmation": "DELETE",
                                    "reason": "test purge"}).get_json()
        for _ in range(100):
            job = client.get(f"/api/v1/jobs/{started['job_id']}").get_json()
            if job["status"] in {"succeeded", "failed"}:
                break
            time.sleep(0.05)
        assert job["status"] == "succeeded"
        assert job["result"]["purge_report"]["publications"]["deleted"] == 1


class TestPublicationDurability:
    """Publications write through the shared persistence adapter (Synapse
    planning schema in production, SQLite locally) and survive a restart."""

    @pytest.fixture()
    def persistence(self, tmp_path):
        from planning.services.planning_persistence import PlanningPersistence
        return PlanningPersistence(f"sqlite:///{tmp_path / 'publications.db'}")

    @pytest.fixture()
    def published(self, client, household, persistence):
        from planning.services.publication import PublicationRegistry
        from planning.services.planning_store import store as planning_store
        registry = PublicationRegistry(persistence=persistence)
        scenario_id = _scenario(client, household)
        facts = planning_store.scenario_facts(__import__("uuid").UUID(scenario_id))
        from planning.services.projections import projection_service
        record, created = registry.publish(
            facts=facts, facts_version_id="v-test",
            scenario_id=__import__("uuid").UUID(scenario_id),
            scenario_name="Proposed Plan", overrides=[],
            projection=projection_service.project(facts),
            actor="tests", firm_id="firm-x")
        assert created
        return persistence, registry, record

    def test_records_survive_restart(self, published):
        from planning.services.publication import PublicationRegistry
        persistence, _, record = published
        reloaded = PublicationRegistry(persistence=persistence)
        revived = reloaded.get(record.publication_id)
        assert revived.status == "published"
        assert revived.input_hash == record.input_hash
        assert revived.summary == record.summary

    def test_withdraw_persists(self, published):
        from planning.services.publication import PublicationRegistry
        persistence, registry, record = published
        registry.withdraw(record.publication_id, "tests", "restart check")
        reloaded = PublicationRegistry(persistence=persistence)
        assert reloaded.get(record.publication_id).status == "withdrawn"

    def test_purge_removes_persisted_rows(self, published):
        from planning.services.publication import PublicationRegistry
        persistence, registry, record = published
        assert registry.purge_household(record.household_id) == 1
        reloaded = PublicationRegistry(persistence=persistence)
        with pytest.raises(KeyError):
            reloaded.get(record.publication_id)
