"""Form-1040-style planning tax calculator."""

from decimal import Decimal

from ..models import TaxBreakdown, TaxInput

D = Decimal
ZERO = D("0")


def _status(status: str) -> str:
    return "mfj" if status in {"mfj", "married_filing_jointly"} else status


def _bracket_tax(amount: Decimal, brackets: list[list[Decimal]]) -> tuple[Decimal, Decimal]:
    amount = max(ZERO, amount)
    tax = ZERO
    rate = ZERO
    for i, (floor, bracket_rate) in enumerate(brackets):
        ceiling = brackets[i + 1][0] if i + 1 < len(brackets) else None
        if amount <= floor:
            break
        taxable = amount - floor if ceiling is None else min(amount, ceiling) - floor
        tax += max(ZERO, taxable) * bracket_rate
        rate = bracket_rate
    return tax, rate


def _ss_taxable(gross: Decimal, provisional_without_half_ss: Decimal,
                thresholds: list[Decimal]) -> Decimal:
    if gross <= 0:
        return ZERO
    provisional = provisional_without_half_ss + gross / 2
    low, high = thresholds
    if provisional <= low:
        return ZERO
    first = min(gross / 2, (provisional - low) / 2)
    if provisional <= high:
        return max(ZERO, first)
    return min(gross * D("0.85"), first + (provisional - high) * D("0.85"))


def _preferential_tax(ordinary_taxable: Decimal, gains: Decimal,
                      thresholds: list[Decimal]) -> tuple[Decimal, dict]:
    gains = max(ZERO, gains)
    zero_room = max(ZERO, thresholds[1] - ordinary_taxable)
    at_zero = min(gains, zero_room)
    remaining = gains - at_zero
    fifteen_room = max(ZERO, thresholds[2] - max(ordinary_taxable, thresholds[1]))
    at_fifteen = min(remaining, fifteen_room)
    at_twenty = max(ZERO, remaining - at_fifteen)
    return at_fifteen * D("0.15") + at_twenty * D("0.20"), {
        "ltcg_at_0pct": at_zero, "ltcg_at_15pct": at_fifteen,
        "ltcg_at_20pct": at_twenty,
    }


