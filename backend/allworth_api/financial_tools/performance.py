"""Performance calculations.

The app uses its simplified Modified Dietz convention:

    modified_dietz_ratio = (ending_value - outflow) / (beginning_value + inflow)

Cash-flow sign convention:
- positive amount = client contribution / inflow
- negative amount = client withdrawal / outflow
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class CashFlow:
    amount: float
    date: date


def _parse_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)[:10]).date()


def modified_dietz_return(
    beginning_value: float,
    ending_value: float,
    cash_flows: list[CashFlow | dict[str, Any]] | None = None,
    start_date: str | date | datetime | None = None,
    end_date: str | date | datetime | None = None,
) -> dict[str, Any]:
    """Return the app's Modified Dietz performance calculation.

    Cash-flow sign convention:
    - positive amount = client contribution / inflow
    - negative amount = client withdrawal / outflow

    Formula:
      modified_dietz_ratio = (ending_value - outflow) / (beginning_value + inflow)
      displayed_return = modified_dietz_ratio - 1
    """
    bmv = float(beginning_value or 0.0)
    emv = float(ending_value or 0.0)
    flows = cash_flows or []
    parsed_flows: list[CashFlow] = []
    for flow in flows:
        if isinstance(flow, CashFlow):
            parsed_flows.append(flow)
            continue
        parsed_flows.append(
            CashFlow(amount=float(flow.get("amount", 0.0)), date=_parse_date(flow["date"]))
        )

    inflow = 0.0
    outflow = 0.0
    flow_details = []
    for flow in parsed_flows:
        if flow.amount >= 0:
            inflow += flow.amount
            direction = "inflow"
        else:
            outflow += abs(flow.amount)
            direction = "outflow"
        flow_details.append(
            {
                "date": flow.date.isoformat(),
                "amount": round(flow.amount, 2),
                "direction": direction,
            }
        )

    adjusted_ending_value = emv - outflow
    adjusted_beginning_value = bmv + inflow
    ratio = adjusted_ending_value / adjusted_beginning_value if abs(adjusted_beginning_value) > 0.005 else 1.0
    rate = ratio - 1.0
    gain_loss = adjusted_ending_value - adjusted_beginning_value
    net_cash_flow = inflow - outflow

    return {
        "method": "modified_dietz",
        "return": round(rate, 6),
        "ratio": round(ratio, 6),
        "return_pct": round(rate * 100, 2),
        "beginning_value": round(bmv, 2),
        "ending_value": round(emv, 2),
        "adjusted_beginning_value": round(adjusted_beginning_value, 2),
        "adjusted_ending_value": round(adjusted_ending_value, 2),
        "gain_loss": round(gain_loss, 2),
        "inflow": round(inflow, 2),
        "outflow": round(outflow, 2),
        "net_cash_flow": round(net_cash_flow, 2),
        "weighted_cash_flow": 0.0,
        "denominator": round(adjusted_beginning_value, 2),
        "cash_flows": flow_details,
        "calculation": {
            "formula": "(ending_value - outflow) / (beginning_value + inflow)",
            "display_return_formula": "modified_dietz_ratio - 1",
        },
    }


def period_performance_from_values(
    points: list[dict[str, Any]],
    cash_flows: list[CashFlow | dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Calculate Modified Dietz return over a value series."""
    clean = [
        point
        for point in points
        if point.get("value") is not None and point.get("month") is not None
    ]
    if len(clean) < 2:
        return None
    start = str(clean[0]["month"])
    end = str(clean[-1]["month"])
    return modified_dietz_return(
        beginning_value=float(clean[0]["value"]),
        ending_value=float(clean[-1]["value"]),
        cash_flows=cash_flows or [],
        start_date=f"{start}-01" if len(start) == 7 else start,
        end_date=f"{end}-01" if len(end) == 7 else end,
    )
