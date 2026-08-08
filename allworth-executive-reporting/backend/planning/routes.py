"""Financial planning API v1 — Flask blueprint.

This is a faithful Flask port of the original FastAPI planning router. It is
mounted at ``/api/v1`` by ``backend/app.py`` and reuses the framework-agnostic
``planengine`` core plus the ``planning.services`` layer (thread-safe in-memory
store with optional Synapse persistence).

Auth: integrates with the shared Flask JWT middleware, which sets
``request.environ['user.email']`` and ``request.environ['user.claims']``. When
auth is disabled (local dev / tests) there is no user and household isolation is
bypassed, mirroring the original behavior.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from threading import Lock, Thread
from uuid import UUID, uuid4

from flask import Blueprint, Response, jsonify, request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from planning.db import get_session_factory
from planning.services.planning_store import ScenarioRecord, store
from planning.services.warehouse_planning import contract as warehouse_contract
from planning.services.warehouse_planning import (AmbiguousHouseholdError,
                                                  attach_current_holdings,
                                                  import_household,
                                                  resolve_household_id)
from planning.services.warehouse_monte_carlo import (monte_carlo_parameters,
                                                     resolve_monte_carlo_inputs)
from planning.services.warehouse_cma import resolve_capital_market_assumptions
from planning.services.plan_tracking import (apply_actuals, diff_accounts,
                                             drift_status)
from planning.services.publication import publication_registry
from planning.services.reports import render_report
from planning.services.projections import projection_service
from planning.services.vault import vault_service
from planengine.engine import run_projection
from planengine.estate import build_estate_flow
from planengine.goals import evaluate_goals
from planengine.lifecycle import (InvestorParams, SensitivityRequest,
                                  investor_params_from_facts, run_lifecycle_plan)
from planengine.models import Facts
from planengine.montecarlo import run_monte_carlo
from planengine.optimizers import (analyze_nua, inherited_ira_schedules,
                                   optimize_social_security)
from planengine.roth import analyze_roth_conversions
from planengine.solvers import solve_monthly_savings

bp = Blueprint("planning", __name__)


# ---------------------------------------------------------------------------
# Error handling — mirror FastAPI's HTTPException(detail=...) JSON shape so the
# existing frontend (which reads ``body.detail``) keeps working unchanged.
# ---------------------------------------------------------------------------
class ApiError(Exception):
    def __init__(self, status_code: int, detail):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


@bp.errorhandler(ApiError)
def _handle_api_error(exc: ApiError):
    return jsonify(detail=exc.detail), exc.status_code


def _not_found(kind: str):
    raise ApiError(404, f"{kind} not found")


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------
def _json_body() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _qbool(name: str, default: bool = False) -> bool:
    raw = request.args.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _decimal(value, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ApiError(422, f"{field} must be a number")


def _user() -> dict:
    claims = request.environ.get("user.claims")
    email = request.environ.get("user.email")
    if not claims and not email:
        return {}
    user = dict(claims) if isinstance(claims, dict) else {}
    if email:
        user["email"] = email
    return user


def _actor() -> str:
    user = _user()
    return user.get("email") or user.get("oid") or "local-user"


def _firm_id() -> str | None:
    return _user().get("firm_id") or (os.getenv("AUTH_FIRM_ID") or "").strip() or None


def _roles() -> set[str]:
    roles = _user().get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    return {str(role).lower() for role in roles}


def _household_claims() -> set[str]:
    values = _user().get("household_ids") or []
    if isinstance(values, str):
        values = values.split(",")
    return {str(value).strip() for value in values if str(value).strip()}


def _is_client() -> bool:
    return bool(_roles() & {"client", "portal_client", "planengine.client"})


def _authorize_household(household_id: UUID) -> None:
    try:
        facts = store.get_facts(household_id)
    except KeyError:
        raise ApiError(404, "household not found")
    user = _user()
    if not user:  # Authentication-disabled local development and unit tests.
        return
    security = facts.metadata.get("_security", {})
    stored_firm = security.get("firm_id")
    if stored_firm and _firm_id() != stored_firm:
        raise ApiError(404, "household not found")
    if _is_client():
        email = str(user.get("email") or "").lower()
        client_emails = {str(value).lower() for value in security.get("client_emails", [])}
        if str(household_id) not in _household_claims() and email not in client_emails:
            raise ApiError(404, "household not found")


@bp.before_request
def require_resource_access() -> None:
    """Enforce firm and client-household isolation without leaking existence."""
    view_args = request.view_args or {}
    household_id = view_args.get("household_id")
    scenario_id = view_args.get("scenario_id")
    if scenario_id:
        try:
            household_id = store.get_scenario(UUID(str(scenario_id))).household_id
        except (KeyError, ValueError):
            raise ApiError(404, "scenario not found")
    if household_id:
        try:
            parsed = household_id if isinstance(household_id, UUID) else UUID(str(household_id))
        except ValueError:
            raise ApiError(404, "household not found")
        _authorize_household(parsed)
    job_id = view_args.get("job_id")
    if job_id:
        try:
            with _jobs_lock:
                job_record = deepcopy(_jobs.get(UUID(str(job_id))))
        except ValueError:
            job_record = None
        if job_record is None:
            raise ApiError(404, "job not found")
        if job_record.get("household_id"):
            try:
                _authorize_household(UUID(job_record["household_id"]))
            except ApiError:
                # A completed privacy deletion no longer has a household row to
                # authorize against, so bind its result to the initiating actor.
                if not (job_record.get("kind") == "privacy_delete" and
                        job_record.get("actor") == _actor() and
                        job_record.get("firm_id") == _firm_id()):
                    raise
    if _is_client():
        path = request.path
        if (path.startswith("/api/v1/scenarios/") or path.startswith("/api/v1/advisor/") or
                path.endswith("/facts") or path.endswith("/facts/commit") or
                path.endswith("/scenarios")):
            raise ApiError(404, "resource not found")
        allowed_client_write = (
            request.method == "POST" and
            (path.endswith("/vault/files") or path.endswith("/organizer-change-requests"))
        )
        if request.method not in {"GET", "HEAD", "OPTIONS"} and not allowed_client_write:
            raise ApiError(403, "client portal mutation is not permitted")


def _secured_facts(facts: Facts) -> Facts:
    secured = facts.model_copy(deep=True)
    security = dict(secured.metadata.get("_security", {}))
    if firm_id := _firm_id():
        security["firm_id"] = firm_id
    security["created_by"] = _actor()
    client_emails = [str(getattr(person, "email", "")).lower()
                     for person in secured.people if getattr(person, "email", None)]
    if client_emails:
        security["client_emails"] = sorted(set(client_emails))
    secured.metadata["_security"] = security
    return secured


def _scenario_dict(record: ScenarioRecord) -> dict:
    return {"id": str(record.id), "household_id": str(record.household_id),
            "name": record.name, "base_facts_version_id": str(record.base_facts_version_id),
            "overrides": record.overrides, "is_recommended": record.is_recommended,
            "created_at": record.created_at, "updated_at": record.updated_at}


_WAREHOUSE_LOCKED_ASSET_PATHS = ("/accounts", "/real_estate")


def _path_matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in prefixes)


def _reject_warehouse_asset_patch(facts: Facts, operations: list[dict]) -> None:
    """Keep Synapse-sourced asset facts read-only inside the planning copy."""
    if str(facts.metadata.get("source", "")).lower() != "datawarehouse":
        return
    for operation in operations:
        paths = [str(operation.get("path") or "")]
        if operation.get("from") is not None:
            paths.append(str(operation.get("from") or ""))
        if any(_path_matches_prefix(path, _WAREHOUSE_LOCKED_ASSET_PATHS) for path in paths):
            raise ApiError(
                409,
                ("Assets imported from Synapse are read-only in the planning tool. "
                 "Edit the source system and re-import, or adjust planning assumptions, "
                 "cash flows, goals, insurance, and liabilities instead."),
            )


# ---------------------------------------------------------------------------
# Request body validation models (kept for validation parity with the original)
# ---------------------------------------------------------------------------
class PatchBody(BaseModel):
    ops: list[dict]


class OverrideBody(BaseModel):
    overrides: list[dict]


class ScenarioCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class MonteCarloBody(BaseModel):
    trials: int = Field(default=300, ge=10, le=1000)
    seed: int = 42
    refresh_synapse_inputs: bool = True


class DeleteBody(BaseModel):
    confirmation: str
    reason: str = Field(min_length=3, max_length=500)


class VaultShareBody(BaseModel):
    shared_with_client: bool


class PortalRecordBody(BaseModel):
    payload: dict


def _validate(model: type[BaseModel], payload: dict):
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise ApiError(422, exc.errors(include_url=False)) from exc


# ---------------------------------------------------------------------------
# Households
# ---------------------------------------------------------------------------
@bp.get("/households")
def list_households():
    households = store.list_households()
    visible = []
    for household in households:
        try:
            _authorize_household(UUID(household["id"]))
        except ApiError:
            continue
        visible.append(household)
    return jsonify(households=visible)


@bp.post("/households")
def create_household():
    try:
        facts = _validate(Facts, _json_body())
        facts = _secured_facts(facts)
        created, scenarios = store.create_household(facts.model_dump(), _actor())
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc
    return jsonify(household_id=str(created.household_id),
                   scenario_ids=[str(x.id) for x in scenarios],
                   facts=created.model_dump(mode="json")), 201


@bp.get("/households/<uuid:household_id>/summary")
def household_summary(household_id: UUID):
    try:
        facts = store.get_facts(household_id)
    except KeyError:
        _not_found("household")
    total_assets = sum((x.value for x in facts.accounts if not x.exclude_from_planning), Decimal("0"))
    total_liabilities = sum((x.current_balance for x in facts.liabilities), Decimal("0"))
    net_worth = total_assets - total_liabilities
    scenarios = store.scenarios_for(household_id)
    return jsonify(id=str(household_id), name=facts.name,
                   net_worth=str(net_worth),
                   total_assets=str(total_assets),
                   total_liabilities=str(total_liabilities),
                   people_count=len(facts.people),
                   account_count=len(facts.accounts), scenario_count=len(scenarios),
                   source=facts.metadata.get("source", "planning"),
                   data_quality_warnings=facts.metadata.get("data_quality_warnings", []),
                   data_quality={"has_client": any(p.role == "client" for p in facts.people),
                                 "has_accounts": bool(facts.accounts),
                                 "has_income": bool(facts.income), "has_expenses": bool(facts.expenses)})


@bp.get("/households/<uuid:household_id>/facts")
def get_facts(household_id: UUID):
    try:
        facts = store.get_facts(household_id)
        if facts.metadata.get("source") == "datawarehouse" and any(not account.holdings for account in facts.accounts):
            try:
                session = get_session_factory()()
                try:
                    facts = attach_current_holdings(session, facts)
                finally:
                    session.close()
            except (SQLAlchemyError, RuntimeError, ValueError):
                pass
        return jsonify(facts.model_dump(mode="json"))
    except KeyError:
        _not_found("household")


# ---------------------------------------------------------------------------
# Vault (documents)
# ---------------------------------------------------------------------------
@bp.get("/households/<uuid:household_id>/vault/files")
def list_vault_files(household_id: UUID):
    return jsonify(files=vault_service.list(household_id, client_visible_only=_is_client()))


@bp.post("/households/<uuid:household_id>/vault/files")
def upload_vault_file(household_id: UUID):
    upload = request.files.get("file")
    if upload is None:
        raise ApiError(422, "file is required")
    content = upload.read()
    folder = request.form.get("folder", "Shared")
    shared_with_client = _form_bool("shared_with_client", False)
    try:
        record = vault_service.add(household_id, upload.filename or "document",
                                   upload.mimetype or "application/octet-stream",
                                   content, _actor(), folder, shared_with_client)
    except ValueError as exc:
        raise ApiError(422, str(exc)) from exc
    store.record_event(_actor(), "vault_upload", household_id,
                       {key: record[key] for key in ("id", "name", "size", "sha256")})
    return jsonify(record), 201


def _form_bool(name: str, default: bool) -> bool:
    raw = request.form.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@bp.get("/households/<uuid:household_id>/vault/files/<uuid:file_id>")
def download_vault_file(household_id: UUID, file_id: UUID):
    try:
        record, content = vault_service.get(household_id, file_id)
    except KeyError:
        _not_found("vault file")
    if _is_client() and not record["shared_with_client"]:
        _not_found("vault file")
    store.record_event(_actor(), "vault_download", household_id,
                       {"id": str(file_id), "name": record["name"]})
    safe_name = record["name"].replace('"', "")
    return Response(content, mimetype=record["mime"],
                    headers={"Content-Disposition": f'attachment; filename="{safe_name}"'})


@bp.patch("/households/<uuid:household_id>/vault/files/<uuid:file_id>")
def share_vault_file(household_id: UUID, file_id: UUID):
    body = _validate(VaultShareBody, _json_body())
    try:
        record = vault_service.set_shared(household_id, file_id, body.shared_with_client)
    except KeyError:
        _not_found("vault file")
    store.record_event(_actor(), "vault_share", household_id,
                       {"id": str(file_id), "shared_with_client": body.shared_with_client})
    return jsonify(record)


@bp.delete("/households/<uuid:household_id>/vault/files/<uuid:file_id>")
def delete_vault_file(household_id: UUID, file_id: UUID):
    try:
        vault_service.delete(household_id, file_id)
    except KeyError:
        _not_found("vault file")
    store.record_event(_actor(), "vault_delete", household_id, {"id": str(file_id)})
    return "", 204


# ---------------------------------------------------------------------------
# Portal collections (budgets, alerts, tasks, organizer change requests)
# ---------------------------------------------------------------------------
def _portal_list(household_id: UUID, kind: str):
    try:
        rows = store.list_portal(household_id, kind)
    except KeyError:
        _not_found("household")
    return jsonify({kind: rows})


@bp.get("/households/<uuid:household_id>/budgets")
def list_budgets(household_id: UUID):
    return _portal_list(household_id, "budgets")


@bp.post("/households/<uuid:household_id>/budgets")
def create_budget(household_id: UUID):
    body = _validate(PortalRecordBody, _json_body())
    return jsonify(store.create_portal(household_id, "budgets", body.payload, _actor())), 201


@bp.patch("/households/<uuid:household_id>/budgets/<uuid:record_id>")
def update_budget(household_id: UUID, record_id: UUID):
    body = _validate(PortalRecordBody, _json_body())
    try:
        record = store.update_portal(record_id, body.payload, _actor(), household_id)
    except KeyError:
        _not_found("budget")
    return jsonify(record)


@bp.get("/households/<uuid:household_id>/alerts")
def list_alerts(household_id: UUID):
    return _portal_list(household_id, "alerts")


@bp.post("/households/<uuid:household_id>/alerts")
def create_alert(household_id: UUID):
    body = _validate(PortalRecordBody, _json_body())
    return jsonify(store.create_portal(household_id, "alerts", body.payload, _actor())), 201


@bp.patch("/households/<uuid:household_id>/alerts/<uuid:record_id>")
def update_alert(household_id: UUID, record_id: UUID):
    body = _validate(PortalRecordBody, _json_body())
    try:
        record = store.update_portal(record_id, body.payload, _actor(), household_id)
    except KeyError:
        _not_found("alert")
    return jsonify(record)


@bp.get("/households/<uuid:household_id>/tasks")
def list_tasks(household_id: UUID):
    return _portal_list(household_id, "tasks")


@bp.post("/households/<uuid:household_id>/tasks")
def create_task(household_id: UUID):
    body = _validate(PortalRecordBody, _json_body())
    return jsonify(store.create_portal(household_id, "tasks", body.payload, _actor())), 201


@bp.patch("/households/<uuid:household_id>/tasks/<uuid:record_id>")
def update_task(household_id: UUID, record_id: UUID):
    body = _validate(PortalRecordBody, _json_body())
    try:
        record = store.update_portal(record_id, body.payload, _actor(), household_id)
    except KeyError:
        _not_found("task")
    return jsonify(record)


@bp.get("/households/<uuid:household_id>/organizer-change-requests")
def list_organizer_changes(household_id: UUID):
    return _portal_list(household_id, "organizer_change_requests")


@bp.post("/households/<uuid:household_id>/organizer-change-requests")
def create_organizer_change(household_id: UUID):
    body = _validate(PortalRecordBody, _json_body())
    payload = dict(body.payload)
    payload.setdefault("status", "pending_advisor_review")
    return jsonify(store.create_portal(household_id, "organizer_change_requests", payload, _actor())), 201


@bp.get("/advisor/feed")
def advisor_feed():
    if _is_client():
        raise ApiError(404, "resource not found")
    events = []
    for household in store.list_households():
        household_id = UUID(household["id"])
        try:
            _authorize_household(household_id)
        except ApiError:
            continue
        for kind in ("alerts", "tasks", "organizer_change_requests"):
            for row in store.list_portal(household_id, kind):
                events.append({**row, "household_name": household["name"]})
    events.sort(key=lambda row: row["updated_at"], reverse=True)
    return jsonify(events=events)


# ---------------------------------------------------------------------------
# Facts editing + versioning
# ---------------------------------------------------------------------------
@bp.patch("/households/<uuid:household_id>/facts")
def patch_facts(household_id: UUID):
    body = _validate(PatchBody, _json_body())
    try:
        _reject_warehouse_asset_patch(store.get_facts(household_id), body.ops)
        return jsonify(store.patch_facts(household_id, body.ops, _actor()).model_dump(mode="json"))
    except KeyError:
        _not_found("household")
    except (ValueError, IndexError, TypeError) as exc:
        raise ApiError(422, str(exc)) from exc


@bp.post("/households/<uuid:household_id>/facts/commit")
def commit_facts(household_id: UUID):
    try:
        version = store.commit(household_id, _actor())
    except KeyError:
        _not_found("household")
    return jsonify(facts_version_id=str(version),
                   committed_at=datetime.now(timezone.utc).isoformat()), 201


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------
@bp.get("/households/<uuid:household_id>/scenarios")
def list_scenarios(household_id: UUID):
    try:
        store.get_facts(household_id)
    except KeyError:
        _not_found("household")
    return jsonify(scenarios=[_scenario_dict(x) for x in store.scenarios_for(household_id)])


@bp.post("/households/<uuid:household_id>/scenarios")
def create_scenario(household_id: UUID):
    body = _validate(ScenarioCreateBody, _json_body())
    try:
        return jsonify(_scenario_dict(store.create_scenario(household_id, body.name, _actor()))), 201
    except KeyError:
        _not_found("household")
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc


@bp.post("/scenarios/<uuid:scenario_id>/promote")
def promote_scenario(scenario_id: UUID):
    try:
        return jsonify(_scenario_dict(store.promote_scenario(scenario_id, _actor())))
    except KeyError:
        _not_found("scenario")


@bp.patch("/scenarios/<uuid:scenario_id>/overrides")
def patch_overrides(scenario_id: UUID):
    body = _validate(OverrideBody, _json_body())
    try:
        return jsonify(_scenario_dict(store.patch_scenario(scenario_id, body.overrides, _actor())))
    except KeyError:
        _not_found("scenario")
    except (ValueError, IndexError, TypeError) as exc:
        code = 409 if "immutable" in str(exc).lower() else 422
        raise ApiError(code, str(exc)) from exc


@bp.post("/scenarios/<uuid:scenario_id>/project")
def project(scenario_id: UUID):
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    return jsonify(projection_service.project(facts, _qbool("tracing")).model_dump(mode="json"))


@bp.get("/scenarios/<uuid:scenario_id>/goals")
def scenario_goals(scenario_id: UUID):
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    projection = projection_service.project(facts)
    return jsonify(goals=evaluate_goals(facts, projection))


@bp.post("/scenarios/<uuid:scenario_id>/stress/<kind>")
def stress(scenario_id: UUID, kind: str):
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    base = projection_service.project(facts)
    changes = {
        "crash": {base.start_year: Decimal("-0.30")},
        "low_return": {row.year: Decimal("0.01") for row in base.rows},
        "inflation": None,
        "longevity": None,
    }
    if kind not in changes:
        raise ApiError(422, "unsupported stress kind")
    if kind == "inflation":
        facts.assumptions.inflation_rate += Decimal("0.02")
    if kind == "longevity":
        for person in facts.people:
            person.assumed_age_of_death = max(person.assumed_age_of_death, 105)
    projection = run_projection(facts, return_path=changes[kind])
    return jsonify(kind=kind, projection=projection.model_dump(mode="json"),
                   delta_ending_net_worth=str(projection.ending_net_worth - base.ending_net_worth))


@bp.post("/scenarios/<uuid:scenario_id>/solve")
def solve(scenario_id: UUID):
    body = _json_body()
    lever = body.get("lever", "monthly_savings")
    if lever != "monthly_savings":
        raise ApiError(422, "supported lever: monthly_savings")
    if "target" not in body:
        raise ApiError(422, "target is required")
    target = _decimal(body["target"], "target")
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    result = solve_monthly_savings(facts, target)
    return jsonify(lever=result.lever, value=str(result.value), target=str(result.target),
                   iterations=result.iterations, achieved=result.achieved)


@bp.post("/scenarios/<uuid:scenario_id>/roth-conversion")
def roth_conversion(scenario_id: UUID):
    body = _json_body()
    window_years = body.get("window_years")
    if window_years is not None:
        try:
            window_years = int(window_years)
        except (TypeError, ValueError):
            raise ApiError(422, "window_years must be an integer")
        if not 1 <= window_years <= 30:
            raise ApiError(422, "window_years must be between 1 and 30")
    heir_tax_rate = _decimal(body.get("heir_tax_rate", "0.24"), "heir_tax_rate")
    if not Decimal("0") <= heir_tax_rate <= Decimal("0.60"):
        raise ApiError(422, "heir_tax_rate must be between 0 and 0.60")
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    analysis = analyze_roth_conversions(facts, window_years=window_years,
                                        heir_tax_rate=heir_tax_rate)
    return jsonify(analysis.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Plan publication (spec 28 — immutable approved-plan snapshots for the mart)
# ---------------------------------------------------------------------------
@bp.post("/scenarios/<uuid:scenario_id>/publish")
def publish_plan(scenario_id: UUID):
    if _is_client():
        raise ApiError(404, "resource not found")
    body = _json_body()
    advisor_note = body.get("advisor_note")
    if advisor_note is not None and len(str(advisor_note)) > 2000:
        raise ApiError(422, "advisor_note must be at most 2000 characters")
    idempotency_key = body.get("idempotency_key")
    if idempotency_key is not None and not (1 <= len(str(idempotency_key)) <= 128):
        raise ApiError(422, "idempotency_key must be 1-128 characters")
    try:
        record = store.get_scenario(scenario_id)
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    projection = projection_service.project(facts)
    publication, created = publication_registry.publish(
        facts=facts, facts_version_id=str(record.base_facts_version_id),
        scenario_id=scenario_id, scenario_name=record.name,
        overrides=record.overrides, projection=projection, actor=_actor(),
        firm_id=_firm_id(), advisor_note=str(advisor_note) if advisor_note else None,
        idempotency_key=str(idempotency_key) if idempotency_key else None)
    store.record_event(_actor(), "plan_publish", record.household_id,
                       {"publication_id": str(publication.publication_id),
                        "scenario_id": str(scenario_id), "created": created,
                        "input_hash": publication.input_hash})
    return jsonify(publication.to_dict()), (201 if created else 200)


@bp.get("/households/<uuid:household_id>/publications")
def list_publications(household_id: UUID):
    return jsonify(publications=[record.to_dict() for record
                                 in publication_registry.for_household(household_id)])


@bp.post("/publications/<uuid:publication_id>/withdraw")
def withdraw_publication(publication_id: UUID):
    if _is_client():
        raise ApiError(404, "resource not found")
    try:
        record = publication_registry.get(publication_id)
        _authorize_household(record.household_id)
        record = publication_registry.withdraw(
            publication_id, _actor(), _json_body().get("reason"))
    except KeyError:
        _not_found("publication")
    store.record_event(_actor(), "plan_withdraw", record.household_id,
                       {"publication_id": str(publication_id)})
    return jsonify(record.to_dict())


# ---------------------------------------------------------------------------
# Lifecycle advice (deterministic Idzorek-Kaplan model)
# ---------------------------------------------------------------------------
def _lifecycle_params(scenario_id: UUID, base: InvestorParams | None) -> InvestorParams:
    if base is not None:
        return base
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    return investor_params_from_facts(facts)


@bp.post("/scenarios/<uuid:scenario_id>/lifecycle-plan")
def lifecycle_plan(scenario_id: UUID):
    body = _json_body()
    base = _validate(InvestorParams, body) if body else None
    params = _lifecycle_params(scenario_id, base)
    return jsonify(run_lifecycle_plan(params))


@bp.post("/scenarios/<uuid:scenario_id>/lifecycle-plan/sensitivity")
def lifecycle_sensitivity(scenario_id: UUID):
    payload = _validate(SensitivityRequest, _json_body())
    base = _lifecycle_params(scenario_id, payload.base)
    if payload.param not in InvestorParams.model_fields:
        raise ApiError(422, f"unsupported lifecycle parameter: {payload.param}")
    results = []
    for value in payload.values:
        params = base.model_copy(update={payload.param: value})
        results.append({"param": payload.param, "value": value,
                        "result": run_lifecycle_plan(params)})
    return jsonify(base=base.model_dump(mode="json"), results=results)


# ---------------------------------------------------------------------------
# Estate
# ---------------------------------------------------------------------------
def _estate_flow(scenario_id: UUID) -> dict:
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    death_order = request.args.get("death_order", "client_first")
    flow = build_estate_flow(facts, death_order)
    return {key: str(value) if isinstance(value, Decimal) else value
            for key, value in flow.__dict__.items()}


@bp.post("/scenarios/<uuid:scenario_id>/estate-flow")
def estate_flow(scenario_id: UUID):
    return jsonify(_estate_flow(scenario_id))


@bp.get("/scenarios/<uuid:scenario_id>/estate-liquidity")
def estate_liquidity(scenario_id: UUID):
    return jsonify(_estate_flow(scenario_id))


@bp.get("/scenarios/<uuid:scenario_id>/estate-tax-projection")
def estate_tax_projection(scenario_id: UUID):
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    projection = run_projection(facts)
    from planengine.estate import estate_tax
    return jsonify(years=[{"year": row.year, "gross_estate": str(row.estate_value),
                           "federal_estate_tax": str(estate_tax(row.estate_value))}
                          for row in projection.rows])


# ---------------------------------------------------------------------------
# Standalone tools
# ---------------------------------------------------------------------------
@bp.post("/tools/social-security-optimizer")
def social_security_optimizer():
    body = _json_body()
    client_pia = _decimal(request.args.get("client_pia", body.get("client_pia")), "client_pia")
    spouse_pia = _decimal(request.args.get("spouse_pia", body.get("spouse_pia")), "spouse_pia")
    result = optimize_social_security(client_pia, spouse_pia)
    return jsonify(client_claim_age=result.client_claim_age,
                   spouse_claim_age=result.spouse_claim_age,
                   expected_lifetime_benefit=str(result.expected_lifetime_benefit))


@bp.post("/tools/inherited-ira")
def inherited_ira():
    body = _json_body()
    balance = _decimal(request.args.get("balance", body.get("balance")), "balance")
    return jsonify({key: [str(x) for x in values]
                    for key, values in inherited_ira_schedules(balance).items()})


@bp.post("/tools/nua")
def nua():
    body = _json_body()
    cost_basis = _decimal(request.args.get("cost_basis", body.get("cost_basis")), "cost_basis")
    market_value = _decimal(request.args.get("market_value", body.get("market_value")), "market_value")
    ordinary_rate = _decimal(request.args.get("ordinary_rate", body.get("ordinary_rate")), "ordinary_rate")
    ltcg_rate = _decimal(request.args.get("ltcg_rate", body.get("ltcg_rate")), "ltcg_rate")
    result = analyze_nua(cost_basis, market_value, ordinary_rate, ltcg_rate)
    return jsonify({key: str(value) for key, value in result.__dict__.items()})


# ---------------------------------------------------------------------------
# Background jobs (Monte Carlo + privacy delete) — Flask threads replace
# FastAPI BackgroundTasks.
# ---------------------------------------------------------------------------
_jobs: dict[UUID, dict] = {}
_jobs_lock = Lock()


def _run_mc_job(job_id: UUID, scenario_id: UUID, trials: int, seed: int, input_snapshot: dict):
    with _jobs_lock:
        _jobs[job_id].update(status="running", progress=5)
    try:
        facts = store.scenario_facts(scenario_id)
        cma, corr = monte_carlo_parameters(input_snapshot)
        result = run_monte_carlo(facts, n_trials=trials, seed=seed, cma=cma,
                                 corr=corr, input_snapshot=input_snapshot)
        with _jobs_lock:
            _jobs[job_id].update(status="succeeded", progress=100,
                                 result=result.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001 - surfaced to the job record
        with _jobs_lock:
            _jobs[job_id].update(status="failed", error=str(exc))


def _run_delete_job(job_id: UUID, household_id: UUID, actor: str, reason: str):
    with _jobs_lock:
        _jobs[job_id].update(status="running", progress=10)
    try:
        vault_count = vault_service.purge(household_id)
        publication_count = publication_registry.purge_household(household_id)
        counts = store.delete_household(household_id, actor, reason)
        projection_service.clear()
        purge_report = {
            "facts": {"deleted": counts["facts"], "remaining": 0},
            "facts_versions": {"deleted": counts["facts_versions"], "remaining": 0},
            "scenarios": {"deleted": counts["scenarios"], "remaining": 0},
            "portal_records": {"deleted": counts["portal_records"], "remaining": 0},
            "projections_blob_store": {"deleted": "cache_purged", "remaining": 0},
            "vault": {"deleted": vault_count, "remaining": 0},
            "publications": {"deleted": publication_count, "remaining": 0},
            "external_transactions": {"deleted": 0, "remaining": 0},
            "llm_traces": {"deleted": 0, "remaining": 0},
        }
        with _jobs_lock:
            _jobs[job_id].update(status="succeeded", progress=100,
                                 result={"purge_report": purge_report})
    except Exception as exc:  # noqa: BLE001 - surfaced to the job record
        with _jobs_lock:
            _jobs[job_id].update(status="failed", error=str(exc))


def _spawn(target, *args) -> None:
    Thread(target=target, args=args, daemon=True).start()


@bp.post("/households/<uuid:household_id>/delete")
def delete_household(household_id: UUID):
    body = _validate(DeleteBody, _json_body())
    if body.confirmation != "DELETE":
        raise ApiError(422, "confirmation must be DELETE")
    job_id = uuid4()
    with _jobs_lock:
        _jobs[job_id] = {"id": str(job_id), "status": "queued", "progress": 0,
                         "household_id": str(household_id), "kind": "privacy_delete",
                         "actor": _actor(), "firm_id": _firm_id()}
    _spawn(_run_delete_job, job_id, household_id, _actor(), body.reason)
    return jsonify(job_id=str(job_id), status="queued"), 202


@bp.post("/scenarios/<uuid:scenario_id>/monte-carlo")
def monte_carlo(scenario_id: UUID):
    body = _validate(MonteCarloBody, _json_body())
    try:
        record = store.get_scenario(scenario_id)
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    session = None
    try:
        if body.refresh_synapse_inputs and facts.metadata.get("source_id"):
            session = get_session_factory()()
        inputs = resolve_monte_carlo_inputs(session, facts)
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        inputs = resolve_monte_carlo_inputs(None, facts)
        inputs["warnings"].append(
            f"Live Synapse refresh unavailable; using versioned input snapshot ({type(exc).__name__})")
    finally:
        if session is not None:
            session.close()
    if not inputs["ready"]:
        raise ApiError(422, {
            "message": "Monte Carlo inputs are incomplete",
            "missing_required_inputs": inputs["missing_required_inputs"],
            "warnings": inputs["warnings"],
        })
    job_id = uuid4()
    with _jobs_lock:
        _jobs[job_id] = {"id": str(job_id), "status": "queued", "progress": 0,
                         "household_id": str(record.household_id), "actor": _actor(),
                         "firm_id": _firm_id(), "kind": "monte_carlo"}
    _spawn(_run_mc_job, job_id, scenario_id, body.trials, body.seed, inputs)
    return jsonify(job_id=str(job_id), status="queued"), 202


@bp.get("/scenarios/<uuid:scenario_id>/monte-carlo/inputs")
def monte_carlo_inputs(scenario_id: UUID):
    try:
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    session = None
    try:
        if _qbool("refresh_synapse", True) and facts.metadata.get("source_id"):
            session = get_session_factory()()
        return jsonify(resolve_monte_carlo_inputs(session, facts))
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        result = resolve_monte_carlo_inputs(None, facts)
        result["warnings"].append(f"Live Synapse refresh unavailable ({type(exc).__name__})")
        return jsonify(result)
    finally:
        if session is not None:
            session.close()


@bp.get("/jobs/<uuid:job_id>")
def job(job_id: UUID):
    with _jobs_lock:
        result = deepcopy(_jobs.get(job_id))
    if result is None:
        _not_found("job")
    return jsonify(result)


@bp.post("/households/<uuid:household_id>/compare")
def compare(household_id: UUID):
    payload = request.get_json(silent=True)
    scenario_ids = payload if isinstance(payload, list) else (payload or {}).get("scenario_ids", [])
    projections = []
    for raw_id in scenario_ids:
        try:
            scenario_id = UUID(str(raw_id))
        except ValueError:
            _not_found("scenario")
        try:
            record = store.get_scenario(scenario_id)
            if record.household_id != household_id:
                _not_found("scenario")
            projection = projection_service.project(store.scenario_facts(scenario_id))
        except KeyError:
            _not_found("scenario")
        projections.append({"scenario_id": str(scenario_id), "name": record.name,
                            "ending_net_worth": str(projection.ending_net_worth),
                            "lifetime_taxes": str(projection.lifetime_taxes),
                            "first_shortfall_year": projection.first_shortfall_year,
                            "series": [{"year": x.year, "net_worth": str(x.net_worth)} for x in projection.rows]})
    return jsonify(household_id=str(household_id), scenarios=projections)


# ---------------------------------------------------------------------------
# Warehouse + capital market assumptions + reports
# ---------------------------------------------------------------------------
@bp.get("/warehouse/contract")
def datawarehouse_contract():
    return jsonify(warehouse_contract())


@bp.get("/capital-market-assumptions")
def capital_market_assumptions():
    session = None
    try:
        if _qbool("refresh_synapse", True):
            session = get_session_factory()()
        return jsonify(resolve_capital_market_assumptions(session))
    except (SQLAlchemyError, RuntimeError, ValueError) as exc:
        result = resolve_capital_market_assumptions(None)
        result["warnings"].append(f"Live Synapse CMA refresh unavailable ({type(exc).__name__})")
        return jsonify(result)
    finally:
        if session is not None:
            session.close()


@bp.get("/report-definitions")
def report_definitions():
    return jsonify(definitions=[{"id": i + 1, "name": name}
                                for i, name in enumerate(_REPORT_NAMES)])


_REPORT_NAMES = ["Balance Sheet / Net Worth", "Cash Flow Report", "Cash Flow Chart",
                 "Total Portfolio Assets", "Monte Carlo Report", "Retirement Analysis",
                 "Social Security Comparison", "Tax Report", "Roth Conversion Analysis",
                 "Education Funding", "Life Insurance Needs", "Disability / LTC Analysis",
                 "Estate Flowchart", "Estate & Gift Tax Projection", "Estate Liquidity",
                 "Asset Allocation", "Beneficiary Review", "What-If Comparison",
                 "Annual Review Package", "Client Snapshot"]


@bp.get("/scenarios/<uuid:scenario_id>/reports/<int:definition_id>")
def render_planning_report(scenario_id: UUID, definition_id: int):
    definition = next(({"id": i + 1, "name": name} for i, name in enumerate(_REPORT_NAMES)
                       if i + 1 == definition_id), None)
    if definition is None:
        _not_found("report definition")
    try:
        record = store.get_scenario(scenario_id)
        facts = store.scenario_facts(scenario_id)
    except KeyError:
        _not_found("scenario")
    html = render_report(facts, projection_service.project(facts), definition["name"], record.name)
    store.create_portal(record.household_id, "report_runs", {
        "definition_id": definition["id"], "definition_name": definition["name"],
        "scenario_id": str(scenario_id), "scenario_name": record.name,
    }, _actor())
    return Response(html, mimetype="text/html")


@bp.get("/households/<uuid:household_id>/report-history")
def report_history(household_id: UUID):
    try:
        rows = store.list_portal(household_id, "report_runs")
    except KeyError:
        _not_found("household")
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return jsonify(runs=rows)


@bp.post("/warehouse/households/<path:source_household_id>/import")
def import_from_warehouse(source_household_id: str):
    identifier = source_household_id.strip()
    is_salesforce_id = bool(re.fullmatch(r"[A-Za-z0-9]{15}(?:[A-Za-z0-9]{3})?", identifier))
    is_exact_household_name = bool(
        3 <= len(identifier) <= 255 and re.fullmatch(r"[\w .,'&()\-/]+", identifier))
    if not is_salesforce_id and not is_exact_household_name:
        raise ApiError(422, "Enter a Salesforce household ID or exact household name")
    try:
        session = get_session_factory()()
    except (RuntimeError, ValueError) as exc:
        raise ApiError(503, str(exc)) from exc
    try:
        resolved_id = identifier if is_salesforce_id else resolve_household_id(session, identifier)
        facts = import_household(session, resolved_id)
        facts = _secured_facts(facts)
        created, scenarios = store.create_household(facts.model_dump(), _actor())
    except KeyError:
        _not_found("warehouse household")
    except AmbiguousHouseholdError as exc:
        raise ApiError(
            409,
            "More than one warehouse household has that exact name; import by Salesforce household ID",
        ) from exc
    except SQLAlchemyError as exc:
        raise ApiError(502, {
            "message": "Synapse could not complete the household import.",
            "hint": "Confirm the warehouse schema is current, then retry or use the Salesforce household ID.",
        }) from exc
    finally:
        session.close()
    return jsonify(household_id=str(created.household_id),
                   scenario_ids=[str(x.id) for x in scenarios],
                   provenance=created.metadata.get("provenance", {})), 201


@bp.post("/households/<uuid:household_id>/sync-actuals")
def sync_actuals(household_id: UUID):
    """Plan-vs-actual: re-pull warehouse values, report drift, optionally apply.

    Body: {"apply": bool} — when true, warehouse-owned assets/liabilities in the
    plan copy are replaced with fresh values (advisor planning inputs are kept).
    An off-track household gets a portal alert so it surfaces in the advisor feed.
    """
    if _is_client():
        raise ApiError(404, "resource not found")
    body = _json_body()
    apply_requested = bool(body.get("apply", False))
    try:
        plan_facts = store.get_facts(household_id)
    except KeyError:
        _not_found("household")
    source_id = plan_facts.metadata.get("source_id")
    if plan_facts.metadata.get("source") != "datawarehouse" or not source_id:
        raise ApiError(422, "Actuals sync requires a household imported from the data warehouse")
    try:
        session = get_session_factory()()
    except (RuntimeError, ValueError) as exc:
        raise ApiError(503, str(exc)) from exc
    try:
        fresh_facts = import_household(session, str(source_id))
    except KeyError:
        _not_found("warehouse household")
    except SQLAlchemyError as exc:
        raise ApiError(502, {
            "message": "Synapse could not refresh household actuals.",
            "hint": "Retry once the warehouse feeds are current.",
        }) from exc
    finally:
        session.close()
    diff = diff_accounts(plan_facts, fresh_facts)
    projection = projection_service.project(plan_facts)
    drift = drift_status(projection, Decimal(diff["actual_total"]),
                         datetime.now(timezone.utc).year)
    alert = None
    if drift["status"] == "behind":
        alert = store.create_portal(household_id, "alerts", {
            "kind": "plan_drift", "severity": "warning",
            "title": f"{plan_facts.name} is behind plan",
            "detail": (f"Actual portfolio {diff['actual_total']} vs projected "
                       f"{drift['projected_portfolio']} for {drift['year']} "
                       f"(tolerance {drift['tolerance']})"),
        }, _actor())
    applied = False
    if apply_requested:
        synced_at = datetime.now(timezone.utc).isoformat()
        updated = apply_actuals(plan_facts, fresh_facts, synced_at=synced_at)
        store.replace_facts(household_id, _secured_facts(updated), _actor(),
                            action="sync_actuals")
        applied = True
    store.record_event(_actor(), "sync_actuals", household_id,
                       {"applied": applied, "drift_status": drift["status"],
                        "total_delta": diff["total_delta"]})
    return jsonify(household_id=str(household_id), diff=diff, drift=drift,
                   applied=applied, alert=alert,
                   warnings=fresh_facts.metadata.get("data_quality_warnings", []))
