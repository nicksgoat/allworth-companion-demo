"""FastAPI router exposing the layered financial tools."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from allworth_api.financial_tools.compute import simulate
from allworth_api.financial_tools.data import DEFAULT_MODEL_ID
from allworth_api.financial_tools.tools import run_financial_tool

router = APIRouter(prefix="/tools", tags=["financial-tools"])


class SimulateRequest(BaseModel):
    initial_value: float
    annual_contribution: float = 0.0
    expected_annual_return: float = 0.07
    annual_volatility: float = 0.15
    years: int = 20
    n_simulations: int = 10_000
    goal_amount: float | None = None


class RebalanceRequest(BaseModel):
    model_id: str = DEFAULT_MODEL_ID
    account_id: str | None = None
    current_holdings: list[dict] | None = None
    target_allocation: dict[str, float] | None = None
    realized_gains_budget: dict[str, float] | None = None
    tax_budget: dict[str, float] | None = None


@router.post("/simulate")
def simulate_tool(req: SimulateRequest):
    return simulate(**req.model_dump())


@router.post("/rebalance")
def rebalance_tool(req: RebalanceRequest):
    return run_financial_tool("rebalance", req.model_dump(), "maya")
