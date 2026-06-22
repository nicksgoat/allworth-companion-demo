"""Capital-gains tax simulation over aggregate position basis data."""

from allworth_api.core.formatting import js_round

LT_RATE = 0.15 + 0.038  # cap gains + NIIT
ST_RATE = 0.24 + 0.038  # ordinary bracket + NIIT


def simulate_tax_impact(
    amount: float,
    account_id: str,
    symbol: str | None = None,
    *,
    positions: list[dict],
) -> dict:
    matching_positions = [position for position in positions if position["accountId"] == account_id]
    if symbol:
        matching_positions = [
            position for position in matching_positions if position["symbol"] == symbol.upper()
        ]
    buckets = []
    for position in matching_positions:
        for term in ("long", "short"):
            value_key = "longTermValue" if term == "long" else "shortTermValue"
            basis_key = "longTermCostBasis" if term == "long" else "shortTermCostBasis"
            bucket_value = float(position.get(value_key, 0) or 0)
            bucket_basis = float(position.get(basis_key, 0) or 0)
            if bucket_value <= 0:
                continue
            buckets.append(
                {
                    "symbol": position["symbol"],
                    "value": bucket_value,
                    "cost_basis": bucket_basis,
                    "gain_term": term,
                    "average_cost_basis": position.get("averageCostBasis"),
                    "price": position.get("price"),
                }
            )
    if not buckets:
        return {
            "error": (
                f"No aggregate cost-basis data found for {account_id}{f' / {symbol}' if symbol else ''}. "
                f"Cash accounts can be drawn with no capital-gains tax."
            )
        }

    ordered = sorted(
        buckets,
        key=lambda bucket: (
            max(bucket["value"] - bucket["cost_basis"], 0) / bucket["value"]
            if bucket["value"]
            else 0,
            0 if bucket["gain_term"] == "long" else 1,
            bucket["symbol"],
        ),
    )
    remaining = amount
    proceeds = lt_gain = st_gain = 0
    sales = []
    for bucket in ordered:
        if remaining <= 0:
            break
        bucket_value = bucket["value"]
        sell_value = min(remaining, bucket_value)
        gain_ratio = max(bucket_value - bucket["cost_basis"], 0) / bucket_value
        gain = sell_value * gain_ratio
        if bucket["gain_term"] == "short":
            st_gain += gain
        else:
            lt_gain += gain
        proceeds += sell_value
        remaining -= sell_value
        sales.append(
            {
                "symbol": bucket["symbol"],
                "averageCostBasis": bucket["average_cost_basis"],
                "price": bucket["price"],
                "proceeds": js_round(sell_value),
                "gain": js_round(gain),
                "term": bucket["gain_term"],
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
            f"{ST_RATE * 100:.1f}%. Uses aggregate average-basis data by holding. Estimates only — Nicole can run "
            f"exact numbers."
        ),
        "sales": sales,
    }
