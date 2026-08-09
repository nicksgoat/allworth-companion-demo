"""Domain models.

The :class:`Bond` model is the normalized representation the whole app
speaks. The ingest service is the only place that knows about the raw
Tamarac schema and maps it onto these structures.
"""

from .bond import Bond, CreditRating, RatingChange

__all__ = ["Bond", "CreditRating", "RatingChange"]
