"""Shared cash symbol helpers for tax tools."""

from __future__ import annotations

from typing import Any


SWEEP_CASH_SYMBOLS = frozenset({
    "CASH",
    "FCASH",
    "MMDA12",
    "IDA12",
    "FDRXX",
})


def normalize_symbol(value: Any) -> str:
    """Normalize a symbol-like value for comparisons."""
    return str(value or "").strip().upper()


def is_sweep_cash_symbol(value: Any) -> bool:
    """Return True when the symbol is an explicit sweep-cash alias."""
    return normalize_symbol(value) in SWEEP_CASH_SYMBOLS


def canonicalize_sweep_cash_symbol(value: Any) -> str:
    """Map supported sweep-cash aliases to the canonical CASH symbol."""
    symbol = normalize_symbol(value)
    return "CASH" if symbol in SWEEP_CASH_SYMBOLS else symbol
