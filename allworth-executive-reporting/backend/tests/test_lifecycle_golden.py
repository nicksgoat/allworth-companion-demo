"""Lifecycle model golden-file regression test.

Pins the deterministic Idzorek-Kaplan lifecycle outputs for a reference case so
any change to the model math is caught and reviewed deliberately. When the
change is intentional, regenerate tests/golden/lifecycle_reference.json.

Run:
    python -m pytest tests/test_lifecycle_golden.py -v
"""

import json
from pathlib import Path

import pytest

from planengine.lifecycle import InvestorParams, run_lifecycle_plan

GOLDEN = json.loads((Path(__file__).parent / "golden" / "lifecycle_reference.json").read_text())


@pytest.fixture(scope="module")
def result() -> dict:
    return run_lifecycle_plan(InvestorParams.model_validate(GOLDEN["inputs"]))


def _assert_row(actual: dict, expected: dict) -> None:
    assert actual.keys() == expected.keys()
    for key, value in expected.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            assert actual[key] == pytest.approx(value, rel=1e-9), key
        else:
            assert actual[key] == value, key


def test_economic_balance_sheet(result):
    _assert_row(result["economic_balance_sheet"], GOLDEN["economic_balance_sheet"])


def test_bequest(result):
    _assert_row(result["bequest"], GOLDEN["bequest"])


def test_consumption_path_endpoints(result):
    _assert_row(result["consumption_path"][0], GOLDEN["consumption_first"])
    _assert_row(result["consumption_path"][-1], GOLDEN["consumption_last"])


def test_glide_path_shape(result):
    assert len(result["glide_path"]) == GOLDEN["path_length"]
    _assert_row(result["glide_path"][0], GOLDEN["glide_first"])
    _assert_row(next(r for r in result["glide_path"] if r["age"] == 65),
                GOLDEN["glide_at_retirement"])
    _assert_row(result["glide_path"][-1], GOLDEN["glide_last"])


def test_survival_and_human_capital(result):
    _assert_row(next(r for r in result["survival_curve"] if r["age"] == 85),
                GOLDEN["survival_at_85"])
    _assert_row(result["human_capital_path"][0], GOLDEN["human_capital_first"])


def test_glide_path_invariants(result):
    for row in result["glide_path"]:
        total = row["domestic_stock"] + row["global_stock"] + row["bonds_cash"]
        # components are rounded to 4dp individually, so allow rounding drift
        assert total == pytest.approx(1.0, abs=2e-4)
        assert 0.0 <= row["constrained_equity"] <= 1.0
