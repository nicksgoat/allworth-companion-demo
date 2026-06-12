"""Household data layer — resolves client data from Synapse or seed fallback.

When a household_id is a numeric Synapse AVHHID and Synapse is available,
queries live data. Otherwise falls back to the static seed data (demo mode).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from allworth_api.data import synapse
from allworth_api.data.seed import accounts_for as seed_accounts_for
from allworth_api.data.seed import portfolio_for as seed_portfolio_for
from allworth_api.data.seed import seed
from allworth_api.data.seed import spending_summary as seed_spending_summary

logger = logging.getLogger(__name__)

# Demo household IDs that should always use seed data
_DEMO_IDS = {"maya", "hh_castillo", "hh_raman"}

# Thread pool for parallel Synapse queries
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="synapse")


def _is_synapse_household(household_id: str) -> bool:
    """Check if this household should be resolved from Synapse (numeric AVHHID)."""
    return household_id not in _DEMO_IDS and household_id.isdigit() and synapse.is_available()


# ── Client persona ────────────────────────────────────────────────────────


def get_client_persona(household_id: str) -> dict[str, Any] | None:
    """Build a ClientPersona-shaped dict for the household."""
    if not _is_synapse_household(household_id):
        return next((c for c in seed["personas"]["clients"] if c["id"] == household_id), None)

    try:
        hh_id = int(household_id)
        hh = synapse.resolve_household(household_id=hh_id)
        if not hh:
            return None

        members = synapse.get_household_members(hh_id)
        primary = next((m for m in members if m.get("role") == "Primary"), None)
        name = hh.get("household_name") or f"Household {household_id}"
        # Strip common suffixes like "Doe, John and Jane" → keep as-is

        initials = "".join(w[0].upper() for w in name.split()[:2] if w) or "??"

        return {
            "id": household_id,
            "name": name,
            "age": _calc_age(primary.get("date_of_birth")) if primary else None,
            "city": "",
            "advisorId": "dana",
            "bio": "",
            "avatarInitials": initials,
        }
    except Exception as e:
        logger.warning(f"Failed to build persona for {household_id}: {e}")
        return None


def _calc_age(dob: Any) -> int | None:
    """Calculate age from a date-of-birth value."""
    if not dob:
        return None
    from datetime import date, datetime

    if isinstance(dob, datetime):
        dob = dob.date()
    elif isinstance(dob, str):
        try:
            dob = datetime.strptime(dob[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    if not isinstance(dob, date):
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ── Accounts ──────────────────────────────────────────────────────────────


def get_accounts(household_id: str) -> dict[str, Any]:
    """Return accounts summary shaped for the dashboard."""
    if not _is_synapse_household(household_id):
        return seed_accounts_for()

    try:
        hh_id = int(household_id)
        raw = synapse.get_accounts(hh_id)
        if not raw:
            return seed_accounts_for()

        allworth = []
        outside = []

        for acct in raw:
            category = (acct.get("account_category") or "").lower()
            acct_type = (acct.get("account_type") or "").lower()
            custodian = (acct.get("custodian") or "").lower()
            balance = acct.get("balance", 0) or 0

            # Allworth-managed = advisory accounts at known custodians
            is_allworth = "advisory" in acct_type or custodian in ("schwab", "fidelity")

            entry = {
                "id": str(acct.get("account_id", "")),
                "name": acct.get("account_name", f"Account {acct.get('account_id')}"),
                "institution": _infer_institution(custodian, acct.get("model_name")),
                "group": "allworth" if is_allworth else "outside",
                "type": _map_account_type(acct_type),
                "balance": round(balance),
            }

            if entry["group"] == "allworth":
                allworth.append(entry)
            else:
                outside.append(entry)

        allworth_total = sum(a["balance"] for a in allworth)
        outside_assets = sum(a["balance"] for a in outside if a["type"] != "liability")
        liabilities = sum(a["balance"] for a in outside if a["type"] == "liability")
        net_worth = allworth_total + outside_assets + liabilities

        return {
            "allworth": allworth,
            "outside": outside,
            "allworthTotal": allworth_total,
            "heldAwayTotal": outside_assets,
            "liabilitiesTotal": liabilities,
            "netWorth": net_worth,
        }
    except Exception as e:
        logger.warning(f"Synapse accounts failed for {household_id}: {e}")
        return seed_accounts_for()


def _infer_institution(custodian: str, model_name: str | None) -> str:
    """Best-effort institution name from custodian."""
    if "schwab" in custodian:
        return "Allworth (Schwab)"
    if "fidelity" in custodian:
        return "Allworth (Fidelity)"
    if "vanguard" in custodian:
        return "Vanguard"
    if custodian:
        return custodian.title()
    if model_name:
        return model_name
    return "Unknown"


def _map_account_type(raw_type: str) -> str:
    """Map Synapse account types to our simplified type enum."""
    raw = raw_type.lower()
    if "ira" in raw and "roth" in raw:
        return "roth"
    if "ira" in raw:
        return "ira"
    if "401" in raw:
        return "401k"
    if "trust" in raw:
        return "taxable"
    if "cash" in raw or "check" in raw or "saving" in raw or "money market" in raw:
        return "cash"
    if "mortgage" in raw or "loan" in raw or "liability" in raw:
        return "liability"
    return "taxable"


# ── Net worth history ─────────────────────────────────────────────────────


def get_net_worth_history(household_id: str) -> list[dict[str, Any]]:
    """Return monthly net worth history for the dashboard chart."""
    if not _is_synapse_household(household_id):
        return seed["netWorthHistory"]

    try:
        hh_id = int(household_id)
        raw = synapse.get_net_worth_history(hh_id)
        if not raw:
            return seed["netWorthHistory"]

        # Deduplicate by month — keep the latest period_key per month
        by_month: dict[str, int] = {}
        for r in raw:
            pk = str(r.get("period_key", ""))
            nw = r.get("net_worth")
            if nw is None or nw == 0:
                continue
            month = f"{pk[:4]}-{pk[4:6]}" if len(pk) >= 6 else pk
            by_month[month] = round(nw)  # later entries overwrite earlier

        result = [{"month": m, "value": v} for m, v in by_month.items()]
        result = result[-12:]  # last 12 months
        return result if result else seed["netWorthHistory"]
    except Exception as e:
        logger.warning(f"Synapse net worth history failed for {household_id}: {e}")
        return seed["netWorthHistory"]


# ── Portfolio / positions ─────────────────────────────────────────────────


def get_portfolio(household_id: str) -> dict[str, Any]:
    """Return portfolio data (positions by account)."""
    if not _is_synapse_household(household_id):
        return seed_portfolio_for()

    try:
        hh_id = int(household_id)
        raw = synapse.get_holdings(hh_id)
        if not raw:
            return seed_portfolio_for()

        positions = []
        by_account: dict[str, list] = {}

        for h in raw:
            acct_id = str(h.get("account_id", ""))
            asset_class = _map_asset_class(h.get("asset_class", "Unclassified"))
            mv = h.get("market_value", 0) or 0
            pos = {
                "accountId": acct_id,
                "symbol": asset_class.upper()[:4],
                "name": h.get("asset_class", "Unclassified"),
                "qty": 1,
                "price": round(mv),
                "value": round(mv),
                "assetClass": asset_class,
            }
            positions.append(pos)
            by_account.setdefault(acct_id, []).append(pos)

        return {"positions": positions, "byAccount": by_account, "taxLots": []}
    except Exception as e:
        logger.warning(f"Synapse portfolio failed for {household_id}: {e}")
        return seed_portfolio_for()


def _map_asset_class(raw: str) -> str:
    """Map Synapse asset class to the frontend's enum."""
    lower = raw.lower()
    if "equity" in lower and ("intl" in lower or "international" in lower or "foreign" in lower):
        return "intl_equity"
    if "equity" in lower or "stock" in lower:
        return "us_equity"
    if "muni" in lower:
        return "muni_bond"
    if "bond" in lower or "fixed" in lower:
        return "bond"
    if "cash" in lower or "money" in lower:
        return "cash"
    return "us_equity"


