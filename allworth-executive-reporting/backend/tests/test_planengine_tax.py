"""Hand-computed 1040 cases against the planning tax calculator.

Every expected value below is derived by hand from the 2026 constants in
planengine/tax/tables/2026.json so a change to either the math or the tables
fails loudly.

Run from the backend/ directory:

    python -m pytest tests/test_planengine_tax.py -v
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from planengine.models import TaxInput
from planengine.tax.calculator import compute_taxes
from planengine.tax.irmaa import irmaa_surcharge
from planengine.tax.tables import load_tables, project_tables

D = Decimal
TABLES = load_tables(2026)


def taxes(**kwargs):
    mode = kwargs.pop("mode", "form_1040")
    return compute_taxes(TaxInput(**kwargs), TABLES, mode)


class TestOrdinaryBrackets:
    def test_mfj_wages_into_12_pct_bracket(self):
        # wages 132,200 − SD 32,200 = 100,000 taxable, all ordinary.
        # 24,800×10% + 75,200×12% = 2,480 + 9,024 = 11,504.
        result = taxes(filing_status="mfj", wages=D("132200"))
        assert result.federal_ordinary == D("11504.00")
        assert result.marginal_rate == D("0.12")

    def test_single_wages_into_22_pct_bracket(self):
        # wages 96,100 − SD 16,100 = 80,000 taxable.
        # 12,400×10% + 38,000×12% + 29,600×22% = 1,240 + 4,560 + 6,512 = 12,312.
        result = taxes(filing_status="single", wages=D("96100"))
        assert result.federal_ordinary == D("12312.00")
        assert result.marginal_rate == D("0.22")

    def test_income_below_standard_deduction_owes_no_federal(self):
        result = taxes(filing_status="mfj", retirement_distributions=D("30000"))
        assert result.federal_ordinary == D("0")
        assert result.federal_cap_gains == D("0")

    def test_roth_conversion_is_ordinary_income(self):
        # conversion 100,000 − SD 32,200 = 67,800 taxable.
        # 2,480 + 43,000×12% = 2,480 + 5,160 = 7,640.
        result = taxes(filing_status="mfj", roth_conversion=D("100000"))
        assert result.federal_ordinary == D("7640.00")
        assert result.detail["agi"] == D("100000")


class TestSocialSecurityTaxability:
    def test_below_first_threshold_untaxed(self):
        # provisional = 10,000 + 20,000/2 = 20,000 ≤ 32,000 (mfj).
        result = taxes(filing_status="mfj", retirement_distributions=D("10000"),
                       social_security_gross=D("20000"))
        assert result.detail["ss_taxable"] == D("0")

    def test_between_thresholds_fifty_pct_phase_in(self):
        # provisional = 20,000 + 40,000/2 = 40,000; (40,000−32,000)/2 = 4,000.
        result = taxes(filing_status="mfj", retirement_distributions=D("20000"),
                       social_security_gross=D("40000"))
        assert result.detail["ss_taxable"] == D("4000")

    def test_above_second_threshold_caps_at_85_pct(self):
        # Very high other income → 85% of gross is taxable.
        result = taxes(filing_status="mfj", retirement_distributions=D("300000"),
                       social_security_gross=D("40000"))
        assert result.detail["ss_taxable"] == D("40000") * D("0.85")


class TestCapitalGainsStacking:
    def test_ltcg_within_zero_bracket(self):
        # Ordinary taxable 0; 50,000 LTCG < 98,900 zero-rate ceiling (mfj).
        result = taxes(filing_status="mfj", retirement_distributions=D("32200"),
                       lt_gain=D("50000"))
        assert result.federal_ordinary == D("0")
        assert result.federal_cap_gains == D("0")
        assert result.detail["ltcg_at_0pct"] == D("50000")

    def test_ltcg_spills_into_15_pct(self):
        # Ordinary taxable 0; 150,000 LTCG → 98,900 at 0%, 51,100 at 15% = 7,665.
        result = taxes(filing_status="mfj", retirement_distributions=D("32200"),
                       lt_gain=D("150000"))
        assert result.detail["ltcg_at_0pct"] == D("98900")
        assert result.detail["ltcg_at_15pct"] == D("51100")
        assert result.federal_cap_gains == D("51100") * D("0.15")

    def test_ordinary_income_pushes_gains_off_zero_bracket(self):
        # Ordinary taxable 98,900 exactly fills the 0% room → all gains at 15%.
        result = taxes(filing_status="mfj", retirement_distributions=D("131100"),
                       lt_gain=D("10000"))
        assert result.detail["ltcg_at_0pct"] == D("0")
        assert result.detail["ltcg_at_15pct"] == D("10000")

    def test_st_loss_offsets_lt_gain_before_cap(self):
        result = taxes(filing_status="mfj", st_gain=D("-10000"), lt_gain=D("4000"))
        # Net −6,000: 3,000 against ordinary now, 3,000 carried forward.
        assert result.detail["capital_loss_used_vs_ordinary"] == D("3000")
        assert result.detail["carryforward_out"] == D("3000")

    def test_carryforward_in_consumed_against_gains(self):
        result = taxes(filing_status="mfj", lt_gain=D("20000"),
                       capital_loss_carryforward=D("20000"))
        assert result.detail["net_lt_gain_taxed"] == D("0")
        assert result.detail["carryforward_out"] == D("0")


class TestSurtaxes:
    def test_niit_applies_to_lesser_of_nii_and_magi_excess(self):
        # MAGI 320,000; excess over 250,000 = 70,000; NII 20,000 → 20,000×3.8%.
        result = taxes(filing_status="mfj", wages=D("300000"),
                       interest_taxable=D("20000"))
        assert result.niit == D("20000") * D("0.038")

    def test_no_niit_without_investment_income(self):
        result = taxes(filing_status="mfj", wages=D("400000"))
        assert result.niit == D("0")

    def test_fica_capped_at_wage_base(self):
        result = taxes(filing_status="single", wages=D("300000"))
        assert result.fica_ss == D("184500") * D("0.062")
        assert result.fica_medicare == D("300000") * D("0.0145")


class TestFlatTaxMode:
    def test_flat_rate_times_agi(self):
        result = taxes(mode="flat_tax", filing_status="mfj", wages=D("100000"))
        fica = D("100000") * (D("0.062") + D("0.0145"))
        assert result.total == D("100000") * D("0.25") + fica


class TestIrmaa:
    def test_base_tier_has_no_surcharge(self):
        assert irmaa_surcharge(D("100000"), "mfj", TABLES).annual_total == D("0")

    def test_tier_boundaries_select_correct_surcharge(self):
        at_ceiling = irmaa_surcharge(D("218000"), "mfj", TABLES)
        above_ceiling = irmaa_surcharge(D("218001"), "mfj", TABLES)
        assert at_ceiling.annual_total == D("0")
        assert above_ceiling.part_b == D("1040.4")
        assert above_ceiling.part_d == D("168")

    def test_surcharge_monotonic_in_magi(self):
        points = [D(x) for x in (0, 218000, 274001, 342001, 410001, 750001, 2000000)]
        surcharges = [irmaa_surcharge(p, "mfj", TABLES).annual_total for p in points]
        assert surcharges == sorted(surcharges)


class TestProjectedTables:
    def test_thresholds_inflate_beyond_base_year(self):
        future = project_tables(TABLES, 2036, D("0.03"))
        factor = (D("1.03")) ** 10
        assert future.standard_deduction["mfj"] == D("32200") * factor
        assert future.brackets["mfj"][1][0] == D("24800") * factor

    def test_base_year_returned_unchanged(self):
        assert project_tables(TABLES, 2026, D("0.03")) is TABLES
