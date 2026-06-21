"""Capital-gains tax simulation over tax lots (pure — no data access)."""

from allworth_api.core.formatting import js_round

LT_RATE = 0.15 + 0.038  # cap gains + NIIT
ST_RATE = 0.24 + 0.038  # ordinary bracket + NIIT


def simulate_tax_impact(
    amount: float,
    account_id: str,
    symbol: str | None = None,
    *,
    positions: list[dict],
    tax_lots: list[dict],
) -> dict:
    prices = {f"{p['accountId']}:{p['symbol']}": p["price"] for p in positions}
    lots = [lot for lot in tax_lots if lot["accountId"] == account_id]
    if symbol:
        lots = [lot for lot in lots if lot["symbol"] == symbol.upper()]
    if not lots:
        return {
            "error": (
                f"No tax lots found for {account_id}{f' / {symbol}' if symbol else ''}. "
                f"Cash accounts can be drawn with no capital-gains tax."
            )
        }

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
            f"{ST_RATE * 100:.1f}%. Lots sold highest-basis-first. Estimates only — your advisor can "
            f"run exact numbers."
        ),
        "sales": sales,
    }
