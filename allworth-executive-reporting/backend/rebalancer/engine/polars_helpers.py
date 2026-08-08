"""
Shared Polars DataFrame normalization helpers.

These small converters ensure that persisted optimization results (which may be
Polars DataFrames or plain Python objects depending on when they were pickled)
are consistently shaped for downstream consumers.
"""

import polars as pl


def frame_to_column_dict(value):
    """Normalize persisted DataFrames to the dict-of-lists shape display helpers expect."""
    if isinstance(value, pl.DataFrame):
        return value.to_dict(as_series=False)
    return value or {}


def rows_from_maybe_frame(value):
    """Normalize persisted row collections for downstream consumers."""
    if isinstance(value, pl.DataFrame):
        return value.to_dicts()
    return list(value or [])


def string_list_from_maybe_frame(value):
    """Normalize list-like values that may occasionally arrive as Polars frames."""
    if value is None:
        return []
    if isinstance(value, pl.DataFrame):
        if value.is_empty():
            return []
        if 'Symbol' in value.columns:
            return [str(item) for item in value.get_column('Symbol').to_list() if item]
        first_column = value.columns[0] if value.columns else None
        if first_column:
            return [str(item) for item in value.get_column(first_column).to_list() if item]
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [str(value)] if value else []


def mapping_from_maybe_frame(value):
    """Normalize mapping-like values that may occasionally arrive as Polars frames."""
    if value is None:
        return {}
    if isinstance(value, pl.DataFrame):
        if value.is_empty():
            return {}
        if {'Symbol', 'Target Symbol'}.issubset(set(value.columns)):
            return {
                str(symbol): str(target)
                for symbol, target in zip(
                    value.get_column('Symbol').to_list(),
                    value.get_column('Target Symbol').to_list(),
                )
                if symbol and target
            }
        return {}
    if isinstance(value, dict):
        return value
    return {}
