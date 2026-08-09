"""Pure, deterministic financial planning engine.

The package intentionally performs no I/O and has no FastAPI or SQLAlchemy
dependencies.  API and warehouse adapters live in :mod:`app`.
"""

from .engine import run_projection
from .models import Facts, Projection, YearRow

__all__ = ["Facts", "Projection", "YearRow", "run_projection"]
