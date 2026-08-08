"""Tests for the called-bond cash and reinvestment review."""

from __future__ import annotations

from investments.services import transactions


def _transaction(account: str, quantity: float, amount: float, *, trade_date: str = "2026-07-15") -> dict:
    return {
        "account_number": account,
        "account_name": "",
        "trade_date": trade_date,
        "transaction_type": "Sell",
        "symbol": None,
        "cusip": f"OLD-{account}",
        "description": "Called bond",
        "quantity": quantity,
        "price": 100.0,
        "amount": amount,
        "notes": "REDEMP",
        "source": "tav.transactions_sells_over_30",
    }


def test_called_review_applies_cash_then_same_quantity_bond_buy(monkeypatch):
    redemptions = [
        _transaction("CASH", 10_000, 10_000),
        _transaction("BUY", 20_000, 20_000),
        _transaction("OPEN", 30_000, 30_000),
    ]
    buys = [
        {
            **_transaction("BUY", 20_000, 20_000, trade_date="2026-07-16"),
            "transaction_type": "Buy",
            "cusip": "NEW-BOND",
        },
        {
            **_transaction("OPEN", 25_000, 25_000, trade_date="2026-07-16"),
            "transaction_type": "Buy",
            "cusip": "WRONG-QUANTITY",
        },
    ]
    monkeypatch.setattr(
        transactions,
        "_load_called_transactions",
        lambda session, start_date, end_date: redemptions,
    )
    monkeypatch.setattr(
        transactions,
        "_load_account_cash",
        lambda session, accounts: {
            "CASH": {
                "account_name": "Cash Account",
                "account_value": 100_000,
                "cash_value": 12_000,
                "cash_percent": 12,
            },
            "BUY": {
                "account_name": "Buy Account",
                "account_value": 100_000,
                "cash_value": 2_000,
                "cash_percent": 2,
            },
            "OPEN": {
                "account_name": "Open Account",
                "account_value": 100_000,
                "cash_value": 4_000,
                "cash_percent": 4,
            },
        },
    )
    monkeypatch.setattr(
        transactions,
        "_load_recent_buys",
        lambda session, accounts, start_date, end_date, match_values: buys,
    )
    monkeypatch.setattr(
        transactions,
        "_load_bond_identifiers",
        lambda session, cusips, symbols: ({"NEW-BOND", "WRONG-QUANTITY"}, set()),
    )
    monkeypatch.setattr(
        transactions,
        "get_bond_ladder_account_numbers",
        lambda session: {"CASH", "BUY", "OPEN"},
    )
    transactions.invalidate_called_report_cache()

    report = transactions.get_called_bonds_review(
        object(), days=30, force_refresh=True
    )

    assert [row["highlight"] for row in report["rows"]] == ["cash", "yellow", None]
    assert report["cash_flagged_count"] == 1
    assert report["reinvested_count"] == 1
    assert report["unresolved_count"] == 1
    assert report["rows"][1]["matching_buy"]["cusip"] == "NEW-BOND"
    assert report["rows"][2]["matching_buy"] is None


class _Rows:
    def mappings(self):
        return self

    def all(self):
        return []


class _Session:
    def __init__(self):
        self.sql = ""
        self.params = {}

    def execute(self, statement, params=None):
        self.sql = str(statement)
        self.params = params or {}
        return _Rows()


def test_called_scan_pushes_all_selective_filters_to_external_table(monkeypatch):
    monkeypatch.setattr(
        transactions,
        "_get_table_columns",
        lambda session, schema, table: {
            "Account_Number",
            "Activity_Type",
            "Notes",
            "Trade_Date",
            "Quantity",
            "Amount",
        },
    )
    session = _Session()

    transactions._load_called_transactions(
        session,
        start_date=transactions.date(2026, 7, 1),
        end_date=transactions.date(2026, 7, 30),
    )

    assert "[tav].[transactions_sells_over_30]" in session.sql
    assert "= 'SELL'" in session.sql
    assert ">= :start_date" in session.sql
    assert "<= :end_date" in session.sql
    assert "LIKE '%REDEMP%'" in session.sql
    assert "NOT LIKE '%MATURED%'" in session.sql
    assert session.params == {"start_date": "2026-07-01", "end_date": "2026-07-30"}