# ── Spending ──────────────────────────────────────────────────────────────


def get_spending(household_id: str, months: int = 3) -> dict[str, Any]:
    """Return spending summary. Currently only available from seed data."""
    if not _is_synapse_household(household_id):
        return seed_spending_summary(months)

    # Synapse rollforward has cash withdrawal / expenses data
    try:
        hh_id = int(household_id)
        raw = synapse.get_rollforward(hh_id, periods=max(months, 12))
        if not raw:
            return seed_spending_summary(months)

        monthly = []
        for r in raw:
            pk = str(r.get("period_key", ""))
            if len(pk) >= 6:
                month = f"{pk[:4]}-{pk[4:6]}"
            else:
                month = pk
            total = abs(r.get("cash_withdrawal", 0)) + abs(r.get("expenses", 0))
            monthly.append({"month": month, "total": round(total)})

        monthly.reverse()  # oldest first
        recent = monthly[-months:] if monthly else []
        if not recent:
            return seed_spending_summary(months)

        avg = sum(m["total"] for m in recent) / len(recent)
        # No plan data in Synapse — use a reasonable estimate
        plan = round(avg * 0.9)  # Assume plan is ~90% of actual

        return {
            "months": recent,
            "all": monthly,
            "avg3mo": round(avg),
            "plan": plan,
            "overPlanPct": round((avg - plan) / plan * 100) if plan > 0 else 0,
        }
    except Exception as e:
        logger.warning(f"Synapse spending failed for {household_id}: {e}")
        return seed_spending_summary(months)


# ── Parallel dashboard fetch ─────────────────────────────────────────────


def get_dashboard_data(household_id: str) -> dict[str, Any]:
    """Fetch all dashboard data in parallel for a household.

    Returns dict with keys: client, accounts, net_worth_history, spending.
    For Synapse households, runs all queries concurrently via thread pool.
    """
    if not _is_synapse_household(household_id):
        return {
            "client": next((c for c in seed["personas"]["clients"] if c["id"] == household_id), None),
            "accounts": seed_accounts_for(),
            "net_worth_history": seed["netWorthHistory"],
            "spending": seed_spending_summary(3),
        }

    import time as _time
    t0 = _time.time()

    futures = {
        "client": _executor.submit(get_client_persona, household_id),
        "accounts": _executor.submit(get_accounts, household_id),
        "net_worth_history": _executor.submit(get_net_worth_history, household_id),
        "spending": _executor.submit(get_spending, household_id, 3),
    }

    results = {}
    for key, future in futures.items():
        try:
            results[key] = future.result(timeout=60)
        except Exception as e:
            logger.warning(f"Parallel fetch failed for {key}: {e}")
            results[key] = None

    elapsed = round((_time.time() - t0) * 1000)
    logger.info(f"[synapse] dashboard data for {household_id} fetched in {elapsed}ms")

    # Apply fallbacks for any failed queries
    if results.get("accounts") is None:
        results["accounts"] = seed_accounts_for()
    if results.get("net_worth_history") is None:
        results["net_worth_history"] = seed["netWorthHistory"]
    if results.get("spending") is None:
        results["spending"] = seed_spending_summary(3)

    return results
