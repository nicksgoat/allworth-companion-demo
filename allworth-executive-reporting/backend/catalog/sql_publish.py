"""Publish the catalog data dictionary to Synapse (``meta.Data_Dictionary_*``).

Builds the relational rows from [sql_export.py](sql_export.py), (re)creates the
four tables from [sql/data_dictionary.sql](sql/data_dictionary.sql), and loads
the rows. A full replace each run — the dataset is small (~78 tables / ~2k
columns) and the catalog data is regenerated upstream.

Usage (from backend/):
    python -m catalog.sql_publish --dry-run        # no DB; writes CSVs + counts
    python -m catalog.sql_publish                  # create tables + load to Synapse

Connection mirrors backend/app.py via AUTH_METHOD (ServicePrincipal /
SqlPassword / ActiveDirectoryInteractive), same as backend/nfbc/synapse_nfbc.py.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from pathlib import Path
from typing import Any

from catalog import sql_export

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent
_DDL_PATH = _HERE / "sql" / "data_dictionary.sql"

# Column order per target table — matches sql/data_dictionary.sql exactly.
_COLUMNS: dict[str, tuple[str, list[str]]] = {
    "tables": ("meta.Data_Dictionary_Table", [
        "table_id", "table_name", "schema_name", "db_name", "db_table", "guid",
        "business_name", "grain", "pk", "domain", "synonyms", "deprecated",
        "spotter_enabled", "description", "notes", "worksheets", "column_count",
        "source", "generated_at",
    ]),
    "columns": ("meta.Data_Dictionary_Column", [
        "table_id", "table_name", "schema_name", "db_table", "db_column_name",
        "display_name", "data_type", "kind", "aggregation", "synonyms",
        "description", "pii", "hot", "derivation_expression", "source_notebook",
        "source_systems", "generated_at",
    ]),
    "joins": ("meta.Data_Dictionary_Join", [
        "from_table", "from_id", "to_table", "to_id", "from_col", "to_col",
        "join_type", "one_to_one", "join_name", "generated_at",
    ]),
    "glossary": ("meta.Data_Dictionary_Glossary", [
        "term", "definition", "generated_at",
    ]),
}

# Fields stored as BIT — pyodbc wants int 0/1 for Synapse dedicated pools.
_BIT_FIELDS = {"deprecated", "spotter_enabled", "pii", "hot", "one_to_one"}


def _to_param(field: str, value: Any) -> Any:
    if field in _BIT_FIELDS:
        return 1 if value else 0
    return value


# ── Connection (mirrors backend/app.py / synapse_nfbc.py) ───────────────────

def _build_conn_str() -> str:
    server = os.getenv("SYNAPSE_SERVER", "allworthsynapse.sql.azuresynapse.net")
    database = os.getenv("SYNAPSE_DATABASE", "DataWarehouse")
    driver = os.getenv("ODBC_DRIVER", "{ODBC Driver 18 for SQL Server}")
    auth = os.getenv("AUTH_METHOD", "ActiveDirectoryInteractive")
    base = f"DRIVER={driver};SERVER={server};DATABASE={database};"

    if auth == "AccessToken":
        # Token is injected via attrs_before in _connect(); no auth in the string.
        return base + "Encrypt=yes;TrustServerCertificate=no"
    if auth == "ServicePrincipal":
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")
        tenant_id = os.getenv("AZURE_TENANT_ID")
        if not all([client_id, client_secret, tenant_id]):
            raise ValueError("Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID")
        return (base + "Authentication=ActiveDirectoryServicePrincipal;"
                f"UID={client_id}@{tenant_id};PWD={client_secret};"
                "Encrypt=yes;TrustServerCertificate=no")
    if auth == "SqlPassword":
        username = os.getenv("SYNAPSE_USERNAME")
        password = os.getenv("SYNAPSE_PASSWORD")
        if not all([username, password]):
            raise ValueError("Set SYNAPSE_USERNAME and SYNAPSE_PASSWORD")
        return base + f"UID={username};PWD={password};Encrypt=yes;TrustServerCertificate=no"
    if auth == "ActiveDirectoryInteractive":
        return base + "Authentication=ActiveDirectoryInteractive;Encrypt=yes;TrustServerCertificate=no"
    raise ValueError(f"Unknown AUTH_METHOD: {auth}")


def _connect():
    """Open a pyodbc connection. Supports AUTH_METHOD=AccessToken (AAD token in
    env AZURE_SQL_ACCESS_TOKEN, e.g. from `az account get-access-token`)."""
    import struct

    import pyodbc

    conn_str = _build_conn_str()
    timeout = int(os.getenv("SYNAPSE_QUERY_TIMEOUT", "60"))

    if os.getenv("AUTH_METHOD") == "AccessToken":
        token = os.environ["AZURE_SQL_ACCESS_TOKEN"]
        # ODBC expects the UTF-16-LE token prefixed with its 4-byte length.
        token_bytes = token.encode("utf-16-le")
        token_struct = struct.pack("<i", len(token_bytes)) + token_bytes
        SQL_COPT_SS_ACCESS_TOKEN = 1256
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=timeout,
                              attrs_before={SQL_COPT_SS_ACCESS_TOKEN: token_struct})
    else:
        conn = pyodbc.connect(conn_str, autocommit=True, timeout=timeout)
    conn.timeout = timeout
    return conn


def _run_ddl(cursor) -> None:
    """Ensure the schema exists, then execute the DDL file batch by batch.

    Synapse dedicated pools reject ``CREATE SCHEMA`` inside a control-of-flow
    ``IF``/``EXEC`` block, so schema creation is done here explicitly.
    """
    cursor.execute("SELECT COUNT(*) FROM sys.schemas WHERE name = 'meta'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("CREATE SCHEMA meta")
    sql = _DDL_PATH.read_text(encoding="utf-8")
    batches = [b.strip() for b in _split_go(sql) if b.strip()]
    for batch in batches:
        cursor.execute(batch)


def _split_go(sql: str) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    for line in sql.splitlines():
        if line.strip().upper() == "GO":
            out.append("\n".join(current))
            current = []
        else:
            current.append(line)
    if current:
        out.append("\n".join(current))
    return out


def _load_table(cursor, target: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    placeholders = ", ".join("?" for _ in columns)
    col_list = ", ".join(f"[{c}]" for c in columns)
    sql = f"INSERT INTO {target} ({col_list}) VALUES ({placeholders})"
    params = [
        tuple(_to_param(c, r.get(c)) for c in columns)
        for r in rows
    ]
    cursor.executemany(sql, params)


def _write_dry_run(rows: dict[str, list[dict[str, Any]]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for key, (target, columns) in _COLUMNS.items():
        items = rows[key]
        path = out_dir / f"{target.split('.')[-1]}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for r in items:
                writer.writerow({c: r.get(c) for c in columns})
        print(f"  {target}: {len(items)} rows -> {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish the catalog data dictionary to Synapse.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build rows and write CSVs; do not touch the database.")
    parser.add_argument("--out-dir", default=None,
                        help="Directory for --dry-run CSVs (default: data/sql_export/).")
    args = parser.parse_args()

    rows = sql_export.build_rows()
    print("Built rows:")
    for key in _COLUMNS:
        print(f"  {key}: {len(rows[key])}")

    if args.dry_run:
        out_dir = Path(args.out_dir) if args.out_dir else (sql_export.data_dir() / "sql_export")
        print(f"\nDry run — writing CSVs to {out_dir}")
        _write_dry_run(rows, out_dir)
        return

    import pyodbc  # noqa: F401 — ensure the ODBC driver is importable before connecting

    print("\nConnecting to Synapse...")
    conn = _connect()
    try:
        cursor = conn.cursor()
        # DDL must run in autocommit mode — Synapse dedicated pools reject
        # CREATE SCHEMA / DDL inside an explicit transaction.
        print("Creating tables (meta.Data_Dictionary_*)...")
        _run_ddl(cursor)
        # Load rows transactionally so a mid-load failure rolls back cleanly.
        conn.autocommit = False
        try:
            for key, (target, columns) in _COLUMNS.items():
                print(f"Loading {target}: {len(rows[key])} rows")
                _load_table(cursor, target, columns, rows[key])
            conn.commit()
            print("Done — committed.")
        except Exception:
            conn.rollback()
            logger.exception("Load failed — rolled back (tables remain, empty).")
            raise
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
