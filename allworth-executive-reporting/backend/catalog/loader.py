"""Catalog data loader.

Reads the generated structured files under ``catalog/data/`` (or the dir set by
``CATALOG_DATA_DIR``) into in-memory dicts, merges the curated overlay on top,
and exposes hot-reload via a file signature — mirroring the Jarvis loader.

Generated files (from ``catalog/generate.py``) are the physical truth; curated
edits live in ``data/overlays/<slug>.yaml`` so they survive regeneration.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"
_reload_lock = threading.Lock()


def data_dir() -> Path:
    override = os.environ.get("CATALOG_DATA_DIR")
    return Path(override) if override else _DEFAULT_DATA_DIR


def tables_dir() -> Path:
    return data_dir() / "tables"


def overlays_dir() -> Path:
    return data_dir() / "overlays"


# --------------------------------------------------------------------------- #
# In-memory state (swapped atomically on reload)
# --------------------------------------------------------------------------- #

TABLES: dict[str, dict[str, Any]] = {}
RELATIONSHIPS: dict[str, Any] = {"nodes": [], "edges": []}
WORKSHEETS: list[dict[str, Any]] = []
GLOSSARY: dict[str, str] = {}
COLUMN_INDEX: dict[str, list[dict[str, Any]]] = {}
WS_COLUMNS: list[dict[str, Any]] = []
WS_COLUMN_INDEX: dict[str, dict[str, Any]] = {}
BUSINESS_LOGIC: dict[str, dict[str, Any]] = {}
COLUMN_LOGIC: dict[str, dict[str, Any]] = {}
SOURCES: list[dict[str, Any]] = []


def file_signature() -> tuple[tuple[str, int], ...]:
    """Change-detection key over generated + overlay files."""
    sig: list[tuple[str, int]] = []
    for d in (tables_dir(), overlays_dir()):
        if d.is_dir():
            for f in d.glob("*.yaml"):
                sig.append((str(f), f.stat().st_mtime_ns))
    for name in ("relationships.yaml", "worksheets.yaml", "glossary.yaml", "worksheet_columns.yaml", "business_logic.yaml", "column_logic.yaml", "sources.yaml"):
        f = data_dir() / name
        if f.is_file():
            sig.append((str(f), f.stat().st_mtime_ns))
    return tuple(sorted(sig))


def _read_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Catalog: failed to read %s", path)
        return None


def _apply_overlay(table: dict[str, Any], overlay: dict[str, Any]) -> None:
    """Merge curated fields from overlay onto a generated table entry in place."""
    for key in ("description", "notes", "business_name", "grain", "pk", "domain"):
        if overlay.get(key):
            table[key] = overlay[key]
    if "deprecated" in overlay:
        table["deprecated"] = bool(overlay["deprecated"])
    col_over = overlay.get("columns") or {}
    if col_over:
        for col in table.get("columns", []):
            patch = col_over.get(col["name"]) or col_over.get(col.get("db_column_name"))
            if not patch:
                continue
            if patch.get("description"):
                col["description"] = patch["description"]
            if "pii" in patch:
                col["pii"] = bool(patch["pii"])


def _load() -> dict[str, Any]:
    tables: dict[str, dict[str, Any]] = {}
    tdir = tables_dir()
    if tdir.is_dir():
        for f in sorted(tdir.glob("*.yaml")):
            entry = _read_yaml(f)
            if isinstance(entry, dict) and entry.get("id"):
                tables[entry["id"]] = entry

    odir = overlays_dir()
    if odir.is_dir():
        for f in sorted(odir.glob("*.yaml")):
            overlay = _read_yaml(f)
            if isinstance(overlay, dict) and overlay.get("id") in tables:
                _apply_overlay(tables[overlay["id"]], overlay)

    rel = _read_yaml(data_dir() / "relationships.yaml") or {"nodes": [], "edges": []}
    ws_doc = _read_yaml(data_dir() / "worksheets.yaml") or {}
    gloss_doc = _read_yaml(data_dir() / "glossary.yaml") or {}
    ws_cols_doc = _read_yaml(data_dir() / "worksheet_columns.yaml") or {}
    ws_columns = ws_cols_doc.get("columns", []) or []
    bl_doc = _read_yaml(data_dir() / "business_logic.yaml") or {}
    cl_doc = _read_yaml(data_dir() / "column_logic.yaml") or {}
    business_logic = {f["name"]: f for f in bl_doc.get("functions", []) or [] if f.get("name")}
    # Curated overlay: edited plain-English summaries survive regeneration.
    bl_overlay = _read_yaml(overlays_dir() / "business_logic.yaml") or {}
    for fn_name, patch in (bl_overlay.get("functions") or {}).items():
        if fn_name in business_logic and isinstance(patch, dict) and patch.get("plain_english") is not None:
            business_logic[fn_name]["plain_english"] = patch["plain_english"]
    column_logic: dict[str, dict[str, Any]] = {}
    for entry in cl_doc.get("columns", []) or []:
        column_logic[f"{str(entry.get('table','')).lower()}||{str(entry.get('column','')).lower()}"] = entry

    col_index: dict[str, list[dict[str, Any]]] = {}
    for slug, tbl in tables.items():
        for col in tbl.get("columns", []):
            col_index.setdefault(col["name"].lower(), []).append(
                {
                    "column": col["name"],
                    "table": tbl["name"],
                    "table_id": slug,
                    "kind": col.get("kind"),
                    "data_type": col.get("data_type"),
                    "db_column_name": col.get("db_column_name"),
                }
            )

    return {
        "tables": tables,
        "relationships": rel,
        "worksheets": ws_doc.get("worksheets", []) or [],
        "glossary": gloss_doc.get("glossary", {}) or {},
        "column_index": col_index,
        "ws_columns": ws_columns,
        "ws_column_index": {c["name"].lower(): c for c in ws_columns if c.get("name")},
        "business_logic": business_logic,
        "column_logic": column_logic,
        "sources": (_read_yaml(data_dir() / "sources.yaml") or {}).get("sources", []) or [],
    }


def reload() -> int:
    fresh = _load()
    with _reload_lock:
        TABLES.clear()
        TABLES.update(fresh["tables"])
        RELATIONSHIPS.clear()
        RELATIONSHIPS.update(fresh["relationships"])
        WORKSHEETS.clear()
        WORKSHEETS.extend(fresh["worksheets"])
        GLOSSARY.clear()
        GLOSSARY.update(fresh["glossary"])
        COLUMN_INDEX.clear()
        COLUMN_INDEX.update(fresh["column_index"])
        WS_COLUMNS.clear()
        WS_COLUMNS.extend(fresh["ws_columns"])
        WS_COLUMN_INDEX.clear()
        WS_COLUMN_INDEX.update(fresh["ws_column_index"])
        BUSINESS_LOGIC.clear()
        BUSINESS_LOGIC.update(fresh["business_logic"])
        COLUMN_LOGIC.clear()
        COLUMN_LOGIC.update(fresh["column_logic"])
        SOURCES.clear()
        SOURCES.extend(fresh["sources"])
    logger.info("Catalog: loaded %d tables from %s", len(TABLES), data_dir())
    return len(TABLES)


# Load once at import.
reload()
