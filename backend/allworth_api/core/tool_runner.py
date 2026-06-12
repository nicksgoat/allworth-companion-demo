# Tool execution: dispatches tool calls to local implementations over seed data.
import time

from allworth_api.core.audit import estimate_tokens, log_tool_call
from allworth_api.core.formatting import fmt_usd
from allworth_api.core.memory import active_facts, add_facts, profile_as_context
from allworth_api.core.nudges import nudges_for
from allworth_api.core.tax import simulate_tax_impact
from allworth_api.data.seed import accounts_for, portfolio_for, seed, spending_summary


def _strip_history(acct):
    return {k: v for k, v in acct.items() if k != "history"}


def run_tool(name: str, tool_input: dict | None, client_id: str) -> dict:
    """Execute a tool and return result wrapped with diagnostics."""
    tool_input = tool_input or {}
    t0 = time.perf_counter()
    result = _dispatch(name, tool_input, client_id)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Append diagnostics envelope (timing + token estimates)
    if isinstance(result, dict) and "error" not in result:
        result["_diagnostics"] = {
            "tool": name,
            "elapsed_ms": round(elapsed_ms, 1),
            "tokens_in": estimate_tokens(tool_input),
            "tokens_out": estimate_tokens(result),
        }

    # Audit trail
    log_tool_call(
        tool=name,
        client_id=client_id,
        params=tool_input,
        result=result,
        elapsed_ms=elapsed_ms,
    )
    return result


def _dispatch(name: str, tool_input: dict, client_id: str) -> dict:
    if name == "get_accounts":
        a = accounts_for()
        return {
            "netWorth": a["netWorth"],
            "allworthManagedTotal": a["allworthTotal"],
            "heldAwayTotal": a["heldAwayTotal"],
            "liabilitiesTotal": a["liabilitiesTotal"],
            "accounts": [_strip_history(acct) for acct in seed["accounts"]],
            "netWorthHistory": seed["netWorthHistory"],
        }
    if name == "get_portfolio":
        p = portfolio_for()
        trust_value = sum(x["value"] for x in p["positions"] if x["accountId"] == "acct_trust")
        aapl = next(
            (x for x in p["positions"] if x["accountId"] == "acct_trust" and x["symbol"] == "AAPL"), None
        )
        return {
            "positions": p["positions"],
            "taxLots": p["taxLots"],
            "concentrationNote": (
                f"AAPL is {aapl['value'] / trust_value * 100:.1f}% of the trust account." if aapl else None
            ),
        }
    if name == "get_financial_plan":
        return {"plan": seed["plan"], "liquidityEvent": seed["liquidityEvent"]}
    if name == "get_spending":
        s = spending_summary(tool_input.get("months") or 3)
        return {
            "recentMonths": s["months"],
            "avg3mo": s["avg3mo"],
            "plannedMonthly": s["plan"],
            "overPlanPct": s["overPlanPct"],
            "note": (
                f"Spending is averaging {fmt_usd(s['avg3mo'])}/mo against a {fmt_usd(s['plan'])}/mo "
                f"plan ({s['overPlanPct']}% over). Travel and Gifts/Family drive most of the difference."
            ),
        }
    if name == "get_client_profile":
        return {
            "clientId": client_id,
            "facts": active_facts(client_id),
            "summary": profile_as_context(client_id),
        }
    if name == "update_client_profile":
        added = add_facts(client_id, [tool_input], None)
        if added:
            return {"saved": True, "fact": added[0]}
        return {"saved": False, "reason": "Similar fact already on file."}
    if name == "simulate_tax_impact":
        return simulate_tax_impact(
            tool_input.get("amount"),
            tool_input.get("accountId"),
            tool_input.get("symbol"),
            positions=seed["positions"],
            tax_lots=seed["taxLots"],
        )
    if name == "get_advisor_brief":
        a = accounts_for()
        return {
            "client": next((c for c in seed["personas"]["clients"] if c["id"] == client_id), None),
            "managedTotal": a["allworthTotal"],
            "heldAwayDetected": a["heldAwayTotal"],
            "heldAwayAccounts": [_strip_history(x) for x in a["outside"] if x["type"] != "liability"],
            "liabilities": [_strip_history(x) for x in a["outside"] if x["type"] == "liability"],
            "openNudges": nudges_for(client_id),
            "profile": active_facts(client_id),
            "liquidityEvent": seed["liquidityEvent"],
        }
    if name == "run_retirement_projection":
        from allworth_api.core.planning import run_retirement_projection

        return run_retirement_projection(
            end_age=tool_input.get("end_age", 95),
            n_simulations=tool_input.get("n_simulations", 500),
        )
    if name == "analyze_portfolio_drift":
        from allworth_api.core.planning import analyze_portfolio_drift

        return analyze_portfolio_drift(account_id=tool_input.get("accountId"))
    if name == "run_roth_conversion_analysis":
        from allworth_api.core.planning import run_roth_conversion_analysis

        return run_roth_conversion_analysis(
            conversion_amount=tool_input.get("conversion_amount"),
            current_income=tool_input.get("current_income"),
        )
    if name == "analyze_goal_funding":
        from allworth_api.core.planning import analyze_goal_funding

        return analyze_goal_funding(
            growth_rate=tool_input.get("growth_rate", 0.06),
        )
    if name == "analyze_income_sustainability":
        from allworth_api.core.planning import analyze_income_sustainability

        return analyze_income_sustainability(
            inflation_rate=tool_input.get("inflation_rate", 0.03),
        )
    return {"error": f"Unknown tool: {name}"}
