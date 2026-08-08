"""Tests for database-backed account analysis behavior."""

from __future__ import annotations

from datetime import date

from investments.services import db_analyzer


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self):
        self.statements: list[str] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append(sql)
        if "Security_Info" in sql:
            return _Rows([
                {
                    "CUSIP": "111",
                    "Issuer": "Issuer One",
                    "Interest_Rate": 2.0,
                    "Current_Yield_to_Worst": 3.0,
                    "Effective_Duration": 4.0,
                    "Maturity_Date": date(2030, 1, 1),
                },
                {
                    "CUSIP": "222",
                    "Issuer": "Issuer Two",
                    "Interest_Rate": 6.0,
                    "Current_Yield_to_Worst": 7.0,
                    "Effective_Duration": 8.0,
                    "Maturity_Date": date(2032, 1, 1),
                },
            ])
        return _Rows([
            {
                "Account_Number": "A1",
                "Account_Name": "Account One",
                "CUSIP": "111",
                "Quantity": 10,
                "Market_Value": 100.0,
                "Upload_Account_ID": 101,
                "As_Of_Date": date(2026, 7, 6),
            },
            {
                "Account_Number": "A2",
                "Account_Name": "Account Two",
                "CUSIP": "222",
                "Quantity": 20,
                "Market_Value": 300.0,
                "Upload_Account_ID": 102,
                "As_Of_Date": date(2026, 7, 6),
            },
        ])


def _columns_for(table: str) -> set[str]:
    if table == "Account_Daily_Holdings":
        return {
            "Account_Number",
            "Account_Name",
            "CUSIP",
            "Quantity",
            "Market_Value",
            "Upload_Account_ID",
            "As_Of_Date",
        }
    if table == "All_Custodian_Values":
        return {"Upload_Account_ID", "Reinvestment_Instructions"}
    return {
        "CUSIP",
        "Issuer",
        "Interest_Rate",
        "Current_Yield_to_Worst",
        "Effective_Duration",
        "Maturity_Date",
    }


def test_analyze_account_numbers_combines_holdings_and_weighted_kpis(monkeypatch):
    db_analyzer._cache.clear()
    monkeypatch.setattr(
        db_analyzer,
        "_get_table_columns",
        lambda session, schema, table: _columns_for(table),
    )

    result = db_analyzer.analyze_account_numbers(_Session(), ["A1", "A2", "A1"])

    assert result is not None
    assert result.account_numbers == ["A1", "A2"]
    assert result.account_names == ["Account One", "Account Two"]
    assert result.holdings_count == 2
    assert [bond.account_id for bond in result.bonds] == ["A1", "A2"]
    assert result.dashboard["kpis"]["market_value"] == 400.0
    assert result.dashboard["kpis"]["average_coupon"] == 5.0
    assert result.dashboard["kpis"]["average_yield"] == 6.0
    assert result.dashboard["kpis"]["average_duration"] == 7.0


def test_analyze_sql_excludes_zero_quantity_holdings(monkeypatch):
    """WHERE clause must contain a non-zero quantity filter (fix for 89236TJK2 bug)."""
    db_analyzer._cache.clear()
    monkeypatch.setattr(
        db_analyzer,
        "_get_table_columns",
        lambda session, schema, table: (
            {
                "Account_Number",
                "CUSIP",
                "Quantity",
                "Market_Value",
                "Upload_Account_ID",
                "As_Of_Date",
            }
            if table == "Account_Daily_Holdings"
            else {"Upload_Account_ID", "Reinvestment_Instructions"}
            if table == "All_Custodian_Values"
            else {"CUSIP", "Maturity_Date"}
        ),
    )

    session = _Session()
    db_analyzer.analyze_account_numbers(session, ["A1"])

    holdings_sql = next(s for s in session.statements if "Account_Daily_Holdings" in s)
    # The generated SQL must exclude rows where Quantity is zero or NULL
    assert "Quantity" in holdings_sql
    assert "<> 0" in holdings_sql or "!= 0" in holdings_sql
    assert "Reinvestment_Instructions" in holdings_sql


def test_appraisal_holdings_does_not_filter_to_individual_bonds(monkeypatch):
    monkeypatch.setattr(
        db_analyzer,
        "_get_table_columns",
        lambda session, schema, table: (
            {
                "Account_Number",
                "Account_Name",
                "CUSIP",
                "Symbol",
                "Security_Description",
                "Security_Type",
                "Subsector",
                "Quantity",
                "Market_Value",
                "Upload_Account_ID",
                "As_Of_Date",
            }
            if table == "Account_Daily_Holdings"
            else {"Upload_Account_ID", "Reinvestment_Instructions"}
            if table == "All_Custodian_Values"
            else {"CUSIP"}
        ),
    )

    session = _Session()
    db_analyzer.get_appraisal_holdings(session, ["A1"])

    holdings_sql = next(s for s in session.statements if "Account_Daily_Holdings" in s)
    assert "Individual Bond" not in holdings_sql
    assert "Subsector] = " not in holdings_sql
    assert "Reinvestment_Instructions" in holdings_sql


def test_to_date_strips_sentinel_years():
    """Dates in year >= 2098 (common security-master placeholders) must return None."""
    from datetime import date as _date
    assert db_analyzer._to_date("12/31/2098") is None
    assert db_analyzer._to_date("2098-12-31") is None
    assert db_analyzer._to_date("12/31/2099") is None
    assert db_analyzer._to_date(_date(2098, 12, 31)) is None
    # Normal dates must still pass through
    assert db_analyzer._to_date("2030-06-15") == _date(2030, 6, 15)
    assert db_analyzer._to_date("12/31/2097") == _date(2097, 12, 31)
