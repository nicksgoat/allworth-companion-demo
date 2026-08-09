"""Dashboard, analytics, and AI summary endpoints."""

from __future__ import annotations

from flask import Blueprint, request

from investments.routers._helpers import api_error
from investments.services import ai_summary, analytics
from investments.services.store import store

bp = Blueprint("dashboard", __name__, url_prefix="/api")


def _bonds_or_404(portfolio_id: str):
    accounts = request.args.get("accounts")
    account_ids = [a for a in (accounts.split(",") if accounts else []) if a]
    bonds = store.bonds_for_accounts(portfolio_id, account_ids)
    if bonds is None:
        raise api_error(404, "Portfolio not found.")
    return bonds


@bp.get("/dashboard/<portfolio_id>")
def dashboard(portfolio_id: str) -> dict:
    return analytics.build_dashboard(_bonds_or_404(portfolio_id))


@bp.get("/maturity/<portfolio_id>")
def maturity(portfolio_id: str) -> dict:
    return {"maturity_ladder": analytics.maturity_ladder(_bonds_or_404(portfolio_id))}


@bp.get("/calls/<portfolio_id>")
def calls(portfolio_id: str) -> dict:
    bonds = _bonds_or_404(portfolio_id)
    return {
        "call_ladder": analytics.call_ladder(bonds),
        "upcoming_calls": analytics.upcoming_calls(bonds),
    }


@bp.get("/income/<portfolio_id>")
def income(portfolio_id: str) -> dict:
    return {"monthly_income": analytics.monthly_income(_bonds_or_404(portfolio_id))}


@bp.get("/cashflow/<portfolio_id>")
def cashflow(portfolio_id: str) -> dict:
    return {"cash_flow": analytics.cash_flow_projection(_bonds_or_404(portfolio_id))}


@bp.get("/credit/<portfolio_id>")
def credit(portfolio_id: str) -> dict:
    bonds = _bonds_or_404(portfolio_id)
    return {
        "credit_distribution": analytics.credit_distribution(bonds),
        "rating_changes": analytics.rating_changes(bonds),
    }


@bp.get("/summary/<portfolio_id>")
def summary(portfolio_id: str) -> dict:
    return ai_summary.generate_summary(_bonds_or_404(portfolio_id))
