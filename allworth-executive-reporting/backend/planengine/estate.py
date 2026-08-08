"""Estate snapshot, tax, liquidity, and distribution waterfall analytics."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .models import Facts

D = Decimal


@dataclass
class EstateFlow:
    gross_estate: Decimal
    liabilities: Decimal
    probate_costs: Decimal
    final_expenses: Decimal
    federal_estate_tax: Decimal
    state_estate_tax: Decimal
    net_to_survivor: Decimal
    net_to_heirs: Decimal
    charitable: Decimal
    liquid_assets: Decimal
    liquidity_need: Decimal
    liquidity_shortfall: Decimal
    flags: list[str] = field(default_factory=list)


def estate_tax(taxable_estate: Decimal, exemption: Decimal = D("15000000"),
               adjusted_taxable_gifts: Decimal = D("0"), dsue: Decimal = D("0")) -> Decimal:
    taxable = max(D("0"), D(taxable_estate) + D(adjusted_taxable_gifts) - D(exemption) - D(dsue))
    # Unified transfer tax reaches 40%; the compressed planning schedule is
    # deliberately conservative above the exemption.
    return taxable * D("0.40")


def build_estate_flow(facts: Facts | dict, death_order: str = "client_first",
                      marital_deduction: bool = True, **_: object) -> EstateFlow:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    gross = sum((a.value for a in facts.accounts if not a.exclude_from_planning), D("0"))
    debts = sum((x.current_balance for x in facts.liabilities), D("0"))
    liquid = sum((a.value for a in facts.accounts if a.kind in {"cash", "taxable", "roth", "qualified"}), D("0"))
    probate_rate = D(str(getattr(facts.assumptions, "probate_rate", D("0.03"))))
    final = D(str(getattr(facts.assumptions, "final_expenses", D("15000"))))
    probate = gross * probate_rate
    taxable = max(D("0"), gross - debts - probate - final)
    fed = D("0") if marital_deduction and len([p for p in facts.people if p.role in {"client", "spouse"}]) > 1 else estate_tax(taxable)
    state_rate = D(str(getattr(facts.assumptions, "state_death_tax_rate", 0)))
    state = taxable * state_rate
    need = debts + probate + final + fed + state
    shortfall = max(D("0"), need - liquid)
    net = max(D("0"), gross - need)
    survivor = net if marital_deduction and fed == 0 else D("0")
    heirs = net - survivor
    return EstateFlow(gross, debts, probate, final, fed, state, survivor, heirs, D("0"),
                      liquid, need, shortfall,
                      ["FORCED_SALE_REQUIRED"] if shortfall else [])


def grat_gift_value(funding: Decimal, annuity: Decimal, term_years: int,
                    section_7520_rate: Decimal) -> Decimal:
    rate = D(section_7520_rate)
    pv = D(annuity) * (D("1") - (D("1") + rate) ** -term_years) / rate if rate else D(annuity) * term_years
    return max(D("0"), D(funding) - pv)
