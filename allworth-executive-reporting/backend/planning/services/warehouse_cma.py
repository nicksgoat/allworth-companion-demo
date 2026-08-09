"""Overlay versioned PlanEngine CMAs with governed Synapse volatility."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from planengine.capital_market import load_capital_market_assumptions, match_asset_class

D = Decimal


def resolve_capital_market_assumptions(session: Session | None) -> dict[str, Any]:
    table = load_capital_market_assumptions()
    warnings: list[str] = []
    for values in table["asset_classes"].values():
        values["expected_return_source"] = table["expected_return_source"]
        values["volatility_source"] = table["default_volatility_source"]

    if session is not None:
        try:
            rows = session.execute(text("""
                SELECT [Asset Class] AS asset_class,
                       MAX(CAST([Volatility] AS float)) AS volatility
                FROM [tav].[Asset_Class_Historical_Volatility]
                WHERE [Asset Class] IS NOT NULL AND [Volatility] IS NOT NULL
                GROUP BY [Asset Class]
            """)).mappings().all()
            applied = 0
            for row in rows:
                name = match_asset_class(row.get("asset_class"), table)
                if not name or row.get("volatility") is None: continue
                volatility = D(str(row["volatility"]))
                if volatility > 2: volatility /= D("100")
                if D("0") <= volatility < D("2"):
                    table["asset_classes"][name]["std_dev"] = volatility
                    table["asset_classes"][name]["volatility_source"] = "tav.Asset_Class_Historical_Volatility"
                    applied += 1
            if not applied:
                warnings.append("Synapse returned no CMA volatility rows matching configured asset classes")
        except SQLAlchemyError as exc:
            warnings.append(f"Synapse CMA volatility refresh unavailable ({type(exc).__name__})")

    table["warnings"] = warnings
    table["source"] = (
        "versioned Allworth expected returns/correlation policy with Synapse volatility overlays"
    )
    return table
