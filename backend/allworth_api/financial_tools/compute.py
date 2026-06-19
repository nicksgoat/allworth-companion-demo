"""Layer 2: compute tools.

Pure math functions with no user context or domain-specific policy.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _percentile(values: np.ndarray, pct: float) -> float:
    if values.size == 0:
        return 0.0
    return float(np.percentile(values, pct))


def simulate(
    initial_value: float,
    annual_contribution: float = 0.0,
    expected_annual_return: float = 0.07,
    annual_volatility: float = 0.15,
    years: int = 20,
    n_simulations: int = 10_000,
    goal_amount: float | None = None,
) -> dict[str, Any]:
    """General-purpose Monte Carlo simulation for any scenario."""
    if years < 0:
        raise ValueError("years must be non-negative")
    if n_simulations <= 0:
        raise ValueError("n_simulations must be positive")

    rng = np.random.default_rng(42)
    values = np.full(n_simulations, float(initial_value), dtype=float)
    returns = rng.normal(expected_annual_return, annual_volatility, size=(years, n_simulations))

    # Each year updates the whole simulation vector at once. We keep the small
    # loop over years because contributions and ruin floors are path-dependent.
    for annual_return in returns:
        values = np.maximum(values * (1 + annual_return) + annual_contribution, 0.0)

    terminal_values = values

    result = {
        "terminal_value": {
            "p10": round(_percentile(terminal_values, 10), 2),
            "p25": round(_percentile(terminal_values, 25), 2),
            "p50": round(_percentile(terminal_values, 50), 2),
            "p75": round(_percentile(terminal_values, 75), 2),
            "p90": round(_percentile(terminal_values, 90), 2),
            "mean": round(float(np.mean(terminal_values)), 2) if terminal_values.size else 0.0,
        },
        "prob_of_ruin": round(float(np.mean(terminal_values <= 0)), 4),
    }

    if goal_amount is not None:
        prob = float(np.mean(terminal_values >= goal_amount))
        result["prob_of_reaching_goal"] = round(prob, 4)
        result["prob_of_reaching_goal_pct"] = f"{prob * 100:.1f}%"

    return result


def _gain_budget(realized_gains_budget: dict[str, float] | None, term: str) -> float | None:
    if not realized_gains_budget:
        return None
    if term == "short":
        return (
            realized_gains_budget["short_term"]
            if "short_term" in realized_gains_budget
            else realized_gains_budget.get("short")
        )
    return (
        realized_gains_budget["long_term"]
        if "long_term" in realized_gains_budget
        else realized_gains_budget.get("long")
    )


def _tax_room(tax_budget: dict[str, float] | None, term: str) -> tuple[float | None, float]:
    if not tax_budget:
        return None, 0.0
    max_tax = tax_budget["max_tax"] if "max_tax" in tax_budget else tax_budget.get("total")
    rate_key = "short_term_rate" if term == "short" else "long_term_rate"
    fallback_key = "short_rate" if term == "short" else "long_rate"
    rate = tax_budget.get(rate_key, tax_budget.get(fallback_key, 0.0))
    return max_tax, float(rate or 0.0)


def _as_lots(holding: dict[str, Any]) -> list[dict[str, Any]]:
    lots = holding.get("lots")
    if lots:
        return [
            {
                "ticker": holding["ticker"],
                "value": float(lot.get("value", 0.0)),
                "cost_basis": float(lot.get("cost_basis", lot.get("costBasis", 0.0))),
                "gain_term": lot.get("gain_term", lot.get("term", "long")),
                "lot_id": lot.get("lot_id", lot.get("id")),
            }
            for lot in lots
        ]

    value = float(holding.get("value", 0.0))
    cost_basis = holding.get("cost_basis", holding.get("costBasis"))
    unrealized_gain = holding.get("unrealized_gain", holding.get("unrealizedGain"))
    if cost_basis is None and unrealized_gain is not None:
        cost_basis = value - float(unrealized_gain)
    if cost_basis is None:
        cost_basis = value
    return [
        {
            "ticker": holding["ticker"],
            "value": value,
            "cost_basis": float(cost_basis),
            "gain_term": holding.get("gain_term", holding.get("term", "long")),
            "lot_id": holding.get("lot_id", holding.get("id")),
        }
    ]


def rebalance(
    current_holdings: list[dict[str, Any]],
    target_allocation: dict[str, float],
    realized_gains_budget: dict[str, float] | None = None,
    tax_budget: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Calculate deterministic tax-aware trades needed to approach a target allocation."""
    target_allocation = {ticker.upper(): float(weight) for ticker, weight in target_allocation.items()}
    total_target_weight = sum(target_allocation.values())
    if not current_holdings:
        return {"error": "current_holdings required"}
    if not target_allocation or total_target_weight <= 0:
        return {"error": "target_allocation required"}
    if abs(total_target_weight - 1.0) > 0.001:
        target_allocation = {
            ticker: weight / total_target_weight for ticker, weight in target_allocation.items()
        }

    values: dict[str, float] = {}
    sell_lots_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for holding in current_holdings:
        ticker = str(holding["ticker"]).upper()
        value = float(holding.get("value", 0.0))
        values[ticker] = values.get(ticker, 0.0) + value
        sell_lots_by_ticker.setdefault(ticker, []).extend(_as_lots({**holding, "ticker": ticker}))

    total_value = sum(values.values())
    if total_value <= 0:
        return {"error": "total portfolio value must be positive"}

    desired_sells = {
        ticker: max(value - target_allocation.get(ticker, 0.0) * total_value, 0.0)
        for ticker, value in values.items()
    }
    desired_buys = {
        ticker: max(target_weight * total_value - values.get(ticker, 0.0), 0.0)
        for ticker, target_weight in target_allocation.items()
    }

    realized = {"long_term": 0.0, "short_term": 0.0}
    estimated_tax = {"long_term": 0.0, "short_term": 0.0}
    sell_trades = []
    budget_limited = False

    for ticker, desired_sell in sorted(desired_sells.items(), key=lambda item: (-item[1], item[0])):
        remaining_sell = desired_sell
        lots = sorted(
            sell_lots_by_ticker.get(ticker, []),
            key=lambda lot: (
                max(lot["value"] - lot["cost_basis"], 0.0) / lot["value"] if lot["value"] else 0.0,
                0 if lot["gain_term"] == "long" else 1,
                lot.get("lot_id") or "",
            ),
        )
        for lot in lots:
            if remaining_sell <= 0:
                break
            lot_value = float(lot["value"])
            if lot_value <= 0:
                continue
            gain = max(lot_value - float(lot["cost_basis"]), 0.0)
            gain_ratio = gain / lot_value
            term_key = "short_term" if lot["gain_term"] == "short" else "long_term"
            sell_amount = min(remaining_sell, lot_value)

            gain_room = _gain_budget(realized_gains_budget, "short" if term_key == "short_term" else "long")
            if gain_room is not None and gain_ratio > 0:
                sell_amount = min(sell_amount, max((gain_room - realized[term_key]) / gain_ratio, 0.0))

            max_tax, rate = _tax_room(tax_budget, "short" if term_key == "short_term" else "long")
            if max_tax is not None and gain_ratio > 0 and rate > 0:
                used_tax = estimated_tax["long_term"] + estimated_tax["short_term"]
                sell_amount = min(sell_amount, max((max_tax - used_tax) / (gain_ratio * rate), 0.0))

            if sell_amount <= 0.005:
                budget_limited = True
                continue

            realized_gain = sell_amount * gain_ratio
            tax = realized_gain * rate
            realized[term_key] += realized_gain
            estimated_tax[term_key] += tax
            remaining_sell -= sell_amount
            values[ticker] -= sell_amount
            sell_trades.append(
                {
                    "ticker": ticker,
                    "action": "SELL",
                    "amount": round(sell_amount, 2),
                    "lot_id": lot.get("lot_id"),
                    "gain_term": term_key,
                    "realized_gain": round(realized_gain, 2),
                    "estimated_tax": round(tax, 2),
                }
            )

        if remaining_sell > 0.005:
            budget_limited = True

    proceeds = sum(trade["amount"] for trade in sell_trades)
    buy_total = sum(desired_buys.values())
    buy_trades = []
    if proceeds > 0 and buy_total > 0:
        for ticker, desired_buy in sorted(desired_buys.items(), key=lambda item: (-item[1], item[0])):
            buy_amount = proceeds * (desired_buy / buy_total)
            values[ticker] = values.get(ticker, 0.0) + buy_amount
            buy_trades.append(
                {
                    "ticker": ticker,
                    "action": "BUY",
                    "amount": round(buy_amount, 2),
                    "realized_gain": 0.0,
                    "estimated_tax": 0.0,
                }
            )

    post_allocation = {
        ticker: round(value / total_value, 4) for ticker, value in sorted(values.items()) if value > 0.005
    }
    target_pct = {ticker: round(weight, 4) for ticker, weight in sorted(target_allocation.items())}
    residual_drift = {
        ticker: round(post_allocation.get(ticker, 0.0) - target_allocation.get(ticker, 0.0), 4)
        for ticker in sorted(set(post_allocation) | set(target_allocation))
    }

    return {
        "total_portfolio_value": round(total_value, 2),
        "target_allocation": target_pct,
        "post_trade_allocation": post_allocation,
        "trades": sell_trades + buy_trades,
        "realized_gains": {key: round(value, 2) for key, value in realized.items()},
        "estimated_tax": {
            "long_term": round(estimated_tax["long_term"], 2),
            "short_term": round(estimated_tax["short_term"], 2),
            "total": round(estimated_tax["long_term"] + estimated_tax["short_term"], 2),
        },
        "residual_drift": residual_drift,
        "budget_limited": budget_limited,
    }
