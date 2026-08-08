"""Catalog query logic: search, faceting, table detail, ER graph, where-used.

Pure Python over the in-memory state in ``loader``; no Flask imports so it can
be reused by a future MCP server.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

from catalog import loader

# Jarvis knowledge base = the "Metrics / encyclopedia" surface of the unified
# tool. We read its in-place resources (single source of truth, also read by the
# MCP server) rather than copying them. Defensive: if Jarvis is unavailable the
# metrics surface is simply disabled.
try:
    from jarvis import handler as jarvis_handler
    from jarvis.knowledge_loader import RESOURCES as JARVIS_RESOURCES
    _JARVIS_OK = True
except Exception:  # pragma: no cover - defensive
    jarvis_handler = None  # type: ignore
    JARVIS_RESOURCES = {}  # type: ignore
    _JARVIS_OK = False

_RELOAD_CHECK_SECONDS = float(os.environ.get("CATALOG_RELOAD_CHECK_SECONDS", "30"))
_last_reload_check = 0.0
_last_signature: tuple[tuple[str, int], ...] = ()


def _maybe_reload() -> None:
    global _last_reload_check, _last_signature
    now = time.monotonic()
    if now - _last_reload_check < _RELOAD_CHECK_SECONDS:
        return
    _last_reload_check = now
    sig = loader.file_signature()
    if sig != _last_signature:
        loader.reload()
        _last_signature = sig


def bump_reload_marker() -> None:
    """Force the next query to re-scan (called after a curated write)."""
    global _last_reload_check
    _last_reload_check = 0.0


# --------------------------------------------------------------------------- #
# Summaries + facets
# --------------------------------------------------------------------------- #

def _summary(tbl: dict[str, Any]) -> dict[str, Any]:
    cols = tbl.get("columns", [])
    return {
        "id": tbl["id"],
        "name": tbl["name"],
        "schema": tbl.get("schema"),
        "domain": tbl.get("domain"),
        "business_name": tbl.get("business_name"),
        "grain": tbl.get("grain"),
        "pk": tbl.get("pk"),
        "deprecated": bool(tbl.get("deprecated")),
        "column_count": tbl.get("column_count", len(cols)),
        "measure_count": sum(1 for c in cols if c.get("kind") == "measure"),
        "has_pii": any(c.get("pii") for c in cols),
        "worksheet_count": len(tbl.get("worksheets", [])),
    }


def facets() -> dict[str, Any]:
    _maybe_reload()
    schemas: dict[str, int] = {}
    domains: dict[str, int] = {}
    deprecated = 0
    pii = 0
    for tbl in loader.TABLES.values():
        schemas[tbl.get("schema") or "?"] = schemas.get(tbl.get("schema") or "?", 0) + 1
        domains[tbl.get("domain") or "Other"] = domains.get(tbl.get("domain") or "Other", 0) + 1
        if tbl.get("deprecated"):
            deprecated += 1
        if any(c.get("pii") for c in tbl.get("columns", [])):
            pii += 1
    return {
        "schemas": [{"value": k, "count": v} for k, v in sorted(schemas.items())],
        "domains": [{"value": k, "count": v} for k, v in sorted(domains.items())],
        "deprecated": deprecated,
        "pii": pii,
        "total": len(loader.TABLES),
    }


def list_tables(
    *,
    q: str = "",
    schema: str = "",
    domain: str = "",
    kind: str = "",
    pii: bool | None = None,
    include_deprecated: bool = True,
) -> dict[str, Any]:
    _maybe_reload()
    q_low = (q or "").strip().lower()
    results: list[tuple[int, dict[str, Any]]] = []

    for tbl in loader.TABLES.values():
        if schema and (tbl.get("schema") or "") != schema:
            continue
        if domain and (tbl.get("domain") or "Other") != domain:
            continue
        if not include_deprecated and tbl.get("deprecated"):
            continue
        cols = tbl.get("columns", [])
        if kind == "measure" and not any(c.get("kind") == "measure" for c in cols):
            continue
        if kind == "attribute" and not any(c.get("kind") == "attribute" for c in cols):
            continue
        if pii is True and not any(c.get("pii") for c in cols):
            continue

        score = 1
        if q_low:
            score = _match_score(tbl, q_low)
            if score <= 0:
                continue
        results.append((score, tbl))

    results.sort(key=lambda item: (-item[0], item[1]["name"]))
    return {
        "tables": [_summary(t) for _, t in results],
        "count": len(results),
        "facets": facets(),
    }


def _match_score(tbl: dict[str, Any], q_low: str) -> int:
    name = tbl.get("name", "").lower()
    score = 0
    if q_low in name:
        score += 6
    if q_low in (tbl.get("business_name") or "").lower():
        score += 4
    for syn in tbl.get("synonyms", []):
        if q_low in str(syn).lower():
            score += 3
    if q_low in (tbl.get("description") or "").lower():
        score += 2
    if q_low in (tbl.get("notes") or "").lower():
        score += 1
    # column-name hits
    for col in tbl.get("columns", []):
        if q_low in col["name"].lower():
            score += 2
            break
    return score


def get_table(slug: str) -> dict[str, Any] | None:
    _maybe_reload()
    tbl = loader.TABLES.get(slug)
    if not tbl:
        return None
    # Attach inbound relationships (other tables that point here).
    inbound: list[dict[str, Any]] = []
    for other in loader.TABLES.values():
        if other["id"] == slug:
            continue
        for rel in other.get("relationships", []):
            if rel.get("to_id") == slug:
                inbound.append(
                    {
                        "from": other["name"],
                        "from_id": other["id"],
                        "join_name": rel.get("join_name"),
                        "type": rel.get("type"),
                        "one_to_one": rel.get("one_to_one"),
                        "on": rel.get("on"),
                    }
                )
    out = dict(tbl)
    out["inbound_relationships"] = inbound
    return out


# --------------------------------------------------------------------------- #
# ER graph
# --------------------------------------------------------------------------- #

def graph(worksheet: str = "") -> dict[str, Any]:
    _maybe_reload()
    node_ids: set[str] = set()

    if worksheet:
        member_names = set()
        for ws in loader.WORKSHEETS:
            if ws.get("name") == worksheet:
                member_names = set(ws.get("tables", []))
                break
        node_ids = {
            tbl["id"] for tbl in loader.TABLES.values() if tbl["name"] in member_names
        }
    else:
        node_ids = set(loader.TABLES.keys())

    nodes = [
        {
            "id": tbl["id"],
            "name": tbl["name"],
            "domain": tbl.get("domain"),
            "schema": tbl.get("schema"),
            "deprecated": bool(tbl.get("deprecated")),
        }
        for tbl in loader.TABLES.values()
        if tbl["id"] in node_ids
    ]

    edges = [
        e
        for e in loader.RELATIONSHIPS.get("edges", [])
        if e.get("from_id") in node_ids and e.get("to_id") in node_ids
    ]
    return {"worksheet": worksheet or None, "nodes": nodes, "edges": edges}


def worksheets() -> list[dict[str, Any]]:
    _maybe_reload()
    return [
        {
            "name": ws.get("name"),
            "description": ws.get("description", ""),
            "table_count": len(ws.get("tables", [])),
        }
        for ws in sorted(loader.WORKSHEETS, key=lambda w: w.get("name", ""))
    ]


# --------------------------------------------------------------------------- #
# Column where-used / lineage
# --------------------------------------------------------------------------- #

def where_used(column: str) -> dict[str, Any]:
    _maybe_reload()
    key = (column or "").strip().lower()
    tables = loader.COLUMN_INDEX.get(key, [])
    # Join edges that reference this column on either side.
    joins: list[dict[str, Any]] = []
    for e in loader.RELATIONSHIPS.get("edges", []):
        if (e.get("from_col") or "").lower() == key or (e.get("to_col") or "").lower() == key:
            joins.append(e)
    return {"column": column, "tables": tables, "joins": joins, "count": len(tables)}


def glossary() -> dict[str, str]:
    _maybe_reload()
    return dict(loader.GLOSSARY)


def sources() -> dict[str, Any]:
    """Source systems (from wealth_mcp.domain.sources via sources.yaml), each
    enriched with usage: how many documented columns/tables trace to its tag."""
    _maybe_reload()
    usage: dict[str, dict[str, Any]] = {}
    for entry in loader.COLUMN_LOGIC.values():
        for tag in entry.get("source_systems") or []:
            u = usage.setdefault(str(tag).lower(), {"columns": 0, "tables": set()})
            u["columns"] += 1
            if entry.get("table"):
                u["tables"].add(entry["table"])
    out = []
    for s in loader.SOURCES:
        item = dict(s)
        u = usage.get((s.get("tag") or "").lower(), {"columns": 0, "tables": set()})
        item["column_count"] = u["columns"]
        item["table_count"] = len(u["tables"])
        item["tables"] = sorted(u["tables"])
        out.append(item)
    out.sort(key=lambda s: (-s["column_count"], s.get("name") or ""))
    return {"sources": out, "count": len(out)}


# --------------------------------------------------------------------------- #
# Columns index (searchable field dictionary drawn from the TML worksheets)
# --------------------------------------------------------------------------- #

def list_columns(q: str = "", kind: str = "", limit: int = 500) -> dict[str, Any]:
    """Unique worksheet (model) columns, searchable by name.

    Each entry aggregates the field across every worksheet it appears in: the
    models, the source table(s) it's drawn from, its kind, and whether it's a
    formula-derived field.
    """
    _maybe_reload()
    ql = (q or "").strip().lower()
    rows: list[dict[str, Any]] = []
    for col in loader.WS_COLUMNS:
        name = col.get("name", "")
        if ql and ql not in name.lower():
            continue
        kinds = col.get("kinds", [])
        if kind and kind not in kinds:
            continue
        rows.append(
            {
                "name": name,
                "kinds": kinds,
                "worksheet_count": len(col.get("worksheets", [])),
                "source_count": len(col.get("sources", [])),
                "has_formula": bool(col.get("formulas")),
                "description": (col.get("descriptions") or [""])[0],
            }
        )
    if ql:
        rows.sort(
            key=lambda r: (
                0 if r["name"].lower() == ql else 1 if r["name"].lower().startswith(ql) else 2,
                -r["worksheet_count"],
                r["name"].lower(),
            )
        )
    else:
        rows.sort(key=lambda r: (-r["worksheet_count"], r["name"].lower()))
    return {"columns": rows[:limit], "count": len(rows)}


def column_detail(name: str) -> dict[str, Any] | None:
    """Full aggregated worksheet-column entry: models, sources, formula, desc,
    plus the Synapse derivation logic (expression, functions, comments) for each
    source table.column."""
    _maybe_reload()
    entry = loader.WS_COLUMN_INDEX.get((name or "").strip().lower())
    if not entry:
        return None
    out = dict(entry)
    out["sources"] = [dict(s) for s in entry.get("sources", [])]
    used_funcs: list[str] = []
    for src in out["sources"]:
        key = f"{str(src.get('table','')).lower()}||{str(src.get('column','')).lower()}"
        logic = loader.COLUMN_LOGIC.get(key)
        if logic:
            src["logic"] = logic
            for fn in logic.get("functions", []):
                if fn not in used_funcs:
                    used_funcs.append(fn)
    out["functions"] = [loader.BUSINESS_LOGIC[f] for f in used_funcs if f in loader.BUSINESS_LOGIC]
    return out


def list_business_logic(q: str = "") -> list[dict[str, Any]]:
    _maybe_reload()
    ql = (q or "").strip().lower()
    funcs = list(loader.BUSINESS_LOGIC.values())
    if ql:
        funcs = [
            f for f in funcs
            if ql in f.get("name", "").lower()
            or ql in f.get("title", "").lower()
            or ql in f.get("description", "").lower()
        ]
    return sorted(funcs, key=lambda f: f.get("name", "").lower())


# --------------------------------------------------------------------------- #
# Metrics (Jarvis encyclopedia) + metric <-> table cross-links
# --------------------------------------------------------------------------- #

_WORD_RE = re.compile(r"[a-z0-9_]+")

# Inference tuning: ignore generic column tokens and any token that resolves to
# more than this many tables (no real signal).
_GENERIC_COLUMN_LIMIT = 5
_METRIC_STOPWORDS = {
    "date", "name", "status", "type", "code", "flag", "active", "year",
    "month", "day", "quarter", "reason", "source", "channel", "division",
    "region", "amount", "value", "count", "total", "current", "client",
    "clients", "period", "rate", "revenue", "assets", "money", "growth",
    "roll", "forward", "trade", "entry", "prospect", "pipeline", "opportunity",
    "definition", "score", "model", "number", "level", "group", "primary",
}


def metrics_available() -> bool:
    return _JARVIS_OK


def _name_to_slug() -> dict[str, str]:
    return {t["name"]: t["id"] for t in loader.TABLES.values()}


def _slug_for(name: str) -> str | None:
    return _name_to_slug().get(name)


def _metric_tokens(resource: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    for kw in resource.get("keywords") or []:
        for w in _WORD_RE.findall(str(kw).lower()):
            tokens.add(w)
    # the metric name itself (e.g. "NCNM", "Net Flows")
    for w in _WORD_RE.findall(str(resource.get("name", "")).lower()):
        tokens.add(w)
    return tokens


def metric_links(resource: dict[str, Any]) -> dict[str, Any]:
    """Resolve a metric's related tables/columns (authored + inferred)."""
    _maybe_reload()
    name_to_slug = _name_to_slug()
    tables: dict[str, dict[str, Any]] = {}  # table name -> entry

    def _add(table_name: str, column: str | None, authored: bool) -> None:
        if not table_name or table_name not in name_to_slug:
            return
        entry = tables.setdefault(
            table_name,
            {"table": table_name, "table_id": name_to_slug[table_name],
             "columns": [], "authored": False},
        )
        entry["authored"] = entry["authored"] or authored
        if column and column not in entry["columns"]:
            entry["columns"].append(column)

    # 1) authored related_tables
    for t in resource.get("related_tables") or []:
        _add(str(t), None, True)

    # 2) authored related_columns ({table,column} or bare column name)
    for rc in resource.get("related_columns") or []:
        if isinstance(rc, dict):
            _add(str(rc.get("table", "")), rc.get("column"), True)
        else:
            for hit in loader.COLUMN_INDEX.get(str(rc).lower(), []):
                _add(hit["table"], hit.get("db_column_name") or str(rc), True)

    # 3) inferred: metric tokens that exactly match a column name, skipping
    # short or overly-generic tokens (a token in many tables carries no signal).
    for tok in _metric_tokens(resource):
        if len(tok) < 4 or tok in _METRIC_STOPWORDS:
            continue
        hits = loader.COLUMN_INDEX.get(tok, [])
        if not hits or len(hits) > _GENERIC_COLUMN_LIMIT:
            continue
        for hit in hits:
            _add(hit["table"], hit.get("db_column_name") or tok, False)

    ordered = sorted(
        tables.values(), key=lambda e: (not e["authored"], e["table"])
    )
    return {"tables": ordered}


