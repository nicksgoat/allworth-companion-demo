"""Resolve Monte Carlo inputs from governed Synapse household data.

The resolver follows the advisor-plugin planning contract but never invents
household financial values. Missing inputs are returned explicitly for advisor
review. Capital-market assumptions are the reviewed reference set; client
weights and balances come from Synapse holdings.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from planengine.models import Facts
from planengine.montecarlo import AssetClass
from planengine.capital_market import canonical_asset_class, build_correlation_matrix
from planning.services.warehouse_cma import resolve_capital_market_assumptions

D = Decimal


def _facts_inputs(facts: Facts) -> dict[str, Any]:
    client = next((person for person in facts.people if person.role == "client"), None)
    unverified = set(facts.metadata.get("unverified_monte_carlo_inputs", []))
    today = date.today()
    annual_income = sum((flow.amount for flow in facts.income if flow.kind != "social_security"), D("0"))
    annual_spending = sum((flow.amount for flow in facts.expenses if flow.required), D("0"))
    return {
        "current_age": (today.year - client.date_of_birth.year -
                        ((today.month, today.day) < (client.date_of_birth.month, client.date_of_birth.day))
                        if client and "current_age" not in unverified else None),
        "retirement_age": (client.retirement_age
                           if client and "retirement_age" not in unverified else None),
        "life_expectancy": client.assumed_age_of_death if client else None,
        "annual_income": annual_income if annual_income > 0 else None,
        "annual_spending": annual_spending if annual_spending > 0 else None,
        "total_wealth": sum((account.value for account in facts.accounts
                             if not account.exclude_from_planning), D("0")),
    }


def resolve_monte_carlo_inputs(session: Session | None, facts: Facts) -> dict[str, Any]:
    base = _facts_inputs(facts)
    source = facts.metadata.get("source", "planning")
    source_id = facts.metadata.get("source_id")
    avhhid = facts.metadata.get("household_avhhid")
    holdings: list[dict] = []
    warehouse_fields: dict[str, Any] = {}
    warnings: list[str] = []
    warnings.extend(str(row) for row in facts.metadata.get("data_quality_warnings", []) if row)
    cma_table = resolve_capital_market_assumptions(session)
    warnings.extend(cma_table.get("warnings", []))

    if session is not None and source_id:
        if not avhhid:
            row = session.execute(text(
                "SELECT TOP 1 [AVHHID],[Expected_Retirement_Date__c],[AUM] "
                "FROM [tho].[Current_Household_Fact] WHERE [HHID]=:household_id"),
                {"household_id": source_id}).mappings().first()
            if row:
                avhhid = row.get("AVHHID")
                warehouse_fields["household_aum"] = row.get("AUM")
                warehouse_fields["expected_retirement_date_key"] = row.get("Expected_Retirement_Date__c")
        if avhhid:
            rows = session.execute(text("""
                SELECT [Asset_Class] AS asset_class,
                       SUM(ABS(CASE
                           WHEN ISNULL([Current_Price],0) * ISNULL([Quantity],0) <> 0
                               THEN [Current_Price] * [Quantity]
                           WHEN ISNULL([Weight],0) <> 0
                               THEN [Total_Account_Value] *
                                    CASE WHEN ABS([Weight]) > 1 THEN [Weight]/100.0 ELSE [Weight] END
                           ELSE 0 END)) AS market_value,
                       MAX([As_Of_Date]) AS as_of_date
                FROM [tho].[Account_Daily_Holdings]
                WHERE [avhhid]=:avhhid AND [Current_Date_Filter]=1
                GROUP BY [Asset_Class]
            """), {"avhhid": avhhid}).mappings().all()
            holdings = [dict(row) for row in rows if D(str(row.get("market_value") or 0)) > 0]
            profile = session.execute(text("""
                SELECT TOP 1 [Risk_Tolerance__c],[Investment_Time_Horizon_BD__c],
                       [Federal_Tax_Bracket_BD__c],[Client_Annual_Income_BD__c],
                       [State_of_Primary_Residence],[Date] AS observed_at
                FROM [tho].[Current_Account_Demographic]
                WHERE [Primary_Household_ID]=:avhhid
                ORDER BY [Date] DESC
            """), {"avhhid": avhhid}).mappings().first()
            if profile: warehouse_fields.update(dict(profile))
        else:
            warnings.append("No AVHHID mapping was found; current holdings could not be resolved")

    if not holdings:
        snapshot = facts.metadata.get("monte_carlo_inputs", {})
        holdings = snapshot.get("holding_classes", [])
    if not holdings:
        warnings.append("No governed asset-class holdings are available; Monte Carlo needs an advisor-reviewed allocation")

    warehouse_income = warehouse_fields.get("Client_Annual_Income_BD__c")
    if base["annual_income"] is None and warehouse_income not in (None, ""):
        amount = D(str(warehouse_income))
        if amount > 0: base["annual_income"] = amount

    totals: dict[str, Decimal] = {}
    as_of_values = []
    for row in holdings:
        name = canonical_asset_class(row.get("asset_class"), cma_table)
        totals[name] = totals.get(name, D("0")) + D(str(row.get("market_value") or 0))
        if row.get("as_of_date"): as_of_values.append(str(row["as_of_date"]))
    total_market_value = sum(totals.values(), D("0"))
    if (base["total_wealth"] or D("0")) <= 0 and total_market_value > 0:
        base["total_wealth"] = total_market_value
        warnings.append("Plan account balances were empty; total wealth uses current Synapse holdings market value")
    asset_classes = []
    for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True):
        assumption = cma_table["asset_classes"][name]
        expected, volatility = assumption["expected_return"], assumption["std_dev"]
        weight = value / total_market_value if total_market_value else D("0")
        asset_classes.append({"name": name, "expected_return": str(expected),
                              "std_dev": str(volatility), "weight": str(weight),
                              "market_value": str(value),
                              "assumption_source": cma_table["source"],
                              "expected_return_source": assumption["expected_return_source"],
                              "volatility_source": assumption["volatility_source"],
                              "weight_source": "tho.Account_Daily_Holdings" if source_id else source})

    class_names = [row["name"] for row in asset_classes]
    correlation = build_correlation_matrix(class_names, cma_table)
    weights = np.asarray([float(row["weight"]) for row in asset_classes])
    expected_returns = np.asarray([float(row["expected_return"]) for row in asset_classes])
    volatilities = np.asarray([float(row["std_dev"]) for row in asset_classes])
    portfolio_expected_return = float(weights @ expected_returns) if len(weights) else None
    covariance = np.outer(volatilities, volatilities) * np.asarray(correlation)
    portfolio_volatility = float(np.sqrt(max(0.0, weights @ covariance @ weights))) if len(weights) else None

    required = {"current_age": base["current_age"], "retirement_age": base["retirement_age"],
                "life_expectancy": base["life_expectancy"], "annual_spending": base["annual_spending"],
                "total_wealth": base["total_wealth"] if base["total_wealth"] > 0 else None,
                "asset_allocation": asset_classes or None}
    missing = [key for key, value in required.items() if value in (None, [], {})]
    inputs = {
        **base, "household_source_id": source_id, "household_avhhid": str(avhhid) if avhhid else None,
        "risk_tolerance": warehouse_fields.get("Risk_Tolerance__c"),
        "investment_time_horizon": warehouse_fields.get("Investment_Time_Horizon_BD__c"),
        "federal_tax_bracket": warehouse_fields.get("Federal_Tax_Bracket_BD__c"),
        "warehouse_annual_income": warehouse_fields.get("Client_Annual_Income_BD__c"),
        "resident_state": warehouse_fields.get("State_of_Primary_Residence"),
        "asset_classes": asset_classes, "correlation_matrix": correlation,
        "cma_version": cma_table["version"], "cma_as_of": cma_table["as_of"],
        "cma_source": cma_table["source"],
        "portfolio_expected_return": portfolio_expected_return,
        "portfolio_volatility": portfolio_volatility,
        "holding_classes": holdings, "holdings_as_of": max(as_of_values) if as_of_values else None,
        "ready": not missing, "missing_required_inputs": missing, "warnings": warnings,
        "provenance": {
            "current_age": "sfp.Contact.Birthdate or tho.Contact_Demographic.dob via versioned facts",
            "retirement_age": "tho.Contact_Demographic.retire_date or tho.Current_Household_Fact.Expected_Retirement_Date__c via versioned facts",
            "life_expectancy": "versioned PlanEngine advisor assumption",
            "annual_income": "sfp.Contact.FinServ__AnnualIncome__c or tho.Current_Account_Demographic.Client_Annual_Income_BD__c",
            "annual_spending": "unambiguous sfp.Plan_Review__c.Monthly_Expenses__c or advisor-entered versioned facts",
            "total_wealth": "versioned financial accounts, falling back only to current holdings market value when empty",
            "holdings": "tho.Account_Daily_Holdings current-date snapshot",
            "capital_market_assumptions": cma_table["source"],
        },
    }
    return inputs


def monte_carlo_parameters(inputs: dict) -> tuple[list[AssetClass], np.ndarray | None]:
    cma = [AssetClass(name=row["name"], expected_return=float(row["expected_return"]),
                      std_dev=float(row["std_dev"]), weight=float(row["weight"]))
           for row in inputs.get("asset_classes", [])]
    corr = np.asarray(inputs.get("correlation_matrix"), dtype=float) if cma else None
    return cma, corr
