"""Canonical bond model and supporting value objects.

The :class:`Bond` model is the single source of truth used by analytics
and the API. It is deliberately provider-agnostic: the ingest service
maps Tamarac (or any future provider) onto these fields. Every numeric
field is optional because real-world exports are sparse.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, computed_field


# Ordered best -> worst. Used to compute an average credit quality and to
# rank downgrades/upgrades independent of the rating agency scale.
_RATING_SCALE: list[str] = [
    "Aaa", "Aa1", "Aa2", "Aa3", "A1", "A2", "A3",
    "Baa1", "Baa2", "Baa3", "Ba1", "Ba2", "Ba3",
    "B1", "B2", "B3", "Caa1", "Caa2", "Caa3", "Ca", "C", "D",
]

# Map common S&P / Fitch style ratings onto the Moody's scale so a mixed
# portfolio can be scored on one axis.
_RATING_ALIASES: dict[str, str] = {
    "AAA": "Aaa", "AA+": "Aa1", "AA": "Aa2", "AA-": "Aa3",
    "A+": "A1", "A": "A2", "A-": "A3",
    "BBB+": "Baa1", "BBB": "Baa2", "BBB-": "Baa3",
    "BB+": "Ba1", "BB": "Ba2", "BB-": "Ba3",
    "B+": "B1", "B": "B2", "B-": "B3", "CCC+": "Caa1", "CCC": "Caa2", "CCC-": "Caa3",
    "CC": "Ca",
}


def normalize_rating(raw: str | None) -> str | None:
    """Return a canonical Moody's-scale rating, or ``None`` if unknown."""
    if not raw:
        return None
    token = str(raw).strip()
    if not token or token.upper() in {"NR", "N/A", "NA", "WR", "-"}:
        return None
    if token in _RATING_SCALE:
        return token
    return _RATING_ALIASES.get(token.upper())


def rating_rank(rating: str | None) -> int | None:
    """Numeric rank where 0 is the highest quality. ``None`` if unknown."""
    canonical = normalize_rating(rating)
    if canonical is None:
        return None
    return _RATING_SCALE.index(canonical)


def rank_to_rating(rank: float) -> str:
    """Inverse of :func:`rating_rank` for a (possibly fractional) rank."""
    idx = max(0, min(len(_RATING_SCALE) - 1, round(rank)))
    return _RATING_SCALE[idx]


class CreditRating(BaseModel):
    """A single agency's rating with optional prior value for change tracking."""

    agency: str
    current: str | None = None
    previous: str | None = None
    effective_date: date | None = None        # when CURRENT rating took effect
    previous_effective_date: date | None = None  # when PREVIOUS rating took effect

    @computed_field
    @property
    def changed(self) -> bool:
        return bool(self.current and self.previous and self.current != self.previous)


class RatingChange(BaseModel):
    """A detected rating movement, surfaced by monitoring."""

    cusip: str | None
    description: str
    agency: str
    from_rating: str
    to_rating: str
    effective_date: date | None
    direction: str  # "downgrade" | "upgrade"
    notches: int


class Bond(BaseModel):
    """Normalized fixed-income holding."""

    # Identity
    symbol: str | None = None
    cusip: str | None = None
    description: str = ""
    account_id: str | None = None
    account_name: str | None = None

    # Pricing & valuation
    coupon: float | None = Field(default=None, description="Annual coupon rate, percent")
    price: float | None = Field(default=None, description="Current clean price per 100")
    quantity: float | None = Field(default=None, description="Face / par held")
    market_value: float | None = None
    weight: float | None = Field(default=None, description="Portfolio weight, percent")
    annual_income: float | None = None

    # Yield & risk
    yield_to_worst: float | None = None
    effective_duration: float | None = None

    # Dates
    issue_date: date | None = None
    maturity_date: date | None = None
    call_date: date | None = None
    next_income_date: date | None = None
    first_coupon_date: date | None = None

    # Call features
    callable: bool = False
    call_price: float | None = None

    # Credit
    ratings: list[CreditRating] = Field(default_factory=list)

    # Classification
    asset_class: str | None = None
    sector: str | None = None
    broad_sector: str | None = None
    segment: str | None = None
    issuer: str | None = None
    state: str | None = None
    income_frequency: str | None = None

    # Tax
    federal_taxable: bool | None = None
    state_taxable: bool | None = None

    # Corporate bond quality scoring
    corporate_quality_score: float | None = None
    corporate_quality_components: dict[str, float] | None = None

    @computed_field
    @property
    def best_rating(self) -> str | None:
        """Highest-quality rating across all agencies on the bond.

        Returns the highest-quality rating whose string is recognisable on the
        canonical Moody's/Fitch scale.  If no rating is recognisable (e.g. the
        security master carries a non-standard string like ``"WR"`` or ``"AA1"``)
        the raw string of the first available rating is returned so the UI
        always has something meaningful to display rather than falling back to
        ``"NR"``.
        """
        ranked = [(rating_rank(r.current), r.current) for r in self.ratings]
        recognised = [(rank, value) for rank, value in ranked if rank is not None]
        if recognised:
            return min(recognised, key=lambda item: item[0])[1]
        # Fallback: return the first raw string so nothing is silently dropped.
        for _, value in ranked:
            if value:
                return value
        return None

    @computed_field
    @property
    def is_investment_grade(self) -> bool | None:
        rank = rating_rank(self.best_rating)
        if rank is None:
            return None
        return rank <= _RATING_SCALE.index("Baa3")

    def effective_market_value(self) -> float:
        """Market value, deriving it from price * quantity when missing."""
        if self.market_value is not None:
            return self.market_value
        if self.price is not None and self.quantity is not None:
            return self.price / 100.0 * self.quantity
        return 0.0

    def effective_annual_income(self) -> float:
        """Annual income, deriving it from coupon * face when missing."""
        if self.annual_income is not None:
            return self.annual_income
        if self.coupon is not None and self.quantity is not None:
            return self.coupon / 100.0 * self.quantity
        return 0.0
