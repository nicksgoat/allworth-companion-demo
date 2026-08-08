"""Tamarac ingestion and normalization.

Turns a raw Tamarac CSV/Excel export into canonical
:class:`~app.models.bond.Bond` objects. This is the *only* module
permitted to know about Tamarac column names. Everything is defensive:
the export is sparse, columns drift, and non-bond rows appear.
"""

from __future__ import annotations

import io
import math
import re
from datetime import date, datetime

import pandas as pd
from dateutil import parser as date_parser

from investments.models.bond import Bond, CreditRating

# Tamarac security types we treat as fixed income. Matching is fuzzy
# (lowercased substring) because the export is inconsistent.
_BOND_TYPE_HINTS = (
    "bond", "fixed income", "municipal", "treasury", "corporate",
    "agency", "cd", "certificate of deposit", "note", "muni",
)

# Canonical field -> list of acceptable source column names (case/space
# insensitive). First match wins.
_COLUMN_MAP: dict[str, tuple[str, ...]] = {
    "symbol": ("symbol", "ticker"),
    "cusip": ("cusip",),
    "description": ("security description", "description", "security name", "name"),
    "account_id": ("account number", "account id", "account"),
    "account_name": ("account name",),
    "security_type": ("security type", "type"),
    "coupon": ("interest rate", "coupon", "coupon rate"),
    "price": ("current price", "price"),
    "quantity": ("quantity", "face value", "par value", "shares"),
    "market_value": ("market value", "value"),
    "annual_income": ("security annual income", "annual income"),
    "yield_to_worst": ("current yield to worst", "yield to worst", "yield"),
    "effective_duration": ("effective duration", "duration"),
    "issue_date": ("issue date",),
    "maturity_date": ("maturity date", "maturity"),
    "call_date": ("call date", "next call date"),
    "call_price": ("call price",),
    "next_income_date": ("next income date",),
    "issuer": ("issuer", "issuer name"),
    "state": ("issue state", "state"),
    "sector": ("sector", "broad sector"),
    "asset_class": ("asset class", "broad asset class"),
    "income_frequency": ("income frequency",),
    "federal_taxable": ("federal taxable",),
    "state_taxable": ("state taxable",),
    "moodys": ("moody's rating", "moodys rating", "moody rating"),
    "moodys_prev": ("previous moody's rating", "previous moodys rating"),
    "moodys_date": ("moody's effective date", "moodys effective date"),
    "fitch": ("fitch rating",),
    "fitch_prev": ("previous fitch rating",),
    "fitch_date": ("fitch effective date",),
}


class IngestError(ValueError):
    """Raised when an upload cannot be parsed into any bonds."""


def _norm_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(name).strip().lower()).strip()


def _resolve_columns(df: pd.DataFrame) -> dict[str, str]:
    """Map canonical field names to the actual columns present in ``df``."""
    lookup = {_norm_key(col): col for col in df.columns}
    resolved: dict[str, str] = {}
    for field, candidates in _COLUMN_MAP.items():
        for candidate in candidates:
            actual = lookup.get(_norm_key(candidate))
            if actual is not None:
                resolved[field] = actual
                break
    return resolved


def _clean(value) -> object | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "n/a", "na", "-"}:
        return None
    return value


def _to_float(value) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[,$%\s]", "", str(value))
    if text in {"", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_date(value) -> date | None:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date_parser.parse(str(value), fuzzy=True).date()
    except (ValueError, OverflowError):
        return None


def _to_bool(value) -> bool | None:
    value = _clean(value)
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"yes", "y", "true", "1", "taxable"}:
        return True
    if text in {"no", "n", "false", "0", "exempt", "tax-exempt", "tax exempt"}:
        return False
    return None


def _is_bond_row(security_type: str | None, maturity: date | None, coupon: float | None) -> bool:
    if security_type:
        lowered = security_type.lower()
        if any(hint in lowered for hint in _BOND_TYPE_HINTS):
            return True
    # Fall back to structural signals: a maturity date plus a coupon is a
    # strong indicator of a fixed-income instrument even if the type is blank.
    return maturity is not None and coupon is not None


def _build_ratings(row: pd.Series, cols: dict[str, str]) -> list[CreditRating]:
    ratings: list[CreditRating] = []
    for agency, cur_key, prev_key, date_key in (
        ("Moody's", "moodys", "moodys_prev", "moodys_date"),
        ("Fitch", "fitch", "fitch_prev", "fitch_date"),
    ):
        current = _clean(row.get(cols.get(cur_key))) if cols.get(cur_key) else None
        if current is None:
            continue
        ratings.append(
            CreditRating(
                agency=agency,
                current=str(current).strip(),
                previous=(
                    str(_clean(row.get(cols[prev_key]))).strip()
                    if cols.get(prev_key) and _clean(row.get(cols[prev_key])) is not None
                    else None
                ),
                effective_date=_to_date(row.get(cols[date_key])) if cols.get(date_key) else None,
            )
        )
    return ratings


