"""Tests for Bond Ladder warehouse loading."""

from __future__ import annotations

from investments.services import db_analyzer
from investments.services import bond_ladder


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
            return _Rows([])
        return _Rows([
            {
                "Account_Number": "A1",
                "Account_Name": "Holding Account",
                "Demo_Account_Name": "Demo Account",
                "Strategy": "AWF - Bond Ladder Municipal 1-10 year",
                "CUSIP": "111",
                "Quantity": 10,
                "Market_Value": 100.0,
                "Total_Account_Value": 100.0,
            }
        ])


def test_fetch_bond_ladder_uses_bond_ladder_checkbox_not_rebalancing_model(monkeypatch):
    def columns_for(session, schema, table):
        return (
            {
                "Account_Number",
                "Account_Name",
                "CUSIP",
                "Quantity",
                "Market_Value",
                "Total_Account_Value",
                "Subsector",
                "avaccountuploadid",
            }
            if table == "Account_Daily_Holdings"
            else {"Upload_Account_ID", "Account_Name", "Bond_Ladder", "Rebalancing_Model_Name"}
            if table == "Current_Account_Demographic"
            else {"Upload_Account_ID", "Reinvestment_Instructions"}
            if table == "All_Custodian_Values"
            else {"CUSIP"}
        )

    monkeypatch.setattr(
        bond_ladder,
        "_get_table_columns",
        columns_for,
    )
    monkeypatch.setattr(db_analyzer, "_get_table_columns", columns_for)
    session = _Session()

    result = bond_ladder._fetch_bond_ladder(session)

    ladder_sql = session.statements[0]
    assert "Bond_Ladder" in ladder_sql
    assert "Rebalancing_Model_Name" in ladder_sql
    assert "Reinvestment_Instructions" in ladder_sql
    assert "LIKE" not in ladder_sql
    assert any("[tav].[Security_Info]" in sql for sql in session.statements)
    assert not any("security_info_new_columns" in sql for sql in session.statements)
    assert result.total_accounts == 1
    assert result.accounts[0].strategy == "AWF - Bond Ladder Municipal 1-10 year"
    assert result.strategies == ["AWF - Bond Ladder Municipal 1-10 year"]
