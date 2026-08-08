"""Boundary models shared by every planning-engine module."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


ZERO = Decimal("0")


class EngineModel(BaseModel):
    model_config = ConfigDict(extra="allow", use_enum_values=True)


class TimingKind(str, Enum):
    NEVER = "never"
    IMMEDIATELY = "immediately"
    CALENDAR_YEAR = "calendar_year"
    CLIENT_AGE = "client_age"
    SPOUSE_AGE = "spouse_age"
    CLIENT_RETIREMENT = "client_retirement"
    SPOUSE_RETIREMENT = "spouse_retirement"
    CLIENT_DEATH = "client_death"
    SPOUSE_DEATH = "spouse_death"
    FIRST_DEATH = "first_death"
    SECOND_DEATH = "second_death"
    DURATION_YEARS = "duration_years"


class Timing(EngineModel):
    kind: TimingKind = TimingKind.IMMEDIATELY
    value: int | None = None

    @model_validator(mode="after")
    def validate_value(self):
        needs_value = self.kind in {
            TimingKind.CALENDAR_YEAR, TimingKind.CLIENT_AGE,
            TimingKind.SPOUSE_AGE, TimingKind.DURATION_YEARS,
        }
        if needs_value and self.value is None:
            raise ValueError(f"{self.kind} requires value")
        if self.kind == TimingKind.DURATION_YEARS and self.value is not None and self.value < 1:
            raise ValueError("duration_years must be positive")
        return self


class Indexing(EngineModel):
    mode: Literal["none", "inflation", "custom"] = "inflation"
    custom_rate: Decimal | None = None
    start_indexing: Literal["immediately", "at_start_year"] = "immediately"

    @model_validator(mode="after")
    def custom_requires_rate(self):
        if self.mode == "custom" and self.custom_rate is None:
            raise ValueError("custom indexing requires custom_rate")
        return self


class Ownership(EngineModel):
    owner_type: str = "joint"
    client_pct: Decimal = Decimal("1")
    entity_id: UUID | None = None


class GrowthRates(EngineModel):
    pre_retire_gross: Decimal | None = None
    post_retire_gross: Decimal | None = None

    def __init__(self, pre_retire_gross=None, post_retire_gross=None, **data):
        if pre_retire_gross is not None: data["pre_retire_gross"] = pre_retire_gross
        if post_retire_gross is not None: data["post_retire_gross"] = post_retire_gross
        super().__init__(**data)


class Person(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    role: str = "client"
    first_name: str = ""
    last_name: str = ""
    date_of_birth: date
    retirement_age: int = 65
    assumed_age_of_death: int = 95
    flat_tax_rate: Decimal | None = None
    core_cash_growth_rate: Decimal = ZERO


class Household(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = "Household"


class Holding(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    account_number: str | None = None
    symbol: str | None = None
    cusip: str | None = None
    description: str = "Holding"
    security_type: str | None = None
    asset_class: str = "Unclassified"
    sector: str | None = None
    quantity: Decimal = ZERO
    current_price: Decimal = ZERO
    market_value: Decimal = ZERO
    cost_basis: Decimal | None = None
    weight: Decimal | None = None
    as_of_date: date | None = None
    source: str = "tho.Account_Daily_Holdings"


class Account(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    kind: str = "taxable"
    name: str = "Account"
    value: Decimal = ZERO
    tax_basis: Decimal = ZERO
    owner: str = "client"
    growth_rate: Decimal = Decimal("0.05")
    income_yield: Decimal = ZERO
    tax_exempt_yield: Decimal = ZERO
    liquidity: int = 2
    apply_rmd: bool = False
    exclude_from_planning: bool = False
    holdings: list[Holding] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_account_values(cls, data):
        if not isinstance(data, dict): return data
        data = dict(data)
        if "value" not in data:
            data["value"] = data.get("total_value", data.get("holdings_value", data.get("nav", 0)))
            data["value"] = Decimal(str(data["value"] or 0)) + Decimal(str(data.get("cash_value", 0) or 0))
        growth = data.get("growth")
        if "growth_rate" not in data and growth:
            data["growth_rate"] = (growth.get("pre_retire_gross") if isinstance(growth, dict)
                                   else getattr(growth, "pre_retire_gross", None)) or Decimal("0.05")
        return data


class TaxableInvestmentAccount(Account): kind: str = "taxable"
class CashAccount(Account): kind: str = "cash"; liquidity: int = 1
class QualifiedRetirementAccount(Account): kind: str = "qualified"; apply_rmd: bool = True
class RothIRA(Account): kind: str = "roth"
class Plan529(Account): kind: str = "529"
class HedgeFundInterest(Account): kind: str = "hedge_fund"; liquidity: int = 4
class PrivateEquityInterest(Account): kind: str = "private_equity"; liquidity: int = 5


class RealEstate(Account):
    kind: str = "real_estate"
    liquidity: int = 5

    @model_validator(mode="before")
    @classmethod
    def normalize_re(cls, data):
        if isinstance(data, dict):
            data = dict(data); data.setdefault("name", data.get("property_name", "Real Estate")); data.setdefault("value", data.get("current_value", 0))
        return data


class LongShortStrategy(Account): kind: str = "long_short"
class ModelPortfolio(EngineModel): name: str; weights: dict[str, Decimal] = Field(default_factory=dict)
class AssetClass(EngineModel): name: str; expected_return: Decimal = ZERO; std_dev: Decimal = ZERO


class Flow(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = "Flow"
    amount: Decimal = ZERO
    starts: Timing = Field(default_factory=Timing)
    ends: Timing = Field(default_factory=lambda: Timing(kind=TimingKind.NEVER))
    indexing: Indexing = Field(default_factory=Indexing)
    owner: str = "client"
    taxable: bool = True
    required: bool = True
    kind: str = "other"

    @model_validator(mode="before")
    @classmethod
    def normalize_flow_values(cls, data):
        if not isinstance(data, dict): return data
        data = dict(data)
        if "amount" not in data:
            data["amount"] = data.get("annual_amount", data.get("current_amount", 0))
        return data


class SalaryBonus(Flow): kind: str = "salary"
class SocialSecurity(Flow): kind: str = "social_security"; taxable: bool = True
class LivingExpenses(Flow): kind: str = "living"; required: bool = True
class EducationExpense(Flow): kind: str = "education"; required: bool = True


class Transfer(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = "Transfer"
    annual_amount: Decimal = ZERO
    source_account: str | UUID | None = None
    destination_account: str | UUID | None = None
    roth_conversion: bool = False
    starts: Timing = Field(default_factory=Timing)
    ends: Timing = Field(default_factory=lambda: Timing(kind=TimingKind.NEVER))


class Mortgage(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    institution: str = "Lender"
    current_balance: Decimal = ZERO
    interest_rate: Decimal = ZERO
    term_years: int = 30
    payment_frequency: str = "monthly"
    repayment_type: str = "p_and_i"


class LifeInsurancePolicy(EngineModel):
    id: UUID = Field(default_factory=uuid4)
    policy_name: str = "Policy"
    policy_number: str | None = None
    institution: str | None = None
    purchase_date: date | None = None
    issue_year: int | None = None
    policy_type: str = "term"
    term_ends_at_retirement: bool = False
    term_years: int | None = None
    insured: str = "client"
    owner: str = "client"
    ownership: Ownership | None = None
    beneficiary: str | None = None
    contingent_beneficiary: str | None = None
    under_our_management: bool = False
    exclude_from_planning: bool = False
    current_death_benefit: Decimal = ZERO
    current_cash_value: Decimal = ZERO
    basis: Decimal = ZERO
    cash_value_growth_rate: Decimal = ZERO
    annual_premium: Decimal = ZERO
    premium_term_years: int | None = None
    premium_payer: str = "client"
    exclusion_amount: Decimal = ZERO
    proceeds_reinvested_at: str | None = None
    proceeds_realization_model: str | None = None
    source: str | None = None
    source_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_policy_values(cls, data):
        if not isinstance(data, dict): return data
        data = dict(data)
        if "current_death_benefit" not in data:
            data["current_death_benefit"] = data.get("death_benefit", data.get("benefit", 0))
        if "current_cash_value" not in data:
            data["current_cash_value"] = data.get("cash_value", 0)
        if "annual_premium" not in data:
            data["annual_premium"] = data.get("premium", 0)
        if "basis" not in data:
            data["basis"] = data.get("cost_basis", 0)
        purchase_date = data.get("purchase_date")
        if "issue_year" not in data and purchase_date:
            try:
                data["issue_year"] = date.fromisoformat(str(purchase_date)[:10]).year
            except ValueError:
                pass
        return data


class DeathEvent(EngineModel):
    person: str
    age: int


class Assumptions(EngineModel):
    start_year: int = Field(default_factory=lambda: date.today().year)
    inflation_rate: Decimal = Decimal("0.03")
    tax_mode: Literal["flat_tax", "form_1040"] = "form_1040"
    flat_tax_rate: Decimal = Decimal("0.25")
    state_income_tax_rate: Decimal = ZERO
    local_income_tax_rate: Decimal = ZERO
    save_pct: Decimal = Decimal("1")
    liquidation_strategy: str = "by_type"
    plan_end_age: int = 100

    @model_validator(mode="before")
    @classmethod
    def normalize_assumption_names(cls, data):
        if not isinstance(data, dict): return data
        data = dict(data)
        if "liquidation_strategy" not in data and "deficit_strategy" in data:
            data["liquidation_strategy"] = data["deficit_strategy"]
        if "save_pct" not in data and "surplus_save_pct" in data:
            data["save_pct"] = data["surplus_save_pct"]
        return data


class Facts(EngineModel):
    household_id: UUID = Field(default_factory=uuid4)
    name: str = "Household"
    people: list[Person] = Field(default_factory=list)
    accounts: list[Account] = Field(default_factory=list)
    income: list[Flow] = Field(default_factory=list)
    expenses: list[Flow] = Field(default_factory=list)
    assumptions: Assumptions = Field(default_factory=Assumptions)
    goals: list[dict[str, Any]] = Field(default_factory=list)
    household: Household | None = None
    real_estate: list[RealEstate] = Field(default_factory=list)
    liabilities: list[Mortgage] = Field(default_factory=list)
    insurance: list[LifeInsurancePolicy] = Field(default_factory=list)
    transfers: list[Transfer] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def normalize_facts_tree(cls, data):
        if not isinstance(data, dict): return data
        data = dict(data)
        household = data.get("household")
        if "name" not in data and household:
            data["name"] = household.get("name", "Household") if isinstance(household, dict) else household.name
        if "household_id" not in data and household:
            data["household_id"] = household.get("id") if isinstance(household, dict) else household.id
        if "income" not in data and "incomes" in data: data["income"] = data["incomes"]
        accounts = list(data.get("accounts", []))
        existing = {str(value) for x in accounts
                    if (value := (x.get("id") if isinstance(x, dict) else getattr(x, "id", None))) is not None}
        for asset in data.get("real_estate", []):
            asset_id = str(asset.get("id")) if isinstance(asset, dict) else str(getattr(asset, "id", ""))
            if not asset_id or asset_id == "None" or asset_id not in existing:
                accounts.append(asset); existing.add(asset_id)
        data["accounts"] = accounts
        return data


class TaxInput(EngineModel):
    filing_status: str = "mfj"
    wages: Decimal = ZERO
    interest_taxable: Decimal = ZERO
    interest_exempt: Decimal = ZERO
    dividends_qualified: Decimal = ZERO
    dividends_ordinary: Decimal = ZERO
    st_gain: Decimal = ZERO
    lt_gain: Decimal = ZERO
    retirement_distributions: Decimal = ZERO
    roth_conversion: Decimal = ZERO
    social_security_gross: Decimal = ZERO
    se_income: Decimal = ZERO
    itemized: Decimal | None = None
    capital_loss_carryforward: Decimal = ZERO
    penalties: Decimal = ZERO
    collectibles_gain: Decimal = ZERO
    unrecaptured_1250: Decimal = ZERO
    sec1256_gain: Decimal = ZERO
    iso_bargain_element: Decimal = ZERO
    mtc_carryforward: Decimal = ZERO


class TaxBreakdown(EngineModel):
    federal_ordinary: Decimal = ZERO
    federal_cap_gains: Decimal = ZERO
    niit: Decimal = ZERO
    additional_medicare: Decimal = ZERO
    fica_ss: Decimal = ZERO
    fica_medicare: Decimal = ZERO
    se_tax: Decimal = ZERO
    state: Decimal = ZERO
    local: Decimal = ZERO
    penalties: Decimal = ZERO
    total: Decimal = ZERO
    marginal_rate: Decimal = ZERO
    effective_rate: Decimal = ZERO
    detail: dict[str, Any] = Field(default_factory=dict)


class YearRow(EngineModel):
    year: int
    client_age: int | None = None
    spouse_age: int | None = None
    phase: str = "current"
    inflows: Decimal = ZERO
    outflows: Decimal = ZERO
    taxes: Decimal = ZERO
    investment_growth: Decimal = ZERO
    withdrawals: Decimal = ZERO
    savings: Decimal = ZERO
    shortfall: Decimal = ZERO
    account_balances: dict[str, Decimal] = Field(default_factory=dict)
    liability_balances: dict[str, Decimal] = Field(default_factory=dict)
    net_worth: Decimal = ZERO
    estate_value: Decimal = ZERO
    trace: list[dict[str, Any]] = Field(default_factory=list)


class Projection(EngineModel):
    household_id: UUID
    start_year: int
    rows: list[YearRow]
    ending_net_worth: Decimal
    lifetime_taxes: Decimal
    first_shortfall_year: int | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def summary(self):
        """Compatibility view used by report and solver layers."""
        return self
