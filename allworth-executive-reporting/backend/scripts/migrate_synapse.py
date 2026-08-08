"""Apply PlanEngine Synapse migrations to the planning-owned schema.

Runs the SQL files in backend/planning/migrations in order, splitting on GO
batch separators. Connects with the same DW_*/SYNAPSE_* settings the app uses
and only ever creates/alters objects inside the PlanEngine schemas
([planengine], [planengine_security]); governed sfp/tho/tav schemas are never
referenced by these scripts.

Usage (from backend/):

    python scripts/migrate_synapse.py            # apply all migrations
    python scripts/migrate_synapse.py --dry-run  # list batches without executing
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import pyodbc

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "planning" / "migrations"
FORBIDDEN_SCHEMAS = ("[sfp]", "[tho]", "[tav]", "sfp.", "tho.", "tav.")


def _connection_string() -> str:
    server = (os.getenv("DW_SERVER") or os.getenv("SYNAPSE_SERVER") or "").strip()
    database = (os.getenv("DW_DATABASE") or os.getenv("SYNAPSE_DATABASE") or "").strip()
    user = (os.getenv("DW_USER") or os.getenv("SYNAPSE_USERNAME") or "").strip().strip("'\"")
    password = (os.getenv("DW_PW") or os.getenv("SYNAPSE_PASSWORD") or "").strip().strip("'\"")
    driver = (os.getenv("ODBC_DRIVER") or os.getenv("SYNAPSE_DRIVER")
              or "ODBC Driver 18 for SQL Server").strip("{}")
    if not (server and database and user and password):
        raise SystemExit("Missing DW_SERVER/DW_DATABASE/DW_USER/DW_PW "
                         "(or SYNAPSE_* equivalents) in the environment")
    return (f"DRIVER={{{driver}}};SERVER=tcp:{server},1433;DATABASE={database};"
            f"UID={user};PWD={password};Encrypt=yes;TrustServerCertificate=no;"
            "Connection Timeout=30")


def _batches(sql: str) -> list[str]:
    batches = [batch.strip() for batch in re.split(r"^\s*GO\s*$", sql,
                                                   flags=re.IGNORECASE | re.MULTILINE)]
    executable = []
    for batch in batches:
        # Synapse rejects comment-only batches; skip anything with no statements.
        stripped = re.sub(r"/\*.*?\*/", "", batch, flags=re.DOTALL)
        stripped = re.sub(r"^\s*--.*$", "", stripped, flags=re.MULTILINE).strip()
        if stripped:
            executable.append(batch)
    return executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise SystemExit(f"No migration files found in {MIGRATIONS_DIR}")

    # Safety gate: PlanEngine migrations must never reference governed schemas.
    for path in files:
        lowered = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_SCHEMAS:
            if token.lower() in lowered:
                raise SystemExit(f"{path.name} references governed schema token "
                                 f"'{token}' - refusing to run")

    if args.dry_run:
        for path in files:
            batches = _batches(path.read_text(encoding="utf-8"))
            print(f"{path.name}: {len(batches)} batches")
        return 0

    connection = pyodbc.connect(_connection_string(), autocommit=True)
    try:
        cursor = connection.cursor()
        for path in files:
            batches = _batches(path.read_text(encoding="utf-8"))
            print(f"Applying {path.name} ({len(batches)} batches)...")
            for index, batch in enumerate(batches, 1):
                try:
                    cursor.execute(batch)
                except pyodbc.Error as exc:
                    print(f"  batch {index} FAILED: {exc}", file=sys.stderr)
                    raise
            print(f"  {path.name} OK")
    finally:
        connection.close()
    print("All migrations applied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
