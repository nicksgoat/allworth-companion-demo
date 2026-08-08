"""Versioned tax constants loader.

Only table data belongs here; calculation logic stays in calculator modules.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

D = Decimal


def _decimalize(value):
    if isinstance(value, dict):
        return {k: _decimalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decimalize(v) for v in value]
    if isinstance(value, (int, float)):
        return D(str(value))
    return value


@dataclass(frozen=True)
class TaxTables:
    year: int
    data: dict

    def __getattr__(self, name):
        try:
            return self.data[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def load_tables(year: int = 2026) -> TaxTables:
    path = Path(__file__).with_name("tables") / f"{year}.json"
    if not path.exists():
        raise ValueError(f"unsupported tax-table year: {year}")
    return TaxTables(year, _decimalize(json.loads(path.read_text())))


def project_tables(base: TaxTables, year: int, inflation_rate: Decimal) -> TaxTables:
    """Inflate indexed planning thresholds beyond the last enacted table year."""
    if year <= base.year: return base
    factor = (D("1") + D(inflation_rate)) ** (year - base.year)
    data = deepcopy(base.data)
    for brackets in data["brackets"].values():
        for bracket in brackets: bracket[0] *= factor
    for thresholds in data["ltcg_thresholds"].values():
        for index in range(len(thresholds)): thresholds[index] *= factor
    for key in data["standard_deduction"]: data["standard_deduction"][key] *= factor
    for section in ("exemption", "phaseout"):
        for key in data["amt"][section]: data["amt"][section][key] *= factor
    data["amt"]["rate_break"] *= factor
    for key in data["retirement_limits"]: data["retirement_limits"][key] *= factor
    for key in data["qbi"]["threshold"]: data["qbi"]["threshold"][key] *= factor
    for key in data["qbi"]["phaseout_end"]: data["qbi"]["phaseout_end"][key] *= factor
    return TaxTables(year, data)
