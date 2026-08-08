"""Deficit funding strategies and withdrawal tax gross-up."""

from dataclasses import dataclass
from decimal import Decimal

D = Decimal


@dataclass
class AcctView:
    id: str
    kind: str
    value: Decimal
    liquidity: int = 2
    growth: Decimal = D("0")
    tax_cost_per_dollar: Decimal = D("0")


@dataclass
class Withdrawal:
    account_id: str
    gross_amount: Decimal
    tax: Decimal
    net_amount: Decimal


@dataclass
class LiquidationResult:
    withdrawals: list[Withdrawal]
    shortfall: Decimal
    iterations: int
    flags: list[str]


def order_accounts(accounts: list[AcctView], strategy: str) -> list[AcctView]:
    type_rank = {"cash": 0, "taxable": 1, "qualified": 2, "ira": 2,
                 "deferred": 2, "roth": 3, "illiquid": 4}
    if strategy == "pro_rata":
        return list(accounts)
    if strategy in {"by_liquidity_then_lowest_tax_impact", "lowest_tax_impact"}:
        return sorted(accounts, key=lambda a: (a.liquidity, a.tax_cost_per_dollar, -a.value))
    if strategy == "lowest_growth_rate":
        return sorted(accounts, key=lambda a: (a.growth, a.liquidity))
    if strategy == "highest_growth_rate":
        return sorted(accounts, key=lambda a: (-a.growth, a.liquidity))
    if strategy == "straight_line":
        return sorted(accounts, key=lambda a: (a.value, a.id))
    return sorted(accounts, key=lambda a: (type_rank.get(a.kind, 2), a.liquidity))


def _rate(a: AcctView, ordinary: Decimal, gain_ratio: Decimal,
          cg: Decimal, penalty: Decimal) -> Decimal:
    if a.kind in {"qualified", "ira", "deferred"}:
        return min(D("0.95"), ordinary + penalty)
    if a.kind == "taxable":
        return min(D("0.95"), a.tax_cost_per_dollar if a.tax_cost_per_dollar > 0 else gain_ratio * cg)
    return max(D("0"), a.tax_cost_per_dollar)


def resolve_deficit(deficit: Decimal, accounts: list[AcctView], strategy: str,
                    marginal_ordinary: Decimal, gain_ratio_taxable: Decimal,
                    cg_rate: Decimal, penalty_rate: Decimal) -> LiquidationResult:
    need = max(D("0"), D(deficit))
    remaining = {a.id: D(a.value) for a in accounts}
    withdrawals: list[Withdrawal] = []
    ordered = order_accounts(accounts, strategy)
    if strategy == "pro_rata" and need:
        # A single proportional pass, tax-grossed per account.
        total = sum(remaining.values(), D("0"))
        ordered = sorted(ordered, key=lambda a: a.id)
        targets = {a.id: need * remaining[a.id] / total for a in ordered} if total else {}
    else:
        targets = {}
    for account in ordered:
        if need <= D("0.005"):
            break
        rate = _rate(account, D(marginal_ordinary), D(gain_ratio_taxable),
                     D(cg_rate), D(penalty_rate))
        desired_net = min(need, targets.get(account.id, need))
        gross = min(remaining[account.id], desired_net / (D("1") - rate))
        tax = gross * rate
        net = gross - tax
        withdrawals.append(Withdrawal(account.id, gross, tax, net))
        remaining[account.id] -= gross
        need -= net
    need = max(D("0"), need)
    return LiquidationResult(withdrawals, need, 1,
                             ["PLAN_DEPLETED"] if need > D("0.01") else [])
