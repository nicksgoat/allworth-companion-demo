"""Tests for the Mock Rebalancer (vendored ProposalGen TaxToolDev engine).

Engine tests run the real CVXPY optimizer on synthetic lot-level portfolios
(offline — no warehouse). Route tests monkeypatch the service layer so the
API contract is exercised hermetically.

Run from the backend/ directory:

    python -m pytest tests/test_rebalancer.py -v
"""
from __future__ import annotations

import os
from datetime import date, timedelta

import polars as pl
import pytest

os.environ["AUTH_DISABLE"] = "1"

from rebalancer.engine.optimizer import PortfolioOptimizer
from rebalancer.routes import bp as rebalancer_bp
from rebalancer import service


# ── Engine fixtures ──────────────────────────────────────────────────────────

def build_portfolio(*rows: dict) -> pl.DataFrame:
    """Lot-level portfolio frame in the shape the optimizer expects."""
    return pl.DataFrame({
        "Symbol": [r["symbol"] for r in rows],
        "Lot Quantity": [float(r["qty"]) for r in rows],
        "Lot Cost Basis": [float(r["cost"]) for r in rows],
        "Date": [date.today() - timedelta(days=r.get("days_ago", 400)) for r in rows],
        "Wash Sale Blocked": [r.get("wash_sale", "No") for r in rows],
        "Asset Class": [r.get("asset_class", "Equity") for r in rows],
        "Subsector": [r.get("subsector") for r in rows],
        "Security Type": [r.get("security_type", "Stock") for r in rows],
        "Category": [r.get("category", "US Stock") for r in rows],
    })


def build_target(weights: dict[str, float]) -> pl.DataFrame:
    return pl.DataFrame({
        "Symbol": list(weights),
        "Target Weight": [float(w) for w in weights.values()],
    })


def build_info(portfolio: pl.DataFrame, target: pl.DataFrame,
               prices: dict[str, float] | None = None) -> pl.DataFrame:
    prices = prices or {}
    symbols = list(dict.fromkeys(portfolio["Symbol"].to_list() + target["Symbol"].to_list()))
    by_symbol = {row["Symbol"]: row for row in portfolio.to_dicts()}
    rows = []
    for symbol in symbols:
        row = by_symbol.get(symbol, {})
        is_cash = symbol == "CASH"
        rows.append({
            "Symbol": symbol,
            "Current Price": float(prices.get(symbol, 1.0 if is_cash else 100.0)),
            "Asset Class": row.get("Asset Class") or ("Cash" if is_cash else "Equity"),
            "Subsector": row.get("Subsector"),
            "Security Type": row.get("Security Type") or ("Cash" if is_cash else "Stock"),
            "Category": row.get("Category") or ("Cash" if is_cash else "Other"),
            "Security Description": symbol,
            "Allows Fractional": "Yes",
            "Wash Sale Blocked": row.get("Wash Sale Blocked", "No"),
            "Unmanaged": "No",
        })
    return pl.DataFrame(rows)


def run_engine(portfolio: pl.DataFrame, target: pl.DataFrame, **kwargs):
    info = kwargs.pop("portfolio_info", None)
    if info is None:
        info = build_info(portfolio, target)
    cash_rows = portfolio.filter(pl.col("Symbol") == "CASH")
    total_cash = float(cash_rows["Lot Quantity"].sum()) if not cash_rows.is_empty() else 0.0
    optimizer = PortfolioOptimizer(
        portfolio=portfolio, target_allocation=target, portfolio_info=info,
        total_cash=total_cash,
        carve_out=kwargs.pop("carve_out", 0.0),
        cash_reserve=kwargs.pop("cash_reserve", 0.0),
    )
    defaults = dict(short_term_rate=0.37, long_term_rate=0.20,
                    max_tax_bill=1e9, realized_gains_constraint=None)
    defaults.update(kwargs)
    return optimizer.optimize_portfolio(**defaults)


SIMPLE_PORTFOLIO = [
    dict(symbol="VTI", qty=100.0, cost=7_500.0),          # $10k at $100, $2.5k LT gain
    dict(symbol="BND", qty=100.0, cost=10_000.0,          # $10k flat
         asset_class="Fixed Income", security_type="Bond", category="Bond"),
    dict(symbol="CASH", qty=1_000.0, cost=1_000.0, days_ago=0,
         asset_class="Cash", security_type="Cash", category="Cash"),
]
SIMPLE_TARGET = {"VTI": 0.55, "BND": 0.40, "CASH": 0.05}


# ── Engine tests ─────────────────────────────────────────────────────────────

