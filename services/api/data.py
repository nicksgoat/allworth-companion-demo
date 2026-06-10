import json
import math
from datetime import datetime, timezone
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
seed = json.loads((API_DIR / "data" / "seed.json").read_text())


def js_round(x: float) -> int:
    # Matches JS Math.round (half toward +inf), not Python's banker's rounding.
    return math.floor(x + 0.5)


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fmt_usd(n: float) -> str:
    return ("-$" if n < 0 else "$") + f"{abs(js_round(n)):,}"


def accounts_for() -> dict:
    allworth = [a for a in seed["accounts"] if a["group"] == "allworth"]
    outside = [a for a in seed["accounts"] if a["group"] == "outside"]
    total = lambda xs: sum(a["balance"] for a in xs)
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
