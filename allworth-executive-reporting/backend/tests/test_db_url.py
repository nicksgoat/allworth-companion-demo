"""Database URL resolution tests."""

from __future__ import annotations

from investments.db import build_pyodbc_database_url


def test_build_pyodbc_database_url_encodes_driver_and_password():
    url = build_pyodbc_database_url(
        server="allworthsynapse.sql.azuresynapse.net",
        database="DataWarehouse",
        username="allworthsqladmin",
        password="p@ss word",
        driver="ODBC Driver 18 for SQL Server",
        port="1433",
        encrypt="yes",
        trust_server_certificate="no",
    )

    assert url.startswith("mssql+pyodbc://allworthsqladmin:")
    assert "@allworthsynapse.sql.azuresynapse.net:1433/DataWarehouse" in url
    assert "driver=ODBC+Driver+18+for+SQL+Server" in url
    assert "Encrypt=yes" in url
    assert "TrustServerCertificate=no" in url
    assert "p%40ss+word" in url