def _read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    name = (filename or "").lower()
    buffer = io.BytesIO(content)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(buffer, dtype=object)
    # CSV: tolerate ragged rows (real Tamarac exports have inconsistent
    # trailing delimiters), stray bad lines, and a UTF-8 BOM. The python
    # engine is more forgiving than the C engine for these files.
    return pd.read_csv(
        buffer,
        dtype=object,
        skip_blank_lines=True,
        encoding="utf-8-sig",
        engine="python",
        on_bad_lines="skip",
    )


def parse_tamarac(content: bytes, filename: str = "upload.csv") -> list[Bond]:
    """Parse a Tamarac export into canonical bonds.

    Raises :class:`IngestError` when nothing parseable is found.
    """
    try:
        df = _read_dataframe(content, filename)
    except Exception as exc:  # surfaced to caller as a 400
        raise IngestError(f"Could not read file: {exc}") from exc

    if df.empty:
        raise IngestError("The uploaded file contained no rows.")

    cols = _resolve_columns(df)
    if "description" not in cols and "cusip" not in cols and "symbol" not in cols:
        raise IngestError(
            "No recognizable security identifier columns "
            "(CUSIP / Symbol / Security Description) were found."
        )

    bonds: list[Bond] = []
    for _, row in df.iterrows():
        coupon = _to_float(row.get(cols["coupon"])) if "coupon" in cols else None
        maturity = _to_date(row.get(cols["maturity_date"])) if "maturity_date" in cols else None
        sec_type = (
            str(_clean(row.get(cols["security_type"])) or "")
            if "security_type" in cols
            else ""
        )
        if not _is_bond_row(sec_type, maturity, coupon):
            continue

        call_date = _to_date(row.get(cols["call_date"])) if "call_date" in cols else None
        bond = Bond(
            symbol=_clean(row.get(cols["symbol"])) if "symbol" in cols else None,
            cusip=_clean(row.get(cols["cusip"])) if "cusip" in cols else None,
            description=str(_clean(row.get(cols["description"])) or "Unknown Security")
            if "description" in cols
            else "Unknown Security",
            account_id=str(_clean(row.get(cols["account_id"])) or "") or None
            if "account_id" in cols
            else None,
            account_name=str(_clean(row.get(cols["account_name"])) or "") or None
            if "account_name" in cols
            else None,
            coupon=coupon,
            price=_to_float(row.get(cols["price"])) if "price" in cols else None,
            quantity=_to_float(row.get(cols["quantity"])) if "quantity" in cols else None,
            market_value=_to_float(row.get(cols["market_value"])) if "market_value" in cols else None,
            annual_income=_to_float(row.get(cols["annual_income"])) if "annual_income" in cols else None,
            yield_to_worst=_to_float(row.get(cols["yield_to_worst"])) if "yield_to_worst" in cols else None,
            effective_duration=_to_float(row.get(cols["effective_duration"])) if "effective_duration" in cols else None,
            issue_date=_to_date(row.get(cols["issue_date"])) if "issue_date" in cols else None,
            maturity_date=maturity,
            call_date=call_date,
            call_price=_to_float(row.get(cols["call_price"])) if "call_price" in cols else None,
            next_income_date=_to_date(row.get(cols["next_income_date"])) if "next_income_date" in cols else None,
            callable=call_date is not None,
            issuer=str(_clean(row.get(cols["issuer"])) or "") or None if "issuer" in cols else None,
            state=str(_clean(row.get(cols["state"])) or "") or None if "state" in cols else None,
            sector=str(_clean(row.get(cols["sector"])) or "") or None if "sector" in cols else None,
            asset_class=str(_clean(row.get(cols["asset_class"])) or "") or None if "asset_class" in cols else None,
            income_frequency=str(_clean(row.get(cols["income_frequency"])) or "") or None
            if "income_frequency" in cols
            else None,
            federal_taxable=_to_bool(row.get(cols["federal_taxable"])) if "federal_taxable" in cols else None,
            state_taxable=_to_bool(row.get(cols["state_taxable"])) if "state_taxable" in cols else None,
            ratings=_build_ratings(row, cols),
        )
        bonds.append(bond)

    if not bonds:
        raise IngestError(
            "No fixed-income holdings were detected in the file. "
            "Ensure it is a Tamarac bond export."
        )
    return bonds