def _resource_for(key: str) -> dict[str, Any] | None:
    return JARVIS_RESOURCES.get(key)


def list_metrics() -> dict[str, Any]:
    if not _JARVIS_OK:
        return {"groups": [], "available": False}
    payload = jarvis_handler.list_docs()
    payload["available"] = True
    return payload


def search_metrics(q: str, limit: int = 12) -> list[dict[str, Any]]:
    if not _JARVIS_OK or not (q or "").strip():
        return []
    return jarvis_handler.search_all(q, limit=limit)


def get_metric(key: str) -> dict[str, Any] | None:
    if not _JARVIS_OK:
        return None
    doc = jarvis_handler.get_doc(key)
    if not doc:
        return None
    res = _resource_for(key) or {}
    doc["related_tables_raw"] = res.get("related_tables", []) or []
    doc["related_columns_raw"] = res.get("related_columns", []) or []
    doc["links"] = metric_links(res or doc)
    return doc


def metrics_for_table(table_name: str) -> list[dict[str, Any]]:
    """Reverse index: metric docs whose (authored/inferred) links hit this table."""
    if not _JARVIS_OK:
        return []
    out: list[dict[str, Any]] = []
    for key, res in JARVIS_RESOURCES.items():
        links = metric_links(res)
        for entry in links["tables"]:
            if entry["table"] == table_name:
                out.append(
                    {
                        "key": key,
                        "name": res.get("name", key),
                        "category": res.get("category"),
                        "authored": entry["authored"],
                        "columns": entry["columns"],
                    }
                )
                break
    out.sort(key=lambda m: (not m["authored"], m["name"]))
    return out

