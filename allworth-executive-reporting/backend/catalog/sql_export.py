"""Flatten the generated catalog data into relational rows for the SQL
data-dictionary tables (``meta.Data_Dictionary_*``).

Pure transform: reads the YAML files under ``catalog/data/`` (or ``CATALOG_DATA_DIR``)
and returns four row lists — ``tables``, ``columns``, ``joins``, ``glossary`` — that
[sql_publish.py](sql_publish.py) loads into Synapse. No Flask and no DB imports, so it
is unit-testable and reusable by an MCP loader.

The catalog YAML is the richest existing copy of the warehouse metadata, so it is
the seed source of truth. Authoring still happens upstream (ThoughtSpot TML +
schema_index.yaml); this module only reshapes the generated output.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def data_dir() -> Path:
    override = os.environ.get("CATALOG_DATA_DIR")
    return Path(override) if override else _DEFAULT_DATA_DIR


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _csv(values: Any) -> str | None:
    """Join a list into a comma-separated string; pass scalars through."""
    if not values:
        return None
    if isinstance(values, (list, tuple, set)):
        items = [str(v).strip() for v in values if str(v).strip()]
        return ", ".join(items) if items else None
    return str(values).strip() or None


def _norm_table_key(name: str) -> str:
    """Normalize a table name for fuzzy matching across TML vs notebook naming
    (e.g. ``Account_Daily_Holdings`` vs ``tho_account_daily_holdings``)."""
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    if key.startswith("tho"):
        key = key[3:]
    return key


def _build_column_logic_index(cl_doc: Any) -> dict[tuple[str, str], dict[str, Any]]:
    """Index column_logic entries by (normalized table, lowered column)."""
    index: dict[tuple[str, str], dict[str, Any]] = {}
    if not isinstance(cl_doc, dict):
        return index
    for entry in cl_doc.get("columns", []) or []:
        tbl = _norm_table_key(entry.get("table") or "")
        col = (entry.get("column") or "").strip().lower()
        if not tbl or not col:
            continue
        # Keep the first (usually most specific) derivation per column.
        index.setdefault((tbl, col), entry)
    return index


def build_rows(when: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    """Read the generated catalog data and return the four relational row sets."""
    generated_at = (when or datetime.now(timezone.utc)).replace(microsecond=0)
    ddir = data_dir()

    cl_index = _build_column_logic_index(_read_yaml(ddir / "column_logic.yaml"))

    table_rows: list[dict[str, Any]] = []
    column_rows: list[dict[str, Any]] = []

    tdir = ddir / "tables"
    if tdir.is_dir():
        for f in sorted(tdir.glob("*.yaml")):
            tbl = _read_yaml(f)
            if not isinstance(tbl, dict) or not tbl.get("id"):
                continue
            table_id = tbl["id"]
            table_name = tbl.get("name") or table_id
            schema_name = tbl.get("schema")
            db_table = tbl.get("db_table") or table_name
            cols = tbl.get("columns", []) or []

            table_rows.append({
                "table_id": table_id,
                "table_name": table_name,
                "schema_name": schema_name,
                "db_name": tbl.get("db"),
                "db_table": db_table,
                "guid": tbl.get("guid"),
                "business_name": tbl.get("business_name"),
                "grain": tbl.get("grain"),
                "pk": tbl.get("pk"),
                "domain": tbl.get("domain"),
                "synonyms": _csv(tbl.get("synonyms")),
                "deprecated": bool(tbl.get("deprecated")),
                "spotter_enabled": bool(tbl.get("spotter_enabled")),
                "description": tbl.get("description") or None,
                "notes": tbl.get("notes") or None,
                "worksheets": _csv(tbl.get("worksheets")),
                "column_count": tbl.get("column_count", len(cols)),
                "source": "catalog",
                "generated_at": generated_at,
            })

            tkey = _norm_table_key(db_table or table_name)
            for col in cols:
                db_col = col.get("db_column_name") or col.get("name")
                logic = cl_index.get((tkey, (db_col or "").strip().lower())) or {}
                column_rows.append({
                    "table_id": table_id,
                    "table_name": table_name,
                    "schema_name": schema_name,
                    "db_table": db_table,
                    "db_column_name": db_col,
                    "display_name": col.get("name"),
                    "data_type": col.get("data_type"),
                    "kind": col.get("kind"),
                    "aggregation": col.get("aggregation"),
                    "synonyms": _csv(col.get("synonyms")),
                    "description": col.get("description") or None,
                    "pii": bool(col.get("pii")),
                    "hot": bool(col.get("hot")),
                    "derivation_expression": logic.get("expression"),
                    "source_notebook": logic.get("notebook"),
                    "source_systems": _csv(logic.get("source_systems")),
                    "generated_at": generated_at,
                })

    join_rows: list[dict[str, Any]] = []
    rel = _read_yaml(ddir / "relationships.yaml") or {}
    for edge in rel.get("edges", []) or []:
        join_rows.append({
            "from_table": edge.get("from"),
            "from_id": edge.get("from_id"),
            "to_table": edge.get("to"),
            "to_id": edge.get("to_id"),
            "from_col": edge.get("from_col"),
            "to_col": edge.get("to_col"),
            "join_type": edge.get("type"),
            "one_to_one": bool(edge.get("one_to_one")),
            "join_name": edge.get("join_name"),
            "generated_at": generated_at,
        })

    glossary_rows: list[dict[str, Any]] = []
    gloss_doc = _read_yaml(ddir / "glossary.yaml") or {}
    for term, definition in (gloss_doc.get("glossary") or {}).items():
        glossary_rows.append({
            "term": str(term),
            "definition": str(definition) if definition is not None else None,
            "generated_at": generated_at,
        })

    return {
        "tables": table_rows,
        "columns": column_rows,
        "joins": join_rows,
        "glossary": glossary_rows,
    }


if __name__ == "__main__":  # quick local sanity check
    rows = build_rows()
    for name, items in rows.items():
        print(f"{name}: {len(items)} rows")
