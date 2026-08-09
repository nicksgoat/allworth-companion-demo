"""Index recurring nominal amounts without float conversions."""

from decimal import Decimal

from .models import Indexing


def indexed_amount(amount: Decimal, indexing: Indexing, *, inflation: Decimal,
                   years_since_plan_start: int, years_since_flow_start: int) -> Decimal:
    if indexing.mode == "none":
        return amount
    rate = inflation if indexing.mode == "inflation" else Decimal(indexing.custom_rate or 0)
    years = (years_since_plan_start if indexing.start_indexing == "immediately"
             else years_since_flow_start)
    return amount * ((Decimal("1") + rate) ** max(0, years))
