"""Goal funding views over the canonical projection ledger."""

from decimal import Decimal

from .models import Facts, Projection

D = Decimal


def evaluate_goals(facts: Facts, projection: Projection) -> list[dict]:
    results = []
    client = next((person for person in facts.people if person.role == "client"), None)
    for index, goal in enumerate(facts.goals):
        target = D(str(goal.get("target_amount", goal.get("amount", goal.get("cost", 0))) or 0))
        due_year = goal.get("target_year") or goal.get("year")
        if due_year is None and goal.get("target_age") is not None and client:
            due_year = client.date_of_birth.year + int(goal["target_age"])
        due_year = int(due_year or projection.rows[-1].year)
        row = min(projection.rows, key=lambda value: abs(value.year - due_year))
        goal_type = str(goal.get("kind", goal.get("type", "general"))).lower()
        if goal_type in {"education", "college"}:
            available = sum((balance for account_id, balance in row.account_balances.items()
                             if next((account.kind for account in facts.accounts
                                      if str(account.id) == account_id), "") == "529"), D("0"))
        else:
            available = max(D("0"), row.net_worth)
        funded = D("1") if target <= 0 else min(D("1"), available / target)
        results.append({"id": str(goal.get("id", index)), "name": goal.get("name", f"Goal {index + 1}"),
                        "kind": goal_type, "target_year": due_year,
                        "target_amount": str(target), "available": str(available),
                        "funded_pct": str(funded * 100),
                        "shortfall": str(max(D("0"), target - available)),
                        "status": "funded" if funded >= 1 else "shortfall"})
    return results
