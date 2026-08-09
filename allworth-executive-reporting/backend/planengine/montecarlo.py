"""Reproducible stochastic re-runs of the full ledger engine."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import numpy as np
from pydantic import BaseModel, Field

from .engine import run_projection
from .models import Facts


class AssetClass(BaseModel):
    name: str
    expected_return: float
    std_dev: float
    weight: float = 1.0


class YearBand(BaseModel):
    year: int
    p5: Decimal; p25: Decimal; p50: Decimal; p75: Decimal; p95: Decimal


class MonteCarloResult(BaseModel):
    n_trials: int
    seed: int
    probability_of_success: float
    success_by_age: dict[int, float]
    ending_value_percentiles: dict[str, Decimal]
    net_worth_bands: list[YearBand]
    first_failure_year_histogram: dict[int, int] = Field(default_factory=dict)
    input_snapshot: dict[str, Any] = Field(default_factory=dict)


def nearest_psd(matrix: np.ndarray) -> np.ndarray:
    sym = (matrix + matrix.T) / 2
    values, vectors = np.linalg.eigh(sym)
    values[values < 1e-10] = 1e-10
    out = vectors @ np.diag(values) @ vectors.T
    scale = np.sqrt(np.diag(out))
    return out / np.outer(scale, scale)


def generate_paths(cma: list[AssetClass], n_years: int, n_trials: int,
                   corr: np.ndarray | None = None, seed: int = 42) -> np.ndarray:
    if not cma or n_years < 1 or n_trials < 1:
        raise ValueError("positive dimensions and at least one asset class required")
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_trials, n_years, len(cma)))
    if corr is not None:
        if corr.shape != (len(cma), len(cma)):
            raise ValueError("correlation matrix shape mismatch")
        z = z @ np.linalg.cholesky(nearest_psd(corr)).T
    mu = np.array([x.expected_return for x in cma])
    sigma = np.array([x.std_dev for x in cma])
    return np.maximum(-0.999, mu + sigma * z)


def run_monte_carlo(facts: Facts | dict, start_year: int | None = None,
                    n_trials: int = 300, seed: int = 42,
                    cma: list[AssetClass] | str | None = None,
                    corr: np.ndarray | None = None,
                    input_snapshot: dict[str, Any] | None = None,
                    chunk_size: int | None = None, **_: Any) -> MonteCarloResult:
    facts = facts if isinstance(facts, Facts) else Facts.model_validate(facts)
    zero_sigma = cma == "zero_sigma"
    if zero_sigma:
        default_return = float(facts.accounts[0].growth_rate if facts.accounts else Decimal("0.05"))
        cma = [AssetClass(name="portfolio", expected_return=default_return, std_dev=0)]
    cma = cma or [AssetClass(name="portfolio", expected_return=0.06, std_dev=0.12)]
    base = run_projection(facts, start_year=start_year)
    paths = generate_paths(cma, len(base.rows), n_trials, corr=corr, seed=seed)
    weights = np.asarray([max(0.0, asset.weight) for asset in cma], dtype=float)
    weights = weights / weights.sum() if weights.sum() else np.ones(len(cma)) / len(cma)
    net_worth = np.empty((n_trials, len(base.rows)))
    success = np.ones((n_trials, len(base.rows)), dtype=bool)
    first_fail: dict[int, int] = {}
    ages = [row.client_age or 0 for row in base.rows]
    years = [row.year for row in base.rows]
    for i in range(n_trials):
        annual = {year: Decimal(str(paths[i, j] @ weights)) for j, year in enumerate(years)}
        projection = base if zero_sigma else run_projection(facts, annual, start_year=start_year)
        failed = False
        for j, row in enumerate(projection.rows):
            net_worth[i, j] = float(row.net_worth)
            failed = failed or row.shortfall > 0
            success[i, j] = not failed
        if projection.first_shortfall_year is not None:
            first_fail[projection.first_shortfall_year] = first_fail.get(projection.first_shortfall_year, 0) + 1
    percentiles = np.percentile(net_worth, [5, 25, 50, 75, 95], axis=0)
    bands = [YearBand(year=year, p5=Decimal(str(percentiles[0, j])),
                      p25=Decimal(str(percentiles[1, j])), p50=Decimal(str(percentiles[2, j])),
                      p75=Decimal(str(percentiles[3, j])), p95=Decimal(str(percentiles[4, j])))
             for j, year in enumerate(years)]
    ending = percentiles[:, -1]
    return MonteCarloResult(n_trials=n_trials, seed=seed,
                            probability_of_success=float(success[:, -1].mean()),
                            success_by_age={age: float(success[:, j].mean()) for j, age in enumerate(ages)},
                            ending_value_percentiles={k: Decimal(str(v)) for k, v in zip(
                                ["p5", "p25", "p50", "p75", "p95"], ending)},
                            net_worth_bands=bands,
                            first_failure_year_histogram=first_fail,
                            input_snapshot=input_snapshot or {})
