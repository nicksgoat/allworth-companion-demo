"""Deterministic synthetic seed data and aggregate queries over it."""

import json
from calendar import monthrange
from collections import defaultdict

from allworth_api.config import DATA_DIR
from allworth_api.core.formatting import js_round

seed = json.loads((DATA_DIR / "seed.json").read_text())


def accounts_for() -> dict:
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


def spending_summary(months: int = 3) -> dict:
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
    """Build mock performance cash flows from the seed files.

    Positive amounts are inflows and negative amounts are outflows. For the
    demo performance view, cash flows mean portfolio contributions and
    distributions, not household spending. The seed transactions only contain
    recent transfer rows, so earlier months use the recurring portfolio income
    assumption from the plan.
    """
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


def portfolio_for() -> dict:
    by_account: dict[str, list] = {}
    positions = []
    for p in seed["positions"]:
        position = dict(p)
        positions.append(position)
        by_account.setdefault(position["accountId"], []).append(position)
    return {"positions": positions, "byAccount": by_account}