class TestEngine:
    def test_unconstrained_rebalance_hits_target(self):
        portfolio = build_portfolio(*SIMPLE_PORTFOLIO)
        target = build_target(SIMPLE_TARGET)
        optimized, *_rest = run_engine(portfolio, target)
        tracking_error = _rest[5]

        assert not optimized.is_empty()
        total = float(optimized["Final Market Value"].sum())
        assert total == pytest.approx(21_000.0, abs=5.0)  # value preserved
        vti = float(optimized.filter(pl.col("Symbol") == "VTI")["Final Market Value"].sum())
        assert vti == pytest.approx(21_000.0 * 0.55, rel=0.03)
        assert tracking_error < 0.05

    def test_quantities_never_negative_and_no_simultaneous_buy_sell(self):
        portfolio = build_portfolio(*SIMPLE_PORTFOLIO)
        optimized, *_ = run_engine(portfolio, build_target(SIMPLE_TARGET))
        assert (optimized["Optimized Quantity"] >= -1e-6).all()
        assert ((optimized["Shares Bought"] <= 1e-6) | (optimized["Shares Sold"] <= 1e-6)).all()

    def test_tax_budget_caps_realized_tax(self):
        # All-appreciated single equity forced toward bonds: unconstrained
        # would realize the full $5k LT gain (~$1k tax at 20%).
        portfolio = build_portfolio(
            dict(symbol="VTI", qty=100.0, cost=5_000.0),
            dict(symbol="CASH", qty=500.0, cost=500.0, days_ago=0,
                 asset_class="Cash", security_type="Cash", category="Cash"),
        )
        target = build_target({"BND": 0.95, "CASH": 0.05})
        budget = 200.0
        results = run_engine(portfolio, target,
                             max_tax_bill=budget, constraint_type="tax_budget")
        total_tax = results[2]  # computed tax (element 1 is the budget passthrough)
        assert total_tax <= budget * 1.05  # small numerical slack

    def test_zero_tax_budget_blocks_gain_realization(self):
        portfolio = build_portfolio(
            dict(symbol="VTI", qty=100.0, cost=5_000.0),
            dict(symbol="CASH", qty=500.0, cost=500.0, days_ago=0,
                 asset_class="Cash", security_type="Cash", category="Cash"),
        )
        target = build_target({"BND": 0.95, "CASH": 0.05})
        results = run_engine(portfolio, target,
                             max_tax_bill=0.0, constraint_type="tax_budget")
        optimized, total_tax = results[0], results[2]
        assert total_tax == pytest.approx(0.0, abs=1.0)
        # The appreciated lot must be (almost) untouched.
        vti_sold = float(optimized.filter(pl.col("Symbol") == "VTI")["Shares Sold"].sum())
        assert vti_sold <= 0.5

    def test_short_vs_long_term_rates_split(self):
        portfolio = build_portfolio(
            dict(symbol="AAA", qty=50.0, cost=2_500.0, days_ago=30),   # ST gain $2.5k
            dict(symbol="BBB", qty=50.0, cost=2_500.0, days_ago=800),  # LT gain $2.5k
            dict(symbol="CASH", qty=100.0, cost=100.0, days_ago=0,
                 asset_class="Cash", security_type="Cash", category="Cash"),
        )
        target = build_target({"CCC": 0.98, "CASH": 0.02})
        # Cheap buy price so whole-share rounding can land inside the cash band.
        info = build_info(portfolio, target, prices={"CCC": 1.0})
        results = run_engine(portfolio, target, portfolio_info=info)
        _, _max_bill, total_tax, rg_short, rg_long, total_gain, *_ = results
        assert rg_short == pytest.approx(2_500.0, rel=0.05)
        assert rg_long == pytest.approx(2_500.0, rel=0.05)
        assert total_gain == pytest.approx(5_000.0, rel=0.05)
        assert total_tax == pytest.approx(2_500 * 0.37 + 2_500 * 0.20, rel=0.05)

    def test_hold_restriction_freezes_symbol(self):
        portfolio = build_portfolio(*SIMPLE_PORTFOLIO)
        target = build_target({"VTI": 0.10, "BND": 0.85, "CASH": 0.05})
        optimized, *_ = run_engine(
            portfolio, target, trade_restrictions={"Hold": ["VTI"]},
        )
        vti = optimized.filter(pl.col("Symbol") == "VTI")
        assert float(vti["Shares Sold"].sum()) <= 1e-3
        assert float(vti["Shares Bought"].sum()) <= 1e-3

    def test_excluded_security_untouched(self):
        portfolio = build_portfolio(*SIMPLE_PORTFOLIO)
        target = build_target({"VTI": 0.10, "BND": 0.85, "CASH": 0.05})
        optimized, *_ = run_engine(portfolio, target, exclude_securities=["VTI"])
        vti = optimized.filter(pl.col("Symbol") == "VTI")
        assert float(vti["Shares Sold"].sum()) <= 1e-3
        assert float(vti["Shares Bought"].sum()) <= 1e-3

    def test_realized_gains_cap(self):
        portfolio = build_portfolio(
            dict(symbol="VTI", qty=100.0, cost=5_000.0),
            dict(symbol="CASH", qty=500.0, cost=500.0, days_ago=0,
                 asset_class="Cash", security_type="Cash", category="Cash"),
        )
        target = build_target({"BND": 0.95, "CASH": 0.05})
        cap = 1_000.0
        results = run_engine(portfolio, target,
                             realized_gains_constraint=cap,
                             constraint_type="realized_gains")
        total_gain = results[5]
        assert total_gain <= cap * 1.05


