"""Lot ledger with FIFO/HIFO/specific disposal, wash sales, and shorts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

D = Decimal


@dataclass
class TaxLot:
    symbol: str
    acquired: date
    qty: Decimal
    cost_basis: Decimal
    account_kind: str = "taxable"
    holding_period_adjustment_days: int = 0


@dataclass
class LotDisposal:
    symbol: str
    disposed: date
    qty: Decimal
    proceeds: Decimal
    basis: Decimal
    gain: Decimal
    term: str
    allowed_gain: Decimal


@dataclass
class ShortLot:
    symbol: str
    opened: date
    qty: Decimal
    proceeds: Decimal


class LotLedger:
    def __init__(self):
        self._lots: list[TaxLot] = []
        self._disposals: list[LotDisposal] = []
        self._shorts: list[ShortLot] = []

    def buy(self, symbol: str, acquired: date, qty: Decimal, cost: Decimal,
            account_kind: str = "taxable") -> TaxLot:
        lot = TaxLot(symbol, acquired, D(qty), D(cost), account_kind)
        self._lots.append(lot)
        # Apply pending loss disposals inside the ±30-day window.  Forward
        # replacements are knowable when the buy arrives; prior buys are
        # handled by sell().
        remaining_qty = lot.qty
        for disp in reversed(self._disposals):
            if disp.symbol != symbol or disp.gain >= 0 or disp.allowed_gain >= 0:
                continue
            days = (acquired - disp.disposed).days
            if not 0 <= days <= 30 or remaining_qty <= 0:
                continue
            matched = min(remaining_qty, disp.qty)
            loss_per_share = -disp.gain / disp.qty
            disallowed = loss_per_share * matched
            disp.allowed_gain += disallowed
            if account_kind != "ira":
                lot.cost_basis += disallowed
                lot.holding_period_adjustment_days = max(
                    lot.holding_period_adjustment_days,
                    max(1, (disp.disposed - disp.disposed).days + 1),
                )
            remaining_qty -= matched
        return lot

    def sell(self, symbol: str, disposed: date, qty: Decimal, proceeds: Decimal,
             method: str = "fifo") -> list[LotDisposal]:
        candidates = [x for x in self._lots if x.symbol == symbol and x.qty > 0]
        if method == "hifo":
            candidates.sort(key=lambda x: x.cost_basis / x.qty, reverse=True)
        else:
            candidates.sort(key=lambda x: x.acquired)
        left, proceeds_left, result = D(qty), D(proceeds), []
        for lot in candidates:
            if left <= 0:
                break
            take = min(left, lot.qty)
            ratio = take / left
            alloc_proceeds = proceeds_left * ratio
            basis = lot.cost_basis * take / lot.qty
            lot.qty -= take; lot.cost_basis -= basis
            gain = alloc_proceeds - basis
            term = "long" if (disposed - lot.acquired).days > 365 else "short"
            disp = LotDisposal(symbol, disposed, take, alloc_proceeds, basis,
                               gain, term, gain)
            # Replacement purchased in prior 30 days.
            if gain < 0:
                for repl in self._lots:
                    if repl.symbol != symbol or repl is lot or repl.qty <= 0:
                        continue
                    if 0 <= (disposed - repl.acquired).days <= 30:
                        disallowed = min(-gain, (-gain / take) * repl.qty)
                        disp.allowed_gain += disallowed
                        if repl.account_kind != "ira":
                            repl.cost_basis += disallowed
                            repl.holding_period_adjustment_days += max(1, (disposed - lot.acquired).days)
                        break
            self._disposals.append(disp); result.append(disp)
            left -= take; proceeds_left -= alloc_proceeds
        if left > 0:
            raise ValueError("insufficient shares")
        return result

    def open_lots(self, symbol: str) -> list[TaxLot]:
        return [x for x in self._lots if x.symbol == symbol and x.qty > 0]

    def realized_losses_allowed(self) -> Decimal:
        return sum((min(D("0"), x.allowed_gain) for x in self._disposals), D("0"))

    def realized_gain(self) -> Decimal:
        return sum((x.allowed_gain for x in self._disposals), D("0"))

    def total_value_at(self, price: Decimal) -> Decimal:
        return sum((x.qty * D(price) for x in self._lots), D("0"))

    def open_short(self, symbol: str, opened: date, qty: Decimal, proceeds: Decimal):
        self._shorts.append(ShortLot(symbol, opened, D(qty), D(proceeds)))

    def cover_short(self, symbol: str, disposed: date, qty: Decimal,
                    cost: Decimal) -> LotDisposal:
        lot = next((x for x in self._shorts if x.symbol == symbol and x.qty >= D(qty)), None)
        if lot is None:
            raise ValueError("insufficient short position")
        ratio = D(qty) / lot.qty
        proceeds = lot.proceeds * ratio
        lot.qty -= D(qty); lot.proceeds -= proceeds
        gain = proceeds - D(cost)
        disp = LotDisposal(symbol, disposed, D(qty), proceeds, D(cost), gain,
                           "short", gain)
        self._disposals.append(disp)
        return disp
