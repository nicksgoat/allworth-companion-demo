"""Bond Ladder endpoints."""

from __future__ import annotations

from datetime import date

from flask import Blueprint, request
from sqlalchemy.exc import SQLAlchemyError

from investments.routers._helpers import api_error, db_session
from investments.services import bond_ladder as bl_service
from investments.services import transactions as tx_service

bp = Blueprint("bond_ladder", __name__, url_prefix="/api")


def _parse_date(value: str | None, name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise api_error(400, f"Invalid {name}: expected YYYY-MM-DD.") from exc


@bp.get("/bond-ladder")
def get_bond_ladder() -> dict:
    """Return all Bond Ladder accounts and their holdings (cached up to 30 min)."""
    strategy = request.args.get("strategy") or None
    sort_by = request.args.get("sort_by", "maturity")
    with db_session() as session:
        try:
            result = bl_service.get_bond_ladder(session)
        except SQLAlchemyError as exc:
            raise api_error(502, f"Database query failed: {exc}") from exc
        except RuntimeError as exc:
            raise api_error(503, str(exc)) from exc

    bonds = result.all_bonds(strategy=strategy, sort_by=sort_by)

    account_summaries = [
        {
            "account_number": a.account_number,
            "account_name": a.account_name or "",
            "strategy": a.strategy,
            "bond_count": a.bond_count,
            "total_market_value": round(a.total_market_value, 2),
        }
        for a in result.accounts
        if strategy is None or a.strategy == strategy
    ]

    fetched_at = bl_service.cache_fetched_at()

    return {
        "total_accounts": len(account_summaries),
        "total_bonds": len(bonds),
        "total_market_value": round(sum(a["total_market_value"] for a in account_summaries), 2),
        "strategies": result.strategies,
        "accounts": account_summaries,
        "bonds": bonds,
        "cache_age_seconds": bl_service.cache_age_seconds(),
        "fetched_at": fetched_at.isoformat() + "Z" if fetched_at else None,
    }


@bp.get("/bond-ladder/called")
def bond_ladder_called() -> dict:
    """Review recently called bonds across Bond Ladder accounts.

    A called bond is identified by a redemption transaction (notes containing
    ``REDEMP`` and not ``MATURED``). The result includes the current cash test
    and same-quantity bond BUY match used by the dedicated review page.
    """
    try:
        days = int(request.args.get("days", 30))
    except ValueError as exc:
        raise api_error(400, "days must be an integer.") from exc
    if not 1 <= days <= 365:
        raise api_error(400, "days must be between 1 and 365.")
    start_date = _parse_date(request.args.get("start_date"), "start_date")
    end_date = _parse_date(request.args.get("end_date"), "end_date")
    force_refresh = (request.args.get("force_refresh") or "").lower() in {"1", "true", "yes"}

    with db_session() as session:
        try:
            return tx_service.get_called_bonds_review(
                session,
                days=days,
                start_date=start_date,
                end_date=end_date,
                force_refresh=force_refresh,
            )
        except SQLAlchemyError as exc:
            raise api_error(502, f"Database query failed: {exc}") from exc
        except ValueError as exc:
            raise api_error(400, str(exc)) from exc
        except RuntimeError as exc:
            raise api_error(503, str(exc)) from exc


@bp.post("/bond-ladder/refresh")
def refresh_bond_ladder() -> dict:
    """Invalidate the cache and immediately re-fetch from the database."""
    bl_service.invalidate_cache()
    with db_session() as session:
        try:
            result = bl_service.get_bond_ladder(session)
        except SQLAlchemyError as exc:
            raise api_error(502, f"Database query failed: {exc}") from exc
        except RuntimeError as exc:
            raise api_error(503, str(exc)) from exc

    fetched_at = bl_service.cache_fetched_at()
    return {
        "total_accounts": result.total_accounts,
        "total_bonds": result.total_bonds,
        "fetched_at": fetched_at.isoformat() + "Z" if fetched_at else None,
    }
