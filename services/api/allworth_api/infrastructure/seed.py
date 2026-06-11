"""Deterministic synthetic seed data and aggregate queries over it."""

import json

from allworth_api.config import DATA_DIR
from allworth_api.domain.formatting import js_round

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


def portfolio_for() -> dict:
    by_account: dict[str, list] = {}
    for p in seed["positions"]:
        by_account.setdefault(p["accountId"], []).append(p)
    return {"positions": seed["positions"], "byAccount": by_account, "taxLots": seed["taxLots"]}