# ── Synthetic lot construction ───────────────────────────────────────────────

class TestSyntheticLots:
    def _positions(self, *rows: dict) -> pl.DataFrame:
        return pl.DataFrame({
            "Symbol": [r["symbol"] for r in rows],
            "Quantity": [float(r["qty"]) for r in rows],
            "Market Value": [float(r["value"]) for r in rows],
            "Cost Basis": [float(r["cost"]) for r in rows],
            "Current Price": [float(r.get("price", 100.0)) for r in rows],
            "ST Gain": [float(r.get("st", 0.0)) for r in rows],
            "LT Gain": [float(r.get("lt", 0.0)) for r in rows],
            "Security Type": [r.get("security_type", "Stock") for r in rows],
            "Asset Class": [r.get("asset_class", "Equity") for r in rows],
            "Subsector": [None for _ in rows],
            "Restriction Type": [None for _ in rows],
            "Wash Sale Blocked": ["No" for _ in rows],
        })

    def test_st_lt_split_preserves_gains(self):
        positions = self._positions(
            dict(symbol="VTI", qty=100.0, value=10_000.0, cost=7_000.0, st=1_000.0, lt=2_000.0),
        )
        lots = service._synthesize_lots(positions)
        assert len(lots) == 2
        total_qty = float(lots["Lot Quantity"].sum())
        total_cost = float(lots["Lot Cost Basis"].sum())
        assert total_qty == pytest.approx(100.0)
        assert total_cost == pytest.approx(7_000.0)
        # Each lot's unrealized gain matches the warehouse split exactly.
        gains = sorted(
            (row["Lot Quantity"] / 100.0) * 10_000.0 - row["Lot Cost Basis"]
            for row in lots.iter_rows(named=True)
        )
        assert gains == [pytest.approx(1_000.0), pytest.approx(2_000.0)]

    def test_no_gain_info_yields_single_lt_lot(self):
        positions = self._positions(
            dict(symbol="BND", qty=50.0, value=5_000.0, cost=5_000.0),
        )
        lots = service._synthesize_lots(positions)
        assert len(lots) == 1
        assert (date.today() - lots["Date"][0]).days > 365  # long-term treatment

    def test_cash_lot_dated_today(self):
        positions = self._positions(
            dict(symbol="CASH", qty=1_000.0, value=1_000.0, cost=1_000.0, price=1.0,
                 asset_class="Cash", security_type="Cash"),
        )
        lots = service._synthesize_lots(positions)
        assert len(lots) == 1
        assert lots["Date"][0] == date.today()

    def test_synthetic_lots_optimize_end_to_end(self):
        positions = self._positions(
            dict(symbol="VTI", qty=100.0, value=10_000.0, cost=7_000.0, st=1_500.0, lt=1_500.0),
            dict(symbol="CASH", qty=500.0, value=500.0, cost=500.0, price=1.0,
                 asset_class="Cash", security_type="Cash"),
        )
        lots = service._synthesize_lots(positions)
        target = build_target({"VTI": 0.50, "BND": 0.45, "CASH": 0.05})
        optimized, _max_bill, total_tax, *_ = run_engine(lots, target)
        assert not optimized.is_empty()
        assert total_tax >= 0


# ── Route tests (service layer monkeypatched — hermetic) ─────────────────────

@pytest.fixture()
def client():
    from flask import Flask

    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(rebalancer_bp, url_prefix="/api/rebalancer", name="rebalancer_test")
    return app.test_client()


