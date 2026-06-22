"""Layered financial tools architecture for the demo backend.

Exposed tools:
- simulate: deterministic-seed Monte Carlo engine
- rebalance: deterministic mock rebalancer with model and tax/gains budgets
"""

from allworth_api.financial_tools.compute import rebalance, simulate
from allworth_api.financial_tools.performance import modified_dietz_return, period_performance_from_values
from allworth_api.financial_tools.router import router
from allworth_api.financial_tools.tools import (
    FINANCIAL_TOOL_DEFINITIONS,
    FINANCIAL_TOOL_LABELS,
    FINANCIAL_TOOL_NAMES,
    is_financial_tool,
    run_financial_tool,
)

__all__ = [
    "FINANCIAL_TOOL_DEFINITIONS",
    "FINANCIAL_TOOL_LABELS",
    "FINANCIAL_TOOL_NAMES",
    "is_financial_tool",
    "modified_dietz_return",
    "period_performance_from_values",
    "rebalance",
    "router",
    "run_financial_tool",
    "simulate",
]