def compute_taxes(inp: TaxInput, tables, mode: str = "form_1040",
                  flat_tax_rate: Decimal = D("0.25")) -> TaxBreakdown:
    status = _status(inp.filing_status)
    wages, se_income = D(inp.wages), D(inp.se_income)
    se_base = max(ZERO, se_income) * D("0.9235")
    ss_rate, med_rate = tables.fica_rates["ss"], tables.fica_rates["medicare"]
    fica_ss = min(max(ZERO, wages), tables.ss_wage_base) * ss_rate
    fica_medicare = max(ZERO, wages) * med_rate
    se_ss = min(se_base, max(ZERO, tables.ss_wage_base - max(ZERO, wages))) * ss_rate * 2
    se_med = se_base * med_rate * 2
    se_tax = se_ss + se_med
    sec1256_lt = inp.sec1256_gain * D("0.60")
    sec1256_st = inp.sec1256_gain * D("0.40")
    st = inp.st_gain + sec1256_st
    lt = inp.lt_gain + sec1256_lt
    # Net ST and LT; losses offset the other character before the $3k cap.
    if st < 0 and lt > 0:
        offset = min(-st, lt); st += offset; lt -= offset
    elif lt < 0 and st > 0:
        offset = min(-lt, st); lt += offset; st -= offset
    prior_loss = max(ZERO, inp.capital_loss_carryforward)
    if prior_loss:
        used = min(prior_loss, max(ZERO, lt) + max(ZERO, st))
        take_st = min(used, max(ZERO, st)); st -= take_st; lt -= used - take_st
        prior_loss -= used
    net_loss = max(ZERO, -(st + lt))
    loss_against_ordinary = min(D("3000"), net_loss + prior_loss)
    carryforward = max(ZERO, net_loss + prior_loss - loss_against_ordinary)
    pre_ss = (wages + se_income + inp.interest_taxable + inp.interest_exempt +
              inp.dividends_ordinary + inp.dividends_qualified + max(ZERO, st) +
              max(ZERO, lt) + inp.retirement_distributions + inp.roth_conversion)
    ss_taxable = _ss_taxable(inp.social_security_gross, pre_ss,
                             tables.ss_taxability_thresholds[status])
    half_se = se_tax / 2
    agi = (wages + se_income + inp.interest_taxable + inp.dividends_ordinary +
           inp.dividends_qualified + max(ZERO, st) + max(ZERO, lt) +
           inp.retirement_distributions + inp.roth_conversion + ss_taxable - half_se -
           loss_against_ordinary)
    if mode == "flat_tax":
        federal = max(ZERO, agi) * D(flat_tax_rate)
        total = federal + fica_ss + fica_medicare + se_tax + inp.penalties
        return TaxBreakdown(federal_ordinary=federal, fica_ss=fica_ss,
                            fica_medicare=fica_medicare, se_tax=se_tax,
                            penalties=inp.penalties, total=total,
                            marginal_rate=D(flat_tax_rate),
                            effective_rate=total / agi if agi > 0 else ZERO,
                            detail={"agi": agi, "ss_taxable": ss_taxable,
                                    "carryforward_out": carryforward})
    standard = tables.standard_deduction[status]
    itemized = D(inp.itemized) if inp.itemized is not None else ZERO
    deduction = max(standard, itemized)
    taxable = max(ZERO, agi - deduction)
    pref = max(ZERO, inp.dividends_qualified + max(ZERO, lt))
    ordinary_taxable = max(ZERO, taxable - pref)
    ordinary_tax, marginal = _bracket_tax(ordinary_taxable, tables.brackets[status])
    cap_tax, cap_detail = _preferential_tax(ordinary_taxable, pref,
                                            tables.ltcg_thresholds[status])
    # Collectibles are netted against ST losses before their 28% basket.
    collectibles_taxed = max(ZERO, inp.collectibles_gain + min(ZERO, inp.st_gain))
    cap_tax += collectibles_taxed * min(D("0.28"), marginal or D("0.28"))
    cap_tax += max(ZERO, inp.unrecaptured_1250) * min(D("0.25"), marginal or D("0.25"))
    magi = agi + inp.interest_exempt
    nii = max(ZERO, inp.interest_taxable + inp.dividends_ordinary +
              inp.dividends_qualified + max(ZERO, st) + max(ZERO, lt))
    niit = min(nii, max(ZERO, magi - tables.niit_threshold[status])) * D("0.038")
    addl_medicare = max(ZERO, wages + se_base - tables.additional_medicare_threshold[status]) * D("0.009")
    # Planning-grade AMT/MTC lifecycle, including ISO bargain element.
    amti = taxable + max(ZERO, inp.iso_bargain_element)
    exemption = max(ZERO, tables.amt["exemption"][status] -
                    max(ZERO, amti - tables.amt["phaseout"][status]) * D("0.25"))
    amt_base = max(ZERO, amti - exemption)
    split = tables.amt["rate_break"]
    tentative_amt = min(amt_base, split) * D("0.26") + max(ZERO, amt_base - split) * D("0.28")
    regular = ordinary_tax + cap_tax
    amt = max(ZERO, tentative_amt - regular)
    mtc_used = min(max(ZERO, inp.mtc_carryforward), max(ZERO, regular - tentative_amt))
    federal = regular + amt - mtc_used
    total = federal + niit + addl_medicare + fica_ss + fica_medicare + se_tax + inp.penalties
    detail = {
        "agi": agi, "taxable_income": taxable,
        "deduction_taken": "itemized" if itemized > standard else "standard",
        "deduction_amount": deduction, "ss_taxable": ss_taxable,
        "capital_loss_used_vs_ordinary": loss_against_ordinary,
        "carryforward_out": carryforward, "net_lt_gain_taxed": max(ZERO, lt),
        "lt_from_1256": sec1256_lt, "st_from_1256": sec1256_st,
        "collectibles_taxed": collectibles_taxed,
        "adjustments": {"half_se_tax": half_se}, "amt": amt,
        "mtc_used": mtc_used,
        "mtc_carryforward_out": max(ZERO, inp.mtc_carryforward - mtc_used + amt),
        **cap_detail,
    }
    return TaxBreakdown(federal_ordinary=ordinary_tax + amt - mtc_used,
                        federal_cap_gains=cap_tax, niit=niit,
                        additional_medicare=addl_medicare, fica_ss=fica_ss,
                        fica_medicare=fica_medicare, se_tax=se_tax,
                        penalties=inp.penalties, total=total,
                        marginal_rate=marginal,
                        effective_rate=total / agi if agi > 0 else ZERO,
                        detail=detail)
