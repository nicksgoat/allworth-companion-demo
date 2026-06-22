"""Deterministic synthetic seed data and aggregate queries over it.

The demo serves multiple client personas (Maya, Kenny). Each client's data lives
in its own seed file. `current_seed()` returns the seed for the client bound to
the current request / chat turn via a context variable, so the data accessors
stay client-aware without threading client_id through every call. The binding is
set at three choke points: the `get_current_household` auth dependency (HTTP
routes), `run_tool` (chat + advisor tools), and `stream_chat`.
"""

import json
from calendar import monthrange
from collections import defaultdict
from contextvars import ContextVar

from allworth_api.config import DATA_DIR
from allworth_api.core.formatting import js_round

DEFAULT_CLIENT = "maya"
_SEED_FILES = {"maya": "seed.json", "kenny": "seed_kenny.json"}
_cache: dict[str, dict] = {}
_current_client: ContextVar[str] = ContextVar("current_client", default=DEFAULT_CLIENT)


def seed_for(client_id: str | None) -> dict:
    """The full seed dict for a client (cached). Unknown ids fall back to Maya."""
    cid = client_id if client_id in _SEED_FILES else DEFAULT_CLIENT
    cached = _cache.get(cid)
    if cached is None:
        cached = json.loads((DATA_DIR / _SEED_FILES[cid]).read_text())
        _cache[cid] = cached
    return cached


def set_current_client(client_id: str | None) -> None:
    """Bind the client whose seed `current_seed()` returns for this context."""
    _current_client.set(client_id if client_id in _SEED_FILES else DEFAULT_CLIENT)


def current_client() -> str:
    return _current_client.get()


def current_seed() -> dict:
    return seed_for(_current_client.get())


def all_client_personas() -> list[dict]:
    """Every client persona across all seeds (for email→client login lookup)."""
    out: list[dict] = []
    for cid in _SEED_FILES:
        out.extend(seed_for(cid)["personas"]["clients"])
    return out


def all_advisors() -> list[dict]:
    """Every advisor across all seeds, de-duplicated by id."""
    by_id: dict[str, dict] = {}
    for cid in _SEED_FILES:
        for a in seed_for(cid)["personas"]["advisors"]:
            by_id.setdefault(a["id"], a)
    return list(by_id.values())


def seed_for_advisor(advisor_id: str | None) -> dict:
    """The seed whose advisor roster includes this advisor (Maya's by default)."""
    for cid in _SEED_FILES:
        s = seed_for(cid)
        if any(a["id"] == advisor_id for a in s["personas"]["advisors"]):
            return s
    return seed_for(DEFAULT_CLIENT)


def advisor_for_client(client_id: str | None) -> dict:
    """The advisor record for a client (matched by advisorId, with a fallback)."""
    s = seed_for(client_id)
    advisors = s["personas"]["advisors"]
    client = next((c for c in s["personas"]["clients"] if c["id"] == client_id), None)
    if client:
        adv = next((a for a in advisors if a["id"] == client.get("advisorId")), None)
        if adv:
            return adv
    return advisors[0]


def _resolve(client_id: str | None) -> dict:
    return seed_for(client_id) if client_id else current_seed()


def accounts_for(client_id: str | None = None) -> dict:
    seed = _resolve(client_id)
    allworth = [a for a in seed["accounts"] if a["group"] == "allworth"]
    outside = [a for a in seed["accounts"] if a["group"] == "outside"]

    def total(xs):
        return sum(a["balance"] for a in xs)

    return {
        "allworth": allworth,
        "outside": outside,
        "allworthTotal": total(allworth),
        "heldAwayTotal": total([a for a in outside if a["type"] != "liability"]),
        "liabilitiesTotal": total([a for a in outside if a["type"] == "liability"]),
        "netWorth": total(seed["accounts"]),
    }


def spending_summary(months: int = 3, client_id: str | None = None) -> dict:
    seed = _resolve(client_id)
    recent = seed["spending"][-months:]
    avg = sum(m["total"] for m in recent) / len(recent)
    plan = seed["plan"]["spendingAssumptionMonthly"]
    return {
        "months": recent,
        "all": seed["spending"],
        "avg3mo": js_round(avg),
        "plan": plan,
        "overPlanPct": js_round((avg - plan) / plan * 100),
    }


def performance_cash_flows_for() -> list[dict]:
    """Build mock performance cash flows from the active client's seed.

    Positive amounts are inflows and negative amounts are outflows. For the
    demo performance view, cash flows mean portfolio contributions and
    distributions, not household spending. The seed transactions only contain
    recent transfer rows, so earlier months use the recurring portfolio income
    assumption from the plan.
    """
    seed = current_seed()
    months = [point["month"] for point in seed["netWorthHistory"]]
    flows_by_month: dict[str, float] = defaultdict(float)
    account_by_id = {account["id"]: account for account in seed["accounts"]}

    for tx in seed.get("transactions", []):
        if tx.get("category") != "Transfer":
            continue
        account = account_by_id.get(tx.get("accountId"), {})
        if account.get("group") != "allworth":
            continue
        amount = float(tx.get("amount", 0) or 0)
        merchant = str(tx.get("merchant", "")).lower()
        if "distribution" not in merchant and "allworth trust" not in merchant:
            continue
        flows_by_month[str(tx.get("date", ""))[:7]] += amount

    recurring_distribution = -float(seed["plan"].get("portfolioIncomeMonthly", 0) or 0)
    flows: list[dict] = []
    for month in months:
        amount = flows_by_month.get(month, recurring_distribution)
        if not amount:
            continue
        _, last_day = monthrange(int(month[:4]), int(month[5:7]))
        flows.append(
            {
                "date": f"{month}-{last_day:02d}",
                "amount": js_round(amount),
                "month": month,
                "source": "seed.transactions.transfer"
                if month in flows_by_month
                else "seed.plan.portfolioIncomeMonthly",
                "label": "Portfolio distribution" if amount < 0 else "Portfolio contribution",
            }
        )

    return flows


def portfolio_for(client_id: str | None = None) -> dict:
    seed = _resolve(client_id)
    by_account: dict[str, list] = {}
    positions = []
    for p in seed["positions"]:
        position = dict(p)
        positions.append(position)
        by_account.setdefault(position["accountId"], []).append(position)
    return {"positions": positions, "byAccount": by_account}
