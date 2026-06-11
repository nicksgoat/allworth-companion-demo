# The 8 demo tools: Anthropic tool definitions + local implementations over seed data.
from data import accounts_for, fmt_usd, js_round, portfolio_for, seed, spending_summary
from memory import active_facts, add_facts, profile_as_context
from nudges import nudges_for

# Labels drive the tool chips in the iOS chat UI.
TOOL_LABELS = {
    "get_accounts": "Reading your accounts…",
    "get_portfolio": "Reading your portfolio…",
    "get_financial_plan": "Reviewing your plan…",
    "get_spending": "Analyzing spending…",
    "get_client_profile": "Recalling what I know…",
    "update_client_profile": "Remembering that…",
    "simulate_tax_impact": "Estimating taxes…",
    "get_advisor_brief": "Preparing advisor brief…",
}

TOOL_DEFINITIONS = [
    {
        "name": "get_accounts",
        "description": "All of the client's accounts — Allworth-managed and outside (held-away) — "
        "with balances, 12-month history, and net worth totals.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_portfolio",
        "description": "Holdings across all accounts: positions with quantities, prices, values, "
        "asset classes, plus tax lots with cost basis and holding term.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_financial_plan",
        "description": "The client's financial plan: spending assumption, income plan, tax profile, "
        "and goals (lake house, 529s, retirement income).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_spending",
        "description": "Monthly spending by category vs. plan, including the recent 3-month average "
        "and how far it runs over plan.",
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "How many recent months to summarize (default 3)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_client_profile",
        "description": "What the assistant has learned about this client over time: goals, "
        "preferences, concerns, liquidity events — each with provenance.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "update_client_profile",
        "description": "Save a newly learned fact about the client (goal, preference, concern, "
        "liquidity event, or outside asset mentioned).",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact, stated plainly"},
                "category": {
                    "type": "string",
                    "enum": [
                        "goals",
                        "preferences",
                        "concerns",
                        "liquidity_events",
                        "outside_assets_mentioned",
                        "life_events",
                    ],
                },
                "source_quote": {
                    "type": "string",
                    "description": "Short verbatim quote from the client that supports the fact",
                },
            },
            "required": ["fact", "category"],
        },
    },
    {
        "name": "simulate_tax_impact",
        "description": "Estimate capital-gains tax for raising a dollar amount by selling from a "
        "given account, using real tax lots (highest-basis-first). Returns proceeds, realized gain, "
        "estimated tax, and effective drag.",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Dollar amount to raise"},
                "accountId": {
                    "type": "string",
                    "description": "Account to sell from: acct_trust (taxable trust) or acct_rh "
                    "(Robinhood). Cash accounts need no simulation.",
                },
                "symbol": {
                    "type": "string",
                    "description": "Optional: restrict the sale to one holding (e.g. AAPL)",
                },
            },
            "required": ["amount", "accountId"],
        },
    },
    {
        "name": "get_advisor_brief",
        "description": "Advisor-facing brief for a client: held-away assets detected, open nudges, "
        "learned profile, and suggested talking points.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

LT_RATE = 0.15 + 0.038  # cap gains + NIIT
ST_RATE = 0.24 + 0.038  # ordinary bracket + NIIT


def _strip_history(acct):
    return {k: v for k, v in acct.items() if k != "history"}


def run_tool(name, tool_input, client_id):
    tool_input = tool_input or {}
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
            tool_input.get("amount"), tool_input.get("accountId"), tool_input.get("symbol")
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
    return {"error": f"Unknown tool: {name}"}


def simulate_tax_impact(amount, account_id, symbol=None):
    prices = {f"{p['accountId']}:{p['symbol']}": p["price"] for p in seed["positions"]}
    lots = [lot for lot in seed["taxLots"] if lot["accountId"] == account_id]
    if symbol:
        lots = [lot for lot in lots if lot["symbol"] == symbol.upper()]
    if not lots:
        return {
            "error": (
                f"No tax lots found for {account_id}{f' / {symbol}' if symbol else ''}. "
                f"Cash accounts can be drawn with no capital-gains tax."
            )
        }

    # Sell highest basis first (most tax-efficient ordering).
    ordered = sorted(lots, key=lambda lot: lot["costPerShare"], reverse=True)
    remaining = amount
    proceeds = lt_gain = st_gain = 0
    sales = []
    for lot in ordered:
        if remaining <= 0:
            break
        price = prices.get(f"{lot['accountId']}:{lot['symbol']}")
        if not price:
            continue
        lot_value = lot["qty"] * price
        sell_value = min(remaining, lot_value)
        sell_qty = sell_value / price
        gain = sell_qty * (price - lot["costPerShare"])
        if lot["term"] == "short":
            st_gain += gain
        else:
            lt_gain += gain
        proceeds += sell_value
        remaining -= sell_value
        sales.append(
            {
                "lotId": lot["id"],
                "symbol": lot["symbol"],
                "qtySold": js_round(sell_qty * 100) / 100,
                "costPerShare": lot["costPerShare"],
                "price": price,
                "proceeds": js_round(sell_value),
                "gain": js_round(gain),
                "term": lot["term"],
                "acquired": lot["acquired"],
            }
        )
    est_tax = js_round(lt_gain * LT_RATE + st_gain * ST_RATE)
    return {
        "requested": amount,
        "proceedsAvailable": js_round(proceeds),
        "shortfall": js_round(remaining) if remaining > 0 else 0,
        "realizedGainLongTerm": js_round(lt_gain),
        "realizedGainShortTerm": js_round(st_gain),
        "estimatedTax": est_tax,
        "effectiveTaxDragPct": js_round(est_tax / proceeds * 1000) / 10 if proceeds > 0 else 0,
        "assumptions": (
            f"Long-term gains at {LT_RATE * 100:.1f}% (15% cap gains + 3.8% NIIT), short-term at "
            f"{ST_RATE * 100:.1f}%. Lots sold highest-basis-first. Estimates only — Dana can run "
            f"exact numbers."
        ),
        "sales": sales,
    }
