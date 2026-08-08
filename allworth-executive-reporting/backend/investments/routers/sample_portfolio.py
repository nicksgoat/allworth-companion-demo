"""Sample bond portfolio endpoints.

Generates an illustrative laddered bond portfolio for a named strategy from the
DataWarehouse universe, returns the fact-sheet metrics as JSON, and exports a
one-page PDF report.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, Response, request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from investments.models.bond import rating_rank
from investments.routers._helpers import api_error, db_session
from investments.services import pdf_report, proposal_report
from investments.services import sample_portfolio as sp

bp = Blueprint("sample_portfolio", __name__, url_prefix="/api/sample-portfolio")


class GenerateRequest(BaseModel):
    strategy: str = Field(..., description="Strategy key, e.g. 'municipal-1-5'")
    target_value: float = Field(default=sp.DEFAULT_TARGET_VALUE, gt=0)
    tax_rate: float = Field(default=0.37, ge=0, lt=1)
    as_of: date | None = None
    exclude_unrated: bool = Field(default=False, description="Exclude bonds with no recognised Fitch rating (NR). Off by default because Fitch coverage is sparse.")
    lot_size: int = Field(default=5_000, description="Bond face-value lot increment (e.g. 1000, 5000, 10000, 50000, 100000)")
    state: str | None = Field(default=None, description="Optional municipal state preference, e.g. CA")


class ProposalRequest(GenerateRequest):
    """Sample-portfolio request plus proposal cover metadata."""

    client_name: str | None = Field(default=None, description="Client shown in the 'Regarding' line")
    prepared_by: str | None = Field(default=None, description="Advisor shown in the 'Prepared By' line")
    proposal_title: str | None = Field(default=None, description="Custom proposal title (defaults to the strategy label)")
    proposal_id: str | None = Field(default=None, description="Optional proposal identifier")


def _parse_request(model: type[GenerateRequest]) -> GenerateRequest:
    try:
        return model.model_validate(request.get_json(force=True, silent=False) or {})
    except ValidationError as exc:
        raise api_error(422, str(exc)) from exc


@bp.get("/strategies")
def list_strategies() -> dict:
    """List the available sample-portfolio strategies."""
    return {
        "strategies": [
            {
                "key": s.key,
                "label": s.label,
                "asset": s.asset,
                "tax_exempt": s.tax_exempt,
                "min_year": s.min_year,
                "max_year": s.max_year,
                "target_count": s.target_count,
            }
            for s in sp.STRATEGIES.values()
        ]
    }


def _serialize(portfolio: sp.SamplePortfolio) -> dict:
    return {
        "strategy": {
            "key": portfolio.strategy.key,
            "label": portfolio.strategy.label,
            "asset": portfolio.strategy.asset,
            "description": portfolio.strategy.description,
        },
        "target_value": portfolio.target_value,
        "as_of": portfolio.as_of.isoformat(),
        "metrics": portfolio.metrics,
        "warnings": portfolio.warnings,
        "bonds": [
            {
                "symbol": b.symbol,
                "cusip": b.cusip,
                "description": b.description,
                "coupon": b.coupon,
                "price": b.price,
                "quantity": b.quantity,
                "market_value": b.market_value,
                "annual_income": b.annual_income,
                "yield_to_worst": b.yield_to_worst,
                "maturity_date": b.maturity_date.isoformat() if b.maturity_date else None,
                "rating": b.best_rating if rating_rank(b.best_rating) is not None else None,
                "rating_agency": b.ratings[0].agency if b.ratings and rating_rank(b.best_rating) is not None else None,
                "previous_rating": b.ratings[0].previous if b.ratings else None,
                "rating_effective_date": b.ratings[0].effective_date.isoformat() if b.ratings and b.ratings[0].effective_date else None,
                "corporate_quality_score": b.corporate_quality_score,
                "corporate_quality_components": b.corporate_quality_components,
                "sector": b.sector,
                "broad_sector": b.broad_sector,
                "segment": b.segment,
                "state": b.state,
                "callable": b.callable,
            }
            for b in portfolio.bonds
        ],
    }


def _generate(session: Session, req: GenerateRequest) -> sp.SamplePortfolio:
    try:
        return sp.generate(
            session,
            req.strategy,
            target_value=req.target_value,
            tax_rate=req.tax_rate,
            as_of=req.as_of,
            exclude_unrated=req.exclude_unrated,
            lot_size=req.lot_size,
            state=req.state,
        )
    except ValueError as exc:
        raise api_error(422, str(exc)) from exc
    except SQLAlchemyError as exc:
        raise api_error(502, f"Database query failed: {exc}") from exc
    except RuntimeError as exc:
        raise api_error(503, str(exc)) from exc


@bp.post("/generate")
def generate_portfolio() -> dict:
    """Generate a sample portfolio and return its metrics + holdings as JSON."""
    req = _parse_request(GenerateRequest)
    with db_session() as session:
        return _serialize(_generate(session, req))


@bp.post("/pdf")
def generate_pdf() -> Response:
    """Generate the one-page PDF report for a sample portfolio."""
    req = _parse_request(GenerateRequest)
    with db_session() as session:
        portfolio = _generate(session, req)
    try:
        pdf_bytes = pdf_report.render_pdf(portfolio)
    except pdf_report.PdfUnavailableError as exc:
        raise api_error(503, str(exc)) from exc

    filename = f"{portfolio.strategy.key}-sample-portfolio.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp.post("/proposal")
def generate_proposal() -> Response:
    """Generate a client-style proposal PDF for a sample portfolio."""
    req = _parse_request(ProposalRequest)
    with db_session() as session:
        portfolio = _generate(session, req)
    try:
        pdf_bytes = proposal_report.render_pdf(
            portfolio,
            client_name=req.client_name,
            prepared_by=req.prepared_by,
            proposal_title=req.proposal_title,
            proposal_id=req.proposal_id,
        )
    except proposal_report.ProposalUnavailableError as exc:
        raise api_error(503, str(exc)) from exc

    filename = f"{portfolio.strategy.key}-bond-ladder-proposal.pdf"
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
