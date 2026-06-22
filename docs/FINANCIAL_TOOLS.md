# Financial Tools

The production-facing financial tool surface is intentionally small:

- `simulate`: deterministic-seed Monte Carlo simulator.
- `rebalance`: deterministic mock model rebalancer with tax-aware sell limits.

This keeps the LLM/tooling path fast, auditable, and easy to test. A portfolio optimizer is not needed for this scope. The rebalancer is a rules-based calculator: compute drift, sell overweight securities in a deterministic tax-efficient order, respect tax/gains budgets, then buy underweight securities with the allowed proceeds.

## Why No Optimizer

Use the deterministic rebalancer when the goal is speed and repeatability:

- Same input always returns the same trades.
- No solver runtime or convergence risk.
- Easy to explain in an advisor review.
- Easy to audit against source model weights and gain budgets.

Add an optimizer later only if the product needs multi-objective constraints such as tax-loss harvesting priority, wash-sale windows, account-location rules, cash minimums, transaction costs, min-trade sizes, or risk-factor constraints.

## Data Mapping

Mock model data mirrors these production tables:

| Purpose | Source |
| --- | --- |
| Model list and model metadata | `tho.model_list` |
| Security-level target weights | `tho.Asset_Allocation_Security_Weights` |

The current mock models live in `backend/data/seed.json` under `allocationModels`.
Only AWF Core-Satellite models from the pasted warehouse extracts are included:

- 66 rows from `tho.model_list`
- 1,350 rows from `tho.Asset_Allocation_Security_Weights`

## Tool: `simulate`

Monte Carlo simulator for projection and affordability scenarios.

Endpoint:

```http
POST /tools/simulate
```

Input:

```json
{
  "initial_value": 100000,
  "annual_contribution": 5000,
  "expected_annual_return": 0.07,
  "annual_volatility": 0.15,
  "years": 20,
  "n_simulations": 10000,
  "goal_amount": 200000
}
```

Output:

```json
{
  "terminal_value": {
    "p10": 208597.21,
    "p25": 300061.39,
    "p50": 443245.24,
    "p75": 643775.72,
    "p90": 923340.17,
    "mean": 509884.33
  },
  "prob_of_ruin": 0.0,
  "prob_of_reaching_goal": 0.9123,
  "prob_of_reaching_goal_pct": "91.2%"
}
```

Implementation notes:

- Uses a fixed RNG seed for deterministic mock results.
- Vectorized with NumPy for speed.
- Inputs are intentionally generic so the LLM can model baseline vs. scenario by changing initial value, contribution, return, volatility, years, or goal amount.

## Tool: `rebalance`

Deterministic model rebalancer. It can use a direct `target_allocation`, or resolve `model_id` from the mock model tables.

Endpoint:

```http
POST /tools/rebalance
```

Minimal input:

```json
{
  "model_id": "AWF - Core-Satellite - 60/40"
}
```

When `current_holdings` is omitted, the tool uses synthetic current holdings and tax lots for the demo client. When `target_allocation` is omitted, the tool uses the selected model's weights.

Input with realized gains budget:

```json
{
  "model_id": "AWF - Core-Satellite - 60/40",
  "current_holdings": [
    {"ticker": "AAPL", "value": 100000, "cost_basis": 50000, "gain_term": "long"},
    {"ticker": "NVDA", "value": 100000, "cost_basis": 90000, "gain_term": "short"},
    {"ticker": "BND", "value": 100000, "cost_basis": 100000, "gain_term": "long"}
  ],
  "target_allocation": {"AAPL": 0.10, "NVDA": 0.10, "BND": 0.80},
  "realized_gains_budget": {
    "long_term": 10000,
    "short_term": 1000
  }
}
```

Input with tax budget:

```json
{
  "model_id": "AWF - Core-Satellite - 60/40",
  "target_allocation": {"AAPL": 0.10, "BND": 0.90},
  "tax_budget": {
    "max_tax": 1500,
    "long_term_rate": 0.15,
    "short_term_rate": 0.35
  }
}
```

Output:

```json
{
  "total_portfolio_value": 300000,
  "target_allocation": {"AAPL": 0.1, "BND": 0.8, "NVDA": 0.1},
  "post_trade_allocation": {"AAPL": 0.3333, "BND": 0.34, "NVDA": 0.3267},
  "trades": [
    {
      "ticker": "AAPL",
      "action": "SELL",
      "amount": 20000,
      "lot_id": null,
      "gain_term": "long_term",
      "realized_gain": 10000,
      "estimated_tax": 0
    },
    {
      "ticker": "NVDA",
      "action": "SELL",
      "amount": 10000,
      "lot_id": null,
      "gain_term": "short_term",
      "realized_gain": 1000,
      "estimated_tax": 0
    },
    {
      "ticker": "BND",
      "action": "BUY",
      "amount": 30000,
      "realized_gain": 0,
      "estimated_tax": 0
    }
  ],
  "realized_gains": {"long_term": 10000, "short_term": 1000},
  "estimated_tax": {"long_term": 0, "short_term": 0, "total": 0},
  "tax_calculation": {
    "method": "For each sell lot, gain_ratio = max(lot_value - lot_cost_basis, 0) / lot_value; realized_gain = actual_sell_amount * gain_ratio; estimated_tax = realized_gain * tax_rate.",
    "tax_rates": {"long_term": 0, "short_term": 0},
    "lots": [
      {
        "ticker": "AAPL",
        "lot_value": 100000,
        "lot_cost_basis": 50000,
        "lot_unrealized_gain": 50000,
        "gain_ratio": 0.5,
        "actual_sell_amount": 20000,
        "cost_basis_sold": 10000,
        "realized_gain": 10000,
        "tax_rate": 0,
        "estimated_tax": 0,
        "calculation": {
          "gain_ratio": "lot_unrealized_gain / lot_value",
          "realized_gain": "actual_sell_amount * gain_ratio",
          "cost_basis_sold": "actual_sell_amount - realized_gain",
          "estimated_tax": "realized_gain * tax_rate"
        }
      }
    ]
  },
  "residual_drift": {"AAPL": 0.2333, "BND": -0.46, "NVDA": 0.2267},
  "budget_limited": true,
  "model": {
    "model_id": "AWF - Core-Satellite - 60/40",
    "model_name": "AWF - Core-Satellite",
    "model_set": "Core-Satellite",
    "model_type": null,
    "portfolio_allocation": "60/40",
    "allocation": "60/40",
    "source_table": "tho.model_list"
  },
  "allocation_source_table": "tho.Asset_Allocation_Security_Weights"
}
```

## Rebalancer Rules

1. Normalize target weights if they do not sum exactly to 1.
2. Compute current value by ticker and target value by ticker.
3. Identify overweight tickers as sell candidates.
4. Sell lots in deterministic tax-efficient order:
   - lowest gain per dollar first,
   - long-term before short-term when gain ratio ties,
   - lot id as final stable tie-breaker.
5. Stop selling when the relevant realized-gain bucket or tax budget would be exceeded.
6. Allocate allowed sale proceeds to underweight tickers in proportion to remaining buy deficits.
7. Return residual drift so the advisor can see what the budget prevented.

## Notes For LLM Use

- Use `simulate` for projection and affordability.
- Use `rebalance` for portfolio/model drift.
- Do not invent model weights. Use `model_id` or explicit `target_allocation`.
- If the client asks for a tax-sensitive rebalance, include either `realized_gains_budget` or `tax_budget`.
- Treat all results as educational analysis, not a trade recommendation.
