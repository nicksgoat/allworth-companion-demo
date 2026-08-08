"""Tests for the combined Account Lookup transaction history."""

from __future__ import annotations

from investments.services import transactions


def test_transactions_combine_sources_include_amount_and_deduplicate(monkeypatch):
    shared = {
        "Transaction_ID": 100,
        "Account_Number": "A1",
        "Trade_Date": "2026-07-01",
        "Transaction_Type": "Sell",
        "Symbol": "BOND1",
        "Amount": -10_000,
    }

    def query(session, schema, table, account_numbers, *, since, redemptions_only):
        if table == "transactions_staging":
            return [
                shared,
                {
                    **shared,
                    "Transaction_ID": 101,
                    "Transaction_Type": "Buy",
                    "Amount": 9_900,
                },
            ]
        return [
            shared,
            {
                **shared,
                "Transaction_ID": 99,
                "Trade_Date": "2026-05-01",
                "Amount": -8_000,
            },
        ]

    monkeypatch.setattr(transactions, "_query_one_table", query)

    rows = transactions.get_transactions(object(), ["A1"])

    assert len(rows) == 3
    assert {row["source"] for row in rows} == {
        "tav.transactions_staging",
        "tav.transactions_sells_over_30",
    }
    assert {row["amount"] for row in rows} == {-10_000.0, 9_900.0, -8_000.0}
    assert sum(row["transaction_id"] == "100" for row in rows) == 1
