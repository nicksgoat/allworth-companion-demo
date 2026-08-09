"""Plan-vs-actual tracking over warehouse-sourced households.

Pure functions: the route layer supplies fresh warehouse facts and the stored
plan; everything here is deterministic diff/drift math so it can be tested
without Synapse.
"""

from __future__ import annotations

from decimal import Decimal

from planengine.models import Facts, Projection

D = Decimal
ZERO = D("0")
DEFAULT_TOLERANCE = D("0.05")


def _account_key(account) -> str:
    for attribute in ("source_id", "external_account_number", "account_number"):
        value = getattr(account, attribute, None)
        if value:
            return f"{attribute}:{value}"
    return f"name:{account.name}"


def diff_accounts(plan_facts: Facts, fresh_facts: Facts) -> dict:
    """Per-account and total deltas between the plan copy and fresh warehouse data."""
    plan = {_account_key(a): a for a in plan_facts.accounts if not a.exclude_from_planning}
    fresh = {_account_key(a): a for a in fresh_facts.accounts if not a.exclude_from_planning}
    matched, added, removed = [], [], []
    for key, account in fresh.items():
        if key in plan:
            before, after = D(plan[key].value), D(account.value)
            matched.append({"name": account.name, "kind": account.kind,
                            "plan_value": str(before), "actual_value": str(after),
                            "delta": str(after - before),
                            "delta_pct": str((after - before) / before) if before else None})
        else:
            added.append({"name": account.name, "kind": account.kind,
                          "actual_value": str(D(account.value))})
    for key, account in plan.items():
        if key not in fresh:
            removed.append({"name": account.name, "kind": account.kind,
                            "plan_value": str(D(account.value))})
    plan_total = sum((D(a.value) for a in plan.values()), ZERO)
    actual_total = sum((D(a.value) for a in fresh.values()), ZERO)
    return {"matched": matched, "added": added, "removed": removed,
            "plan_total": str(plan_total), "actual_total": str(actual_total),
            "total_delta": str(actual_total - plan_total)}


def drift_status(plan_projection: Projection, actual_total: Decimal, year: int,
                 tolerance: Decimal = DEFAULT_TOLERANCE) -> dict:
    """Place actual portfolio value against the plan's projected trajectory."""
    row = next((r for r in plan_projection.rows if r.year == year),
               plan_projection.rows[0] if plan_projection.rows else None)
    if row is None:
        return {"status": "unknown", "reason": "plan projection has no rows"}
    projected = sum(row.account_balances.values(), ZERO)
    if projected <= 0:
        return {"status": "unknown", "reason": "plan projects no portfolio value this year"}
    actual = D(actual_total)
    ratio = actual / projected
    if ratio >= 1 + tolerance:
        status = "ahead"
    elif ratio <= 1 - tolerance:
        status = "behind"
    else:
        status = "on_track"
    return {"status": status, "year": row.year,
            "projected_portfolio": str(projected), "actual_portfolio": str(actual),
            "ratio": str(ratio), "tolerance": str(tolerance)}


def apply_actuals(plan_facts: Facts, fresh_facts: Facts,
                  synced_at: str | None = None) -> Facts:
    """Return plan facts with warehouse-owned sections replaced by fresh data.

    Advisor-owned planning inputs (income, expenses, goals, assumptions,
    insurance, transfers) are preserved; only Synapse-sourced assets and
    liabilities move.
    """
    updated = plan_facts.model_copy(deep=True)
    updated.accounts = [a.model_copy(deep=True) for a in fresh_facts.accounts]
    updated.real_estate = [a.model_copy(deep=True) for a in fresh_facts.real_estate]
    updated.liabilities = [x.model_copy(deep=True) for x in fresh_facts.liabilities]
    metadata = dict(updated.metadata)
    fresh_meta = fresh_facts.metadata
    for key in ("provenance", "data_quality_warnings", "monte_carlo_inputs",
                "household_avhhid", "advisor_id", "crm_lead_id"):
        if key in fresh_meta:
            metadata[key] = fresh_meta[key]
    if synced_at:
        metadata["last_actuals_sync"] = synced_at
    updated.metadata = metadata
    return updated
