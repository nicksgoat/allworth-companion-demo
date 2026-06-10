from __future__ import annotations

import os
import sys
from pathlib import Path

from . import demo_tools
from .models import HouseholdProfile, PortfolioPosition, ToolResult


class ToolAdapter:
    """Single boundary between product API and planning engines."""

    def __init__(self) -> None:
        self.mode = os.getenv("MOBILEAPP_TOOL_MODE", "demo").lower()
        self.plugin_root = Path(os.getenv("ALLWORTH_PLUGIN_ROOT", "/home/stevenluong/Allworth_Plugin"))
        if self.mode == "plugin" and self.plugin_root.exists():
            python_root = self.plugin_root / "python"
            if str(python_root) not in sys.path:
                sys.path.insert(0, str(python_root))

    def catalog(self) -> list[dict[str, str]]:
        return [
            {"id": "retirement_readiness", "family": "planning", "label": "Retirement readiness"},
            {"id": "roth_conversion", "family": "planning", "label": "Roth conversion"},
            {"id": "social_security", "family": "planning", "label": "Social Security timing"},
            {"id": "tax_optimization", "family": "planning", "label": "Tax optimization"},
            {"id": "portfolio_review", "family": "portfolio", "label": "Portfolio review"},
            {"id": "tax_loss_harvesting", "family": "portfolio", "label": "Tax-loss harvesting"},
            {"id": "wash_sale_check", "family": "portfolio", "label": "Wash sale check"},
        ]

    async def run_planning(self, analysis: str, household: HouseholdProfile) -> ToolResult:
        # Keep this deterministic for MVP. The plugin mode hook belongs here.
        if analysis == "roth_conversion":
            return demo_tools.roth_conversion(household)
        if analysis == "social_security":
            return demo_tools.social_security(household)
        if analysis == "tax_optimization":
            return demo_tools.tax_optimization(household)
        return demo_tools.retirement_readiness(household)

    async def run_portfolio(self, analysis: str, portfolio: list[PortfolioPosition]) -> ToolResult:
        if analysis == "tax_loss_harvesting":
            return demo_tools.tax_loss_harvesting(portfolio)
        if analysis == "wash_sale_check":
            return demo_tools.wash_sale_check()
        return demo_tools.portfolio_review(portfolio)


adapter = ToolAdapter()