class TestRoutes:
    def test_health(self, client):
        rv = client.get("/api/rebalancer/health")
        assert rv.status_code == 200
        assert rv.get_json()["mode"] == "mock"

    def test_client_role_blocked(self, client):
        rv = client.get(
            "/api/rebalancer/health",
            environ_overrides={"user.claims": {"roles": ["client"]}},
        )
        assert rv.status_code == 403

    def test_models(self, client, monkeypatch):
        monkeypatch.setattr(service, "list_models", lambda: {
            "model_names": ["AWF - Core-Satellite"],
            "allocations_by_model": {"AWF - Core-Satellite": ["60/40", "80/20"]},
        })
        rv = client.get("/api/rebalancer/models")
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["model_names"] == ["AWF - Core-Satellite"]
        assert body["allocations_by_model"]["AWF - Core-Satellite"] == ["60/40", "80/20"]

    def test_account_resolve(self, client, monkeypatch):
        monkeypatch.setattr(service, "resolve_account", lambda acct: {
            "account_number": acct, "upload_account_id": "U123",
            "current_strategy": "Growth 80/20", "total_account_value": 250_000.0,
            "cash_reserve": 5_000.0, "custodian": "Fidelity",
            "is_taxable": True, "below_minimum": False,
        })
        rv = client.get("/api/rebalancer/account/12345678")
        assert rv.status_code == 200
        body = rv.get_json()
        assert body["upload_account_id"] == "U123"
        assert body["is_taxable"] is True

    def test_account_not_found(self, client, monkeypatch):
        def boom(acct):
            raise ValueError(f"Account {acct} not found")
        monkeypatch.setattr(service, "resolve_account", boom)
        rv = client.get("/api/rebalancer/account/00000000")
        assert rv.status_code == 404

    def test_portfolio(self, client, monkeypatch):
        monkeypatch.setattr(service, "get_portfolio", lambda uid: [
            {"Symbol": "VTI", "Quantity": 100.0, "Market Value": 10_000.0},
        ])
        rv = client.get("/api/rebalancer/portfolio/U123")
        assert rv.status_code == 200
        assert rv.get_json()["holdings"][0]["Symbol"] == "VTI"

    def test_optimize_missing_fields(self, client):
        rv = client.post("/api/rebalancer/optimize", json={"target_allocation": "Growth"})
        assert rv.status_code == 400
        assert "missing required field" in rv.get_json()["error"]

    def test_optimize_with_upload_id(self, client, monkeypatch):
        captured = {}

        def fake_run(params):
            captured.update(params)
            return {"upload_account_id": params["upload_account_id"],
                    "optimized_portfolio": [], "total_tax_budget": 0.0,
                    "tracking_error": 0.01}

        monkeypatch.setattr(service, "run_optimization", fake_run)
        rv = client.post("/api/rebalancer/optimize", json={
            "upload_account_id": "U123",
            "target_allocation": "Growth 80/20",
            "short_term_tax_rate": 0.37,
            "long_term_tax_rate": 0.20,
            "tax_budget": 5_000,
        })
        assert rv.status_code == 200
        assert rv.get_json()["success"] is True
        assert captured["tax_budget"] == 5_000

    def test_optimize_resolves_model_allocation(self, client, monkeypatch):
        monkeypatch.setattr(service, "resolve_target_name",
                            lambda model, allocation: f"{model} {allocation}")
        monkeypatch.setattr(service, "run_optimization",
                            lambda params: {"target_allocation": params["target_allocation"]})
        rv = client.post("/api/rebalancer/optimize", json={
            "upload_account_id": "U123",
            "model": "AWF - Core-Satellite",
            "allocation": "60/40",
            "short_term_tax_rate": 0.37,
            "long_term_tax_rate": 0.20,
        })
        assert rv.status_code == 200
        assert rv.get_json()["results"]["target_allocation"] == "AWF - Core-Satellite 60/40"

    def test_optimize_resolves_account_number(self, client, monkeypatch):
        monkeypatch.setattr(service, "resolve_account", lambda acct: {
            "upload_account_id": "U777", "below_minimum": False,
        })
        monkeypatch.setattr(service, "run_optimization",
                            lambda params: {"upload_account_id": params["upload_account_id"]})
        rv = client.post("/api/rebalancer/optimize", json={
            "account_number": "12345678",
            "target_allocation": "Growth 80/20",
            "short_term_tax_rate": 0.37,
            "long_term_tax_rate": 0.20,
        })
        assert rv.status_code == 200
        assert rv.get_json()["results"]["upload_account_id"] == "U777"

    def test_optimize_below_minimum_rejected(self, client, monkeypatch):
        monkeypatch.setattr(service, "resolve_account", lambda acct: {
            "upload_account_id": "U1", "below_minimum": True,
        })
        rv = client.post("/api/rebalancer/optimize", json={
            "account_number": "1",
            "target_allocation": "Growth",
            "short_term_tax_rate": 0.37,
            "long_term_tax_rate": 0.20,
        })
        assert rv.status_code == 422

    def test_optimize_engine_error_is_422(self, client, monkeypatch):
        def boom(params):
            raise ValueError("No holdings found for account U1")
        monkeypatch.setattr(service, "run_optimization", boom)
        rv = client.post("/api/rebalancer/optimize", json={
            "upload_account_id": "U1",
            "target_allocation": "Growth",
            "short_term_tax_rate": 0.37,
            "long_term_tax_rate": 0.20,
        })
        assert rv.status_code == 422
