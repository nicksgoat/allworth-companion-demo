"""Canonical annual cash-flow ledger simulation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .indexing import indexed_amount
from .amortization import annual_amortization
from .liquidation import AcctView, resolve_deficit
from .models import Facts, Projection, TaxInput, YearRow
from .rmd import rmd_for
from .tax.calculator import compute_taxes
from .tax.tables import load_tables, project_tables
from .timing import resolve_all

D = Decimal
ZERO = D("0")


@dataclass(frozen=True)
class TimelineContext:
    start_year: int
    client_birth_year: int
    spouse_birth_year: int
    client_retirement_year: int
    spouse_retirement_year: int
    client_death_year: int
    spouse_death_year: int


def _context(facts: Facts) -> TimelineContext:
    client = next((p for p in facts.people if p.role == "client"), facts.people[0] if facts.people else None)
    spouse = next((p for p in facts.people if p.role == "spouse"), client)
    if client is None:
        raise ValueError("facts require at least one client person")
    cb, sb = client.date_of_birth.year, spouse.date_of_birth.year
    retirement = getattr(facts.assumptions, "retirement", {}) or {}
    client_cfg = retirement.get("client", {}) if isinstance(retirement, dict) else {}
    spouse_cfg = retirement.get("spouse", {}) if isinstance(retirement, dict) else {}
    client_retirement_age = int(client_cfg.get("retirement_age", client.retirement_age))
    spouse_retirement_age = int(spouse_cfg.get("retirement_age", spouse.retirement_age))
    client_death_age = int(client_cfg.get("assumed_age_of_death", client.assumed_age_of_death))
    spouse_death_age = int(spouse_cfg.get("assumed_age_of_death", spouse.assumed_age_of_death))
    return TimelineContext(facts.assumptions.start_year, cb, sb,
                           cb + client_retirement_age, sb + spouse_retirement_age,
                           cb + client_death_age, sb + spouse_death_age)


def _phase(year: int, ctx: TimelineContext) -> str:
    first_death, second_death = sorted((ctx.client_death_year, ctx.spouse_death_year))
    if year >= second_death:
        return "estate"
    if year >= first_death:
        return "survivor"
    if year >= min(ctx.client_retirement_year, ctx.spouse_retirement_year):
        return "retirement"
    return "current"


def _active_amount(flow, year: int, ctx: TimelineContext, inflation: Decimal) -> Decimal:
    start, end = resolve_all(flow.starts, flow.ends, ctx)
    if start is None or not start <= year <= end:
        return ZERO
    base_amount = flow.amount
    if flow.kind == "living" and year >= min(ctx.client_retirement_year, ctx.spouse_retirement_year):
        base_amount = D(str(getattr(flow, "retirement_amount", flow.amount)))
    return indexed_amount(base_amount, flow.indexing, inflation=inflation,
                          years_since_plan_start=year - ctx.start_year,
                          years_since_flow_start=year - start)


def _policy_issue_year(policy, ctx: TimelineContext) -> int:
    if getattr(policy, "issue_year", None):
        return int(policy.issue_year)
    purchase_date = getattr(policy, "purchase_date", None)
    return int(purchase_date.year) if purchase_date else ctx.start_year


def _insured_death_year(policy, ctx: TimelineContext) -> int:
    insured = str(getattr(policy, "insured", "client"))
    if insured == "spouse":
        return ctx.spouse_death_year
    if insured == "survivorship":
        return max(ctx.client_death_year, ctx.spouse_death_year)
    return ctx.client_death_year


def _insured_retirement_year(policy, ctx: TimelineContext) -> int:
    return ctx.spouse_retirement_year if str(getattr(policy, "insured", "client")) == "spouse" else ctx.client_retirement_year


def _policy_coverage_end_year(policy, ctx: TimelineContext) -> int:
    policy_type = str(getattr(policy, "policy_type", "") or "").lower()
    issue_year = _policy_issue_year(policy, ctx)
    if getattr(policy, "term_ends_at_retirement", False):
        return _insured_retirement_year(policy, ctx)
    term_years = getattr(policy, "term_years", None)
    if term_years and ("term" in policy_type or policy_type in {"group", "other"}):
        return issue_year + int(term_years)
    return max(ctx.client_death_year, ctx.spouse_death_year) + 1


def _policy_premium_end_year(policy, ctx: TimelineContext) -> int:
    issue_year = _policy_issue_year(policy, ctx)
    premium_term_years = getattr(policy, "premium_term_years", None)
    if premium_term_years:
        return issue_year + int(premium_term_years)
    return _policy_coverage_end_year(policy, ctx)


def _policy_cash_value(policy, year: int, ctx: TimelineContext) -> Decimal:
    if getattr(policy, "exclude_from_planning", False):
        return ZERO
    issue_year = _policy_issue_year(policy, ctx)
    death_year = _insured_death_year(policy, ctx)
    coverage_end = _policy_coverage_end_year(policy, ctx)
    if year < issue_year or year >= death_year or year >= coverage_end:
        return ZERO
    cash_value = D(getattr(policy, "current_cash_value", ZERO))
    growth_rate = D(getattr(policy, "cash_value_growth_rate", ZERO))
    return cash_value * ((D("1") + growth_rate) ** max(0, year - ctx.start_year))


def run_projection(facts: Facts | dict, return_path: dict[int, Decimal] | None = None,
                   *, trace: bool = False, start_year: int | None = None,
                   events: list | None = None, assertions: str | None = None, **_: object) -> Projection:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    if start_year is not None:
        facts = facts.model_copy(deep=True)
        facts.assumptions.start_year = start_year
    ctx = _context(facts)
    assumptions = facts.assumptions
    client = next(p for p in facts.people if p.role == "client")
    has_spouse = any(p.role == "spouse" for p in facts.people)
    end_year = min(ctx.start_year + 100,
                   max(ctx.client_death_year, ctx.spouse_death_year,
                       client.date_of_birth.year + assumptions.plan_end_age))
    balances = {str(a.id): D(a.value) for a in facts.accounts if not a.exclude_from_planning}
    basis = {str(a.id): D(a.tax_basis) for a in facts.accounts if not a.exclude_from_planning}
    accounts = {str(a.id): a for a in facts.accounts if not a.exclude_from_planning}
    base_tables = load_tables(2026)
    liability_schedules = []
    for liability in facts.liabilities:
        try:
            liability_schedules.append((liability, annual_amortization(
                liability.current_balance, liability.interest_rate, liability.term_years,
                liability.payment_frequency, liability.repayment_type).years))
        except ValueError:
            continue
    rows: list[YearRow] = []
    lifetime_taxes = ZERO
    first_shortfall = None
    carryforward = ZERO
    for year in range(ctx.start_year, end_year + 1):
        tables = project_tables(base_tables, year, assumptions.inflation_rate)
        inflows = sum((_active_amount(x, year, ctx, assumptions.inflation_rate)
                       for x in facts.income), ZERO)
        outflows = sum((_active_amount(x, year, ctx, assumptions.inflation_rate)
                        for x in facts.expenses), ZERO)
        social_security_gross = sum(
            (_active_amount(x, year, ctx, assumptions.inflation_rate)
             for x in facts.income if x.kind == "social_security"), ZERO)
        insurance_premiums = insurance_death_benefits = insurance_cash_value = ZERO
        for policy in facts.insurance:
            if getattr(policy, "exclude_from_planning", False):
                continue
            death_year = _insured_death_year(policy, ctx)
            issue_year = _policy_issue_year(policy, ctx)
            coverage_end = _policy_coverage_end_year(policy, ctx)
            premium_end = _policy_premium_end_year(policy, ctx)
            if issue_year <= year < death_year and year < coverage_end and year < premium_end:
                insurance_premiums += D(policy.annual_premium)
            if year == death_year and death_year < coverage_end:
                insurance_death_benefits += D(policy.current_death_benefit)
            insurance_cash_value += _policy_cash_value(policy, year, ctx)
        outflows += insurance_premiums
        inflows += insurance_death_benefits
        year_index = year - ctx.start_year
        liability_interest = ZERO
        liability_balances: dict[str, Decimal] = {}
        for liability, schedule in liability_schedules:
            if year_index < len(schedule):
                outflows += schedule[year_index].payment
                liability_interest += schedule[year_index].interest
                liability_balances[str(liability.id)] = schedule[year_index].ending_balance
            else:
                liability_balances[str(liability.id)] = ZERO
        interest_taxable = interest_exempt = ZERO
        rmd_total = ZERO
        for aid, account in accounts.items():
            bal = balances[aid]
            if account.kind in {"taxable", "cash"}:
                interest_taxable += bal * D(account.income_yield)
                interest_exempt += bal * D(account.tax_exempt_yield)
            if account.apply_rmd and account.owner == "client":
                age = year - client.date_of_birth.year
                rmd = min(bal, rmd_for(bal, age, client.date_of_birth.year))
                balances[aid] -= rmd; rmd_total += rmd; inflows += rmd
        inflows += interest_taxable + interest_exempt
        taxable_wages = sum((_active_amount(x, year, ctx, assumptions.inflation_rate)
                             for x in facts.income if x.taxable and x.kind in {"salary", "wages"}), ZERO)
        # Apply employee deferrals and employer matches before tax calculation.
        employee_deferrals = employer_contributions = ZERO
        salary_by_owner = {owner: sum((_active_amount(x, year, ctx, assumptions.inflation_rate)
                                       for x in facts.income if x.kind in {"salary", "wages"} and x.owner == owner), ZERO)
                           for owner in ("client", "spouse")}
        for aid, account in accounts.items():
            contributions = getattr(account, "contributions", None)
            if account.kind != "qualified" or not contributions:
                continue
            owner_salary = salary_by_owner.get(account.owner, ZERO)
            employee = contributions.get("employee", {})
            employee_type = employee.get("type", "none")
            if employee_type == "pct_of_salary": amount = owner_salary * D(str(employee.get("pct", 0)))
            elif employee_type == "fixed": amount = D(str(employee.get("amount", 0)))
            elif employee_type in {"maximum", "maximum_after_matching"}: amount = D(tables.retirement_limits["401k_employee"])
            else: amount = ZERO
            person = next((p for p in facts.people if p.role == account.owner), None)
            age = year - person.date_of_birth.year if person else 0
            limit = D(tables.retirement_limits["401k_employee"])
            if age >= 50: limit += D(tables.retirement_limits["catch_up_50"])
            amount = min(max(ZERO, amount), limit, owner_salary)
            employer = contributions.get("employer", {})
            employer_type = employer.get("type", "none")
            if employer_type == "match_pct":
                eligible = min(amount, owner_salary * D(str(employer.get("max_pct_of_salary", 0))))
                match = eligible * D(str(employer.get("match_pct", 0)))
            elif employer_type == "pct_of_salary": match = owner_salary * D(str(employer.get("pct", 0)))
            elif employer_type == "fixed": match = D(str(employer.get("amount", 0)))
            else: match = ZERO
            max_total = D(tables.retirement_limits["total_415c"])
            match = min(max(ZERO, match), max(ZERO, max_total - amount))
            balances[aid] += amount + match
            employee_deferrals += amount; employer_contributions += match
        inflows -= employee_deferrals
        taxable_wages = max(ZERO, taxable_wages - employee_deferrals)
        # Execute recurring transfers, including taxable Roth conversions.
        roth_conversion = ZERO
        for transfer in facts.transfers:
            start, end = resolve_all(transfer.starts, transfer.ends, ctx)
            if start is None or not start <= year <= end: continue
            source = next((aid for aid, a in accounts.items()
                           if str(a.id) == str(transfer.source_account) or a.name == str(transfer.source_account)), None)
            destination = next((aid for aid, a in accounts.items()
                                if str(a.id) == str(transfer.destination_account) or a.name == str(transfer.destination_account)), None)
            if not source or not destination: continue
            amount = min(D(transfer.annual_amount), balances[source])
            balances[source] -= amount; balances[destination] += amount
            if transfer.roth_conversion: roth_conversion += amount
        tax_input = TaxInput(filing_status="mfj" if has_spouse and year <= min(ctx.client_death_year, ctx.spouse_death_year) else "single",
                             wages=taxable_wages, interest_taxable=interest_taxable,
                             interest_exempt=interest_exempt,
                             retirement_distributions=rmd_total, roth_conversion=roth_conversion,
                             social_security_gross=social_security_gross,
                             itemized=liability_interest,
                             capital_loss_carryforward=carryforward)
        taxes = compute_taxes(tax_input, tables, assumptions.tax_mode,
                              assumptions.flat_tax_rate)
        carryforward = D(taxes.detail.get("carryforward_out", 0))
        total_tax = taxes.total + (max(ZERO, tax_input.wages + interest_taxable) *
                                   (assumptions.state_income_tax_rate + assumptions.local_income_tax_rate))
        lifetime_taxes += total_tax
        net = inflows - outflows - total_tax
        withdrawals = savings = shortfall = ZERO
        savings_target = None
        trace_rows = []
        if net < 0:
            views = [AcctView(aid, account.kind, balances[aid], account.liquidity,
                              account.growth_rate,
                              (taxes.marginal_rate or D("0.24")) if account.kind in {"qualified", "ira"}
                              else (max(ZERO, balances[aid] - basis.get(aid, balances[aid])) /
                                    balances[aid] * D("0.15") if account.kind == "taxable" and balances[aid] else ZERO))
                     for aid, account in accounts.items() if balances[aid] > 0]
            views = [view for view in views if accounts[view.id].kind not in {"private_equity", "real_estate"}]
            result = resolve_deficit(-net, views, assumptions.liquidation_strategy,
                                     taxes.marginal_rate or D("0.24"), D("0.5"),
                                     D("0.15"), D("0"))
            for withdrawal in result.withdrawals:
                old_balance = balances[withdrawal.account_id]
                if accounts[withdrawal.account_id].kind == "taxable" and old_balance > 0:
                    basis[withdrawal.account_id] -= basis[withdrawal.account_id] * withdrawal.gross_amount / old_balance
                balances[withdrawal.account_id] -= withdrawal.gross_amount
                withdrawals += withdrawal.gross_amount
            liquidation_tax = sum((withdrawal.tax for withdrawal in result.withdrawals), ZERO)
            total_tax += liquidation_tax
            lifetime_taxes += liquidation_tax
            shortfall = result.shortfall
            if shortfall > 0 and first_shortfall is None:
                first_shortfall = year
            if trace:
                trace_rows.append({"step": "deficit_funding", "rule": assumptions.liquidation_strategy,
                                   "gross_withdrawals": str(withdrawals),
                                   "withdrawal_tax": str(liquidation_tax),
                                   "shortfall": str(shortfall)})
        elif net > 0 and accounts:
            savings = net * assumptions.save_pct
            # Prefer cash, then taxable for surplus routing.
            target = sorted(accounts, key=lambda aid: (accounts[aid].kind != "cash",
                                                       accounts[aid].kind != "taxable"))[0]
            balances[target] += savings
            savings_target = target
        growth = ZERO
        for aid, account in accounts.items():
            rate = D(return_path.get(year, account.growth_rate) if return_path else account.growth_rate)
            if account.kind in {"taxable", "cash"}:
                rate -= D(account.income_yield) + D(account.tax_exempt_yield)
            amount = balances[aid] * rate
            balances[aid] += amount
            growth += amount
            if account.kind == "taxable" and aid == savings_target:
                basis[aid] = min(balances[aid], basis[aid] + max(ZERO, savings))
        gross_assets = sum(balances.values(), ZERO) + insurance_cash_value
        nw = gross_assets - sum(liability_balances.values(), ZERO)
        rows.append(YearRow(year=year, client_age=year - ctx.client_birth_year,
                            spouse_age=year - ctx.spouse_birth_year,
                            phase=_phase(year, ctx), inflows=inflows, outflows=outflows,
                            taxes=total_tax, investment_growth=growth,
                            withdrawals=withdrawals, savings=savings,
                            shortfall=shortfall, account_balances=dict(balances),
                            liability_balances=liability_balances,
                            net_worth=nw, estate_value=gross_assets, trace=(trace_rows + ([{
                                "step": "contributions", "employee": str(employee_deferrals),
                                "employer": str(employer_contributions), "roth_conversion": str(roth_conversion),
                                "liability_interest": str(liability_interest),
                                "insurance_premiums": str(insurance_premiums),
                                "insurance_death_benefits": str(insurance_death_benefits),
                                "insurance_cash_value": str(insurance_cash_value)}] if trace else []))))
    warnings = list(facts.metadata.get("data_quality_warnings", []))
    if first_shortfall is not None:
        warnings.append(f"Plan liquidity is depleted in {first_shortfall}")
    return Projection(household_id=facts.household_id, start_year=ctx.start_year,
                      rows=rows, ending_net_worth=rows[-1].net_worth if rows else ZERO,
                      lifetime_taxes=lifetime_taxes,
                      first_shortfall_year=first_shortfall, warnings=warnings)
