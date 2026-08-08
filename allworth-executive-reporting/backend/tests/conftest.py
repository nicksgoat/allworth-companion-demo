"""Shared pytest fixtures."""

from __future__ import annotations

import os
from datetime import date

import pytest

# Hermetic-test guard: never let a shell configured for live Synapse leak
# warehouse persistence into the test run. Planning modules read these at
# import time, so strip them before any test module is imported.
for _var in ("SYNAPSE_PLANNING_ENABLED", "PLANNING_LOCAL_DB", "WAREHOUSE_DATABASE_URL"):
    os.environ.pop(_var, None)
os.environ["AUTH_DISABLE"] = "1"

from investments.models.bond import Bond, CreditRating


@pytest.fixture
def sample_bonds() -> list[Bond]:
    """A small, deterministic portfolio used across analytics tests."""
    return [
        Bond(
            cusip="111",
            description="US Treasury 2.5% 2027",
            account_id="A1",
            coupon=2.5,
            price=99.0,
            quantity=100_000,
            yield_to_worst=2.6,
            effective_duration=2.8,
            maturity_date=date(2027, 5, 15),
            sector="Government",
            issuer="US Treasury",
            state="US",
            income_frequency="Semi-Annual",
            ratings=[CreditRating(agency="Moody's", current="Aaa", previous="Aaa")],
        ),
        Bond(
            cusip="222",
            description="California GO 4.0% 2030",
            account_id="A1",
            coupon=4.0,
            price=101.0,
            quantity=50_000,
            yield_to_worst=3.85,
            effective_duration=4.1,
            maturity_date=date(2030, 6, 1),
            call_date=date(2028, 6, 1),
            callable=True,
            call_price=100,
            sector="Municipal",
            issuer="State of California",
            state="CA",
            income_frequency="Semi-Annual",
            ratings=[CreditRating(agency="Moody's", current="Aa2", previous="Aa1")],
        ),
        Bond(
            cusip="333",
            description="Bank of America 4.25% 2028",
            account_id="A2",
            coupon=4.25,
            price=100.5,
            quantity=55_000,
            yield_to_worst=4.1,
            effective_duration=2.6,
            maturity_date=date(2028, 4, 15),
            call_date=date(2027, 4, 15),
            callable=True,
            sector="Financials",
            issuer="Bank of America",
            state="US",
            income_frequency="Quarterly",
            ratings=[CreditRating(agency="Moody's", current="Baa1", previous="A3")],
        ),
    ]
