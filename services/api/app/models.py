from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class RiskTolerance(str, Enum):
    conservative = "conservative"
    moderate = "moderate"
    growth = "growth"


class HouseholdProfile(BaseModel):
    primary_age: int = Field(default=45, ge=18, le=100)
    spouse_age: int | None = Field(default=None, ge=18, le=100)
    retirement_age: int = Field(default=65, ge=40, le=80)
    annual_income: float = Field(default=225000, ge=0)
    annual_expenses: float = Field(default=145000, ge=0)
    portfolio_value: float = Field(default=1250000, ge=0)
    annual_savings: float = Field(default=45000, ge=0)
    filing_status: Literal["single", "married_filing_jointly"] = "married_filing_jointly"
    effective_tax_rate: float = Field(default=0.28, ge=0, le=0.6)
    risk_tolerance: RiskTolerance = RiskTolerance.moderate


class PortfolioPosition(BaseModel):
    symbol: str
    name: str = ""
    asset_class: str = "Equity"
    value: float = Field(ge=0)
    cost_basis: float = Field(default=0, ge=0)
    target_weight: float = Field(default=0, ge=0, le=1)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    household: HouseholdProfile = Field(default_factory=HouseholdProfile)
    portfolio: list[PortfolioPosition] = Field(default_factory=list)


class MetricCard(BaseModel):
    label: str
    value: str
    tone: Literal["good", "warning", "danger", "neutral"] = "neutral"
    detail: str = ""


class AdvisorAction(BaseModel):
    title: str
    priority: Literal["high", "medium", "low"] = "medium"
    rationale: str


class ToolResult(BaseModel):
    tool: str
    summary: str
    cards: list[MetricCard] = Field(default_factory=list)
    actions: list[AdvisorAction] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    disclaimers: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    intent: str
    result: ToolResult
    suggested_prompts: list[str] = Field(default_factory=list)


class PlanningRunRequest(BaseModel):
    analysis: Literal[
        "retirement_readiness",
        "roth_conversion",
        "social_security",
        "withdrawal_strategy",
        "tax_optimization",
    ]
    household: HouseholdProfile = Field(default_factory=HouseholdProfile)


class PortfolioRunRequest(BaseModel):
    analysis: Literal[
        "portfolio_review",
        "tax_loss_harvesting",
        "wash_sale_check",
        "drift_analysis",
    ]
    household: HouseholdProfile = Field(default_factory=HouseholdProfile)
    portfolio: list[PortfolioPosition] = Field(default_factory=list)

