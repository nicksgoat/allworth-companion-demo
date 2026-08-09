"""Database-backed account analysis endpoints."""

from __future__ import annotations

from flask import Blueprint, request
from sqlalchemy.exc import SQLAlchemyError

from investments.models.bond import Bond
from investments.routers._helpers import api_error, db_session
from investments.services import db_analyzer
from investments.services import transactions as tx_service

bp = Blueprint("account_analysis", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bond_to_dict(bond: Bond) -> dict:
    """Serialize a Bond to the shape the frontend Dashboard/Holdings tab expects."""
    return {
        "symbol": bond.symbol or "",
        "cusip": bond.cusip or "",
        "description": bond.description or "",
        "account_number": bond.account_id or "",
        "account_name": bond.account_name or "",
        "coupon": bond.coupon or 0.0,
        "price": bond.price or 0.0,
        "quantity": bond.quantity or 0.0,
        "market_value": bond.effective_market_value(),
        "weight": bond.weight,
        "annual_income": bond.effective_annual_income(),
        "yield_to_worst": bond.yield_to_worst or 0.0,
        "effective_duration": bond.effective_duration or 0.0,
        "ratings": [
            {
                "agency": r.agency,
                "current": r.current,
                "previous": r.previous,
                "effective_date": r.effective_date.isoformat() if r.effective_date else None,
            }
            for r in bond.ratings
        ],
        "maturity_date": bond.maturity_date.isoformat() if bond.maturity_date else "",
        "call_date": bond.call_date.isoformat() if bond.call_date else None,
        "callable": bond.callable,
        "issuer": bond.issuer or "",
        "sector": bond.sector or "",
        "state": bond.state or "",
    }


def _list_to_record(items: list[dict], key: str, val: str) -> dict:
    """Convert [{key: k, val: v}, ...] to {k: v}."""
    return {item[key]: item[val] for item in items if key in item and val in item}


def _normalize_dashboard(raw: dict, bonds: list[Bond]) -> dict:
    """Convert analytics.build_dashboard() output to the frontend Dashboard shape."""
    kpis = raw.get("kpis", {})
    return {
        "portfolio_id": "",
        "bonds": [_bond_to_dict(b) for b in bonds],
        "kpis": {
            "market_value": kpis.get("market_value", 0) or 0,
            "annual_income": kpis.get("annual_income", 0) or 0,
            "avg_coupon": kpis.get("average_coupon") or 0,
            "avg_yield": kpis.get("average_yield") or 0,
            "avg_duration": kpis.get("average_duration") or 0,
            "avg_rating": kpis.get("average_rating") or "N/A",
            "callable_pct": kpis.get("callable_pct") or 0,
            "health_score": kpis.get("health_score") or 0,
        },
        "maturity_ladder": _list_to_record(raw.get("maturity_ladder", []), "bucket", "market_value"),
        "call_ladder": _list_to_record(raw.get("call_ladder", []), "bucket", "market_value"),
        "credit_distribution": _list_to_record(raw.get("credit_distribution", []), "rating", "market_value"),
        "sector_allocation": _list_to_record(raw.get("sector_allocation", []), "label", "market_value"),
        "state_allocation": _list_to_record(raw.get("state_allocation", []), "label", "market_value"),
        "issuer_concentration": _list_to_record(raw.get("issuer_concentration", []), "label", "market_value"),
        # cash_flow returns [{year, principal, income}]; frontend expects [{month, principal, income}]
        "cash_flow_projection": [
            {"month": str(row["year"]), "principal": row["principal"], "income": row["income"]}
            for row in raw.get("cash_flow", [])
        ],
        "monthly_income": _list_to_record(raw.get("monthly_income", []), "month", "income"),
        "coupon_distribution": _list_to_record(raw.get("coupon_distribution", []), "bucket", "count"),
        "yield_distribution": _list_to_record(raw.get("yield_distribution", []), "bucket", "count"),
        "upcoming_calls": [],
        "upcoming_maturities": [],
        "rating_changes": [],
        "ladder_quality_score": raw.get("ladder_quality_score", 0) or 0,
        "portfolio_health_score": kpis.get("health_score") or 0,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@bp.get("/analyze/account/<account_number>")
def analyze_account(account_number: str) -> dict:
    return _analyze_accounts([account_number])


@bp.get("/analyze/accounts")
def analyze_accounts() -> dict:
    account_numbers = request.args.getlist("account_numbers")
    if not account_numbers:
        raise api_error(422, "At least one account_numbers query parameter is required.")
    return _analyze_accounts(account_numbers)


def _analyze_accounts(account_numbers: list[str]) -> dict:
    with db_session() as session:
        try:
            result = db_analyzer.analyze_account_numbers(session, account_numbers)
        except RuntimeError as exc:
            raise api_error(503, str(exc)) from exc
        except SQLAlchemyError as exc:
            raise api_error(502, f"Database query failed: {exc.__class__.__name__}") from exc

    if result is None:
        raise api_error(404, "Account not found in tho.Account_Daily_Holdings.")

    return {
        "account_number": result.account_number,
        "account_name": result.account_name,
        "account_numbers": result.account_numbers,
        "account_names": result.account_names,
        "holdings_count": result.holdings_count,
        "enriched_count": result.enriched_count,
        "dashboard": _normalize_dashboard(result.dashboard, result.bonds),
        "summary": result.summary,
        "field_requirements": result.fields_required,
    }


@bp.get("/analyze/field-requirements")
def field_requirements() -> dict:
    return db_analyzer.FIELD_REQUIREMENTS


# ---------------------------------------------------------------------------
# Transactions endpoints (Tamarac-style activity history)
# ---------------------------------------------------------------------------

@bp.get("/transactions/account/<account_number>")
def transactions_account(account_number: str) -> dict:
    return _transactions([account_number])


@bp.get("/transactions/accounts")
def transactions_accounts() -> dict:
    account_numbers = request.args.getlist("account_numbers")
    if not account_numbers:
        raise api_error(422, "At least one account_numbers query parameter is required.")
    return _transactions(account_numbers)


def _transactions(account_numbers: list[str]) -> dict:
    with db_session() as session:
        try:
            rows = tx_service.get_transactions(session, account_numbers)
        except SQLAlchemyError as exc:
            raise api_error(502, f"Database query failed: {exc.__class__.__name__}") from exc

    return {
        "account_numbers": list(dict.fromkeys(a.strip() for a in account_numbers if a.strip())),
        "count": len(rows),
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Appraisal / Holdings endpoints
# ---------------------------------------------------------------------------

@bp.get("/appraisal/account/<account_number>")
def appraisal_account(account_number: str) -> dict:
    return _appraisal_accounts([account_number])


@bp.get("/appraisal/accounts")
def appraisal_accounts() -> dict:
    account_numbers = request.args.getlist("account_numbers")
    if not account_numbers:
        raise api_error(422, "At least one account_numbers query parameter is required.")
    return _appraisal_accounts(account_numbers)


def _appraisal_accounts(account_numbers: list[str]) -> dict:
    with db_session() as session:
        try:
            result = db_analyzer.get_appraisal_holdings(session, account_numbers)
        except RuntimeError as exc:
            raise api_error(503, str(exc)) from exc
        except SQLAlchemyError as exc:
            raise api_error(502, f"Database query failed: {exc.__class__.__name__}") from exc

    if result is None:
        raise api_error(404, "Account not found in tho.Account_Daily_Holdings.")

    return {
        "account_number": result.account_number,
        "account_name": result.account_name,
        "account_numbers": result.account_numbers,
        "account_names": result.account_names,
        "as_of_date": result.as_of_date,
        "holdings_count": len(result.rows),
        "rows": result.rows,
    }
