"""Tests for the Tamarac ingest service."""

from __future__ import annotations

from pathlib import Path

import pytest

from investments.services.ingest import IngestError, parse_tamarac

SAMPLE = Path(__file__).resolve().parent / "fixtures" / "sample_tamarac.csv"


def test_parses_sample_and_filters_non_bonds():
    bonds = parse_tamarac(SAMPLE.read_bytes(), "sample_tamarac.csv")
    # 10 rows in the file, but the SPY equity ETF row must be excluded.
    assert len(bonds) == 9
    assert all(b.description != "SPDR S&P 500 ETF" for b in bonds)


def test_normalizes_fields():
    bonds = parse_tamarac(SAMPLE.read_bytes(), "sample_tamarac.csv")
    treasury = next(b for b in bonds if b.cusip == "912828YK0")
    assert treasury.coupon == 2.5
    assert treasury.maturity_date is not None
    assert treasury.best_rating == "Aaa"
    assert treasury.is_investment_grade is True


def test_detects_callable():
    bonds = parse_tamarac(SAMPLE.read_bytes(), "sample_tamarac.csv")
    callable_bonds = [b for b in bonds if b.callable]
    assert len(callable_bonds) >= 1
    assert all(b.call_date is not None for b in callable_bonds)


def test_empty_file_raises():
    with pytest.raises(IngestError):
        parse_tamarac(b"", "empty.csv")


def test_unrecognized_columns_raise():
    with pytest.raises(IngestError):
        parse_tamarac(b"colA,colB\n1,2\n", "bad.csv")
