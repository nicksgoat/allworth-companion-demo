# Tool schema definitions and UI labels for the demo and financial tools.

from allworth_api.financial_tools.tools import FINANCIAL_TOOL_DEFINITIONS, FINANCIAL_TOOL_LABELS

TOOL_LABELS = {
    "get_accounts": "Reading your accounts…",
    "get_portfolio": "Reading your portfolio…",
    "get_financial_plan": "Reviewing your plan…",
    "get_spending": "Analyzing spending…",
    "get_client_profile": "Recalling what I know…",
    "update_client_profile": "Remembering that…",
    "simulate_tax_impact": "Estimating taxes…",
    "get_advisor_brief": "Preparing advisor brief…",
    "run_retirement_projection": "Running retirement projection…",
    "analyze_portfolio_drift": "Analyzing portfolio drift…",
    "run_roth_conversion_analysis": "Modeling Roth conversion…",
    "analyze_goal_funding": "Reviewing goal progress…",
    "analyze_income_sustainability": "Evaluating income plan…",
    **FINANCIAL_TOOL_LABELS,
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
        "description": "Layer 1 data tool. Fetch current holdings, total value, and allocation breakdown.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    *FINANCIAL_TOOL_DEFINITIONS,
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
    {
        "name": "run_retirement_projection",
        "description": "Monte Carlo retirement projection: simulates 500 market paths to estimate "
        "probability of funding retirement spending through a target age. Returns success rate, "
        "percentile wealth paths (p5/p25/median/p75/p95), and interpretation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "end_age": {
                    "type": "integer",
                    "description": "Target age for projection (default 95)",
                },
                "n_simulations": {
                    "type": "integer",
                    "description": "Number of Monte Carlo paths (default 500)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "analyze_portfolio_drift",
        "description": "Legacy app-screen drift analyzer. For LLM model/rebalance answers, prefer "
        "the rebalance tool, which resolves exact AWF Core-Satellite model names and weights.",
        "input_schema": {
            "type": "object",
            "properties": {
                "accountId": {
                    "type": "string",
                    "description": "Optional: limit analysis to one account (e.g. acct_trust)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "run_roth_conversion_analysis",
        "description": "Estimate the tax impact of converting traditional IRA funds to Roth IRA. "
        "Shows marginal bracket impact, NIIT surcharge, effective rate, and break-even years "
        "until tax-free growth exceeds the upfront cost.",
        "input_schema": {
            "type": "object",
            "properties": {
                "conversion_amount": {
                    "type": "number",
                    "description": (
                        "Dollar amount to convert (default: $50K or IRA balance, whichever is less)"
                    ),
                },
                "current_income": {
                    "type": "number",
                    "description": "Current year taxable income (default: derived from plan)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "analyze_goal_funding",
        "description": "Assess funding status of each financial goal (lake house, 529s, retirement income). "
        "Projects current funding forward with expected growth, identifies gaps, and calculates "
        "the monthly contribution needed to get back on track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "growth_rate": {
                    "type": "number",
                    "description": "Assumed annual portfolio growth rate (default 0.06 = 6%)",
                },
            },
            "required": [],
        },
    },
    {
        "name": "analyze_income_sustainability",
        "description": "Evaluate whether current income sources (portfolio + other) sustain planned spending "
        "over 5/10/20 year horizons with inflation. Identifies the crossover year when spending "
        "exceeds income and reports cash runway.",
        "input_schema": {
            "type": "object",
            "properties": {
                "inflation_rate": {
                    "type": "number",
                    "description": "Annual inflation rate applied to spending (default 0.03 = 3%)",
                },
            },
            "required": [],
        },
    },
]
