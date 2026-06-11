"""Number and timestamp formatting matching the original JS backend exactly."""

import math
from datetime import UTC, datetime


def js_round(x: float) -> int:
    # Matches JS Math.round (half toward +inf), not Python's banker's rounding.
    return math.floor(x + 0.5)


def iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fmt_usd(n: float) -> str:
    return ("-$" if n < 0 else "$") + f"{abs(js_round(n)):,}"
