"""Data Catalog generator.

Parses the ThoughtSpot TML version-control repo (table + worksheet TMLs) plus
the curated ``schema_index.yaml`` into structured per-table YAML files that the
catalog blueprint serves and a future MCP server can read.

This is a dev-time build step (analogous to ``scripts/install-jarvis-content.ps1``).
Re-run it whenever the TML export changes.

Inputs (resolved in order):
  - env ``CATALOG_TML_DIR``  -> the ``thoughtspot_tml_version_control`` folder.
  - env ``CATALOG_SCHEMA_INDEX`` -> path to ``schema_index.yaml`` (optional enrichment).
  - otherwise a set of candidate paths relative to this repo are probed.

Output:
  backend/catalog/data/
    tables/<slug>.yaml        one structured entry per warehouse table
    relationships.yaml        de-duplicated join edges (the ER graph)
    worksheets.yaml           worksheet -> member tables + description
    glossary.yaml             business term glossary (from schema_index)
    ai_index.yaml             compact, token-efficient rollup for LLM context

Usage:
    python -m catalog.generate            # from the backend/ dir
    python backend/catalog/generate.py    # from the repo root
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

_HERE = Path(__file__).resolve().parent
_DATA_DIR = _HERE / "data"
_TABLES_DIR = _DATA_DIR / "tables"

# db_column reference like "[Household_Rollforward::avhhid]"
_REF_RE = re.compile(r"\[([^\]:]+)::([^\]]+)\]")


def _candidate_tml_dirs() -> list[Path]:
    env = os.environ.get("CATALOG_TML_DIR")
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    # Common local layouts: the workspace root holds both this repo and the
    # tml/ clone as siblings.
    repo_root = _HERE.parents[2]  # backend/catalog -> backend -> repo root
    workspace_root = repo_root.parent
    for base in (repo_root, workspace_root, workspace_root.parent):
        candidates.append(base / "tml" / "thoughtspot_tml_version_control")
        candidates.append(base / "thoughtspot_tml_version_control")
    return candidates


def _resolve_tml_dir() -> Path:
    for c in _candidate_tml_dirs():
        if (c / "table").is_dir():
            return c
    tried = "\n  ".join(str(c) for c in _candidate_tml_dirs())
    raise SystemExit(
        "Could not locate the ThoughtSpot TML repo. Set CATALOG_TML_DIR to the "
        "'thoughtspot_tml_version_control' folder.\nTried:\n  " + tried
    )


def _resolve_schema_index() -> Path | None:
    env = os.environ.get("CATALOG_SCHEMA_INDEX")
    if env and Path(env).is_file():
        return Path(env)
    repo_root = _HERE.parents[2]
    workspace_root = repo_root.parent
    for base in (repo_root, workspace_root, workspace_root.parent):
        p = base / "schema_index.yaml"
        if p.is_file():
            return p
    return None


def _resolve_synapse_dir() -> Path | None:
    """Locate the allworthsynapse notebook folder (for business-logic parsing)."""
    env = os.environ.get("CATALOG_SYNAPSE_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    repo_root = _HERE.parents[2]
    workspace_root = repo_root.parent
    for base in (repo_root, workspace_root, workspace_root.parent):
        p = base / "az_dev_ops" / "allworthsynapse" / "notebook"
        if p.is_dir():
            return p
    return None


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def slugify(name: str) -> str:
    """Lowercase, dash-separated slug matching ^[a-z0-9][a-z0-9-]{1,63}$."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not s:
        s = "table"
    if not s[0].isalnum():
        s = "t" + s
    return s[:64]


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report and skip bad files
        print(f"  ! failed to parse {path.name}: {exc}", file=sys.stderr)
        return None


def _parse_on_pairs(on_clause: str) -> list[dict[str, str]]:
    """Turn '[A::x] = [B::y] AND [A::z] = [B::w]' into column pairs."""
    refs = _REF_RE.findall(on_clause or "")
    pairs: list[dict[str, str]] = []
    for i in range(0, len(refs) - 1, 2):
        (lt, lc), (rt, rc) = refs[i], refs[i + 1]
        pairs.append(
            {
                "from_table": lt.strip(),
                "from_col": lc.strip(),
                "to_table": rt.strip(),
                "to_col": rc.strip(),
            }
        )
    return pairs


# --------------------------------------------------------------------------- #
# schema_index.yaml enrichment
# --------------------------------------------------------------------------- #

def _load_schema_index(path: Path | None) -> dict[str, Any]:
    """Return {tables_by_name, glossary, join_hints, few_shot, deprecated}."""
    out: dict[str, Any] = {
        "tables_by_name": {},
        "glossary": {},
        "join_hints": [],
        "few_shot": [],
        "deprecated": set(),
    }
    if not path:
        return out
    data = _load_schema_index_yaml(path) or {}
    out["glossary"] = data.get("glossary", {}) or {}
    out["join_hints"] = data.get("join_hints", []) or []
    out["few_shot"] = data.get("few_shot", []) or []
    for name in data.get("deprecated_from_ai_catalog", []) or []:
        out["deprecated"].add(_bare_name(str(name)).lower())

    for entry in data.get("tables", []) or []:
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("name", ""))
        bare = _bare_name(raw).lower()
        if not bare:
            continue
        out["tables_by_name"][bare] = {
            "business_name": entry.get("business_name"),
            "grain": entry.get("grain"),
            "pk": entry.get("pk"),
            "synonyms": entry.get("synonyms", []) or [],
            "notes": entry.get("notes"),
            "hot_columns": _hot_column_names(entry.get("hot_columns")),
        }
    return out


# schema_index.yaml hand-curated hot_columns blocks mix plain scalars and
# `key: value` lines, which is invalid YAML. Rewrite each `hot_columns:` header
# into a literal block scalar so the body is captured as opaque text we can
# tokenise, without mutating the source file.
_HOT_HEADER_RE = re.compile(r"^(\s*)hot_columns:\s*$", re.MULTILINE)


def _load_schema_index_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    text = _HOT_HEADER_RE.sub(r"\1hot_columns: |", text)
    try:
        return yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! failed to parse {path.name}: {exc}", file=sys.stderr)
        return None


def _bare_name(name: str) -> str:
    """'tho.Current_Household_Fact' / '"tho.X(Trade Date)"' -> table part."""
    n = name.strip().strip('"').strip("'")
    if "." in n:
        n = n.split(".", 1)[1]
    return n


def _hot_column_names(hot: Any) -> set[str]:
    """schema_index hot_columns come as a mapping or list; extract bare names."""
    names: set[str] = set()
    tokens: list[str] = []
    if isinstance(hot, dict):
        tokens = list(hot.keys())
    elif isinstance(hot, list):
        tokens = [str(t) for t in hot]
    elif isinstance(hot, str):
        tokens = hot.splitlines()
    for tok in tokens:
        # A token may be 'LeadId, AVHHID, HHID', '"Primary Household ID" -> X',
        # or 'LeadId: Salesforce Lead ID' (drop the trailing description).
        head = str(tok).split("->", 1)[0].split(":", 1)[0]
        for piece in re.split(r"[,\s]+", head):
            piece = piece.strip().strip('"').strip("'")
            if piece:
                names.add(piece.lower())
    return names


# PII heuristic: column names that likely carry personal data.
_PII_HINTS = (
    "ssn", "dob", "birth", "email", "phone", "address", "zip", "postal",
    "first_name", "last_name", "firstname", "lastname", "street", "city",
)


def _looks_pii(col_name: str, db_col: str) -> bool:
    h = f"{col_name} {db_col}".lower()
    return any(hint in h for hint in _PII_HINTS)


# --------------------------------------------------------------------------- #
# Table TML parsing
# --------------------------------------------------------------------------- #

def _parse_table_tml(path: Path) -> dict[str, Any] | None:
    doc = _load_yaml(path)
    if not isinstance(doc, dict) or "table" not in doc:
        return None
    tbl = doc["table"] or {}
    name = tbl.get("name")
    if not name:
        return None

    columns: list[dict[str, Any]] = []
    for col in tbl.get("columns", []) or []:
        if not isinstance(col, dict):
            continue
        props = col.get("properties", {}) or {}
        db_props = col.get("db_column_properties", {}) or {}
        col_name = col.get("name", "")
        db_col = col.get("db_column_name", col_name)
        ctype = str(props.get("column_type", "")).upper()
        columns.append(
            {
                "name": col_name,
                "db_column_name": db_col,
                "data_type": db_props.get("data_type"),
                "kind": "measure" if ctype == "MEASURE" else "attribute",
                "aggregation": props.get("aggregation"),
                "synonyms": props.get("synonyms", []) or [],
                "description": "",
                "pii": _looks_pii(col_name, db_col),
            }
        )

    joins: list[dict[str, Any]] = []
    for j in tbl.get("joins_with", []) or []:
        if not isinstance(j, dict):
            continue
        dest = j.get("destination", {}) or {}
        on_clause = j.get("on", "")
        joins.append(
            {
                "join_name": j.get("name"),
                "to": dest.get("name"),
                "to_guid": dest.get("fqn"),
                "type": j.get("type"),
                "one_to_one": bool(j.get("is_one_to_one")),
                "on": on_clause,
                "pairs": _parse_on_pairs(on_clause),
            }
        )

    spotter = (
        (tbl.get("properties", {}) or {})
        .get("spotter_config", {})
        .get("is_spotter_enabled")
    )

    return {
        "guid": doc.get("guid"),
        "name": name,
        "schema": tbl.get("schema"),
        "db": tbl.get("db"),
        "db_table": tbl.get("db_table", name),
        "columns": columns,
        "joins": joins,
        "spotter_enabled": bool(spotter),
    }


# --------------------------------------------------------------------------- #
# Worksheet TML parsing
# --------------------------------------------------------------------------- #

def _parse_worksheet_tml(path: Path) -> dict[str, Any] | None:
    doc = _load_yaml(path)
    if not isinstance(doc, dict) or "model" not in doc:
        # Older TML uses `worksheet:`; support both.
        model = doc.get("worksheet") if isinstance(doc, dict) else None
        if not isinstance(model, dict):
            return None
    else:
        model = doc["model"]
    name = model.get("name")
    if not name:
        return None
    tables: list[str] = []
    for mt in model.get("model_tables", model.get("tables", [])) or []:
        if isinstance(mt, dict) and mt.get("name"):
            tables.append(mt["name"])
    # De-dupe while preserving order.
    seen: set[str] = set()
    unique = [t for t in tables if not (t in seen or seen.add(t))]

    # Formulas defined on the worksheet: id/name -> expression.
    formulas: dict[str, dict[str, str]] = {}
    for fx in model.get("formulas", []) or []:
        if not isinstance(fx, dict):
            continue
        expr = (fx.get("expr") or "").strip()
        if not expr:
            continue
        rec = {"name": fx.get("name") or "", "expr": expr}
        if fx.get("id"):
            formulas[fx["id"]] = rec
        if fx.get("name"):
            formulas.setdefault("name:" + fx["name"], rec)

    # Worksheet columns: each is either sourced from a physical table column
    # (column_id: Table::Column) or derived from a formula (formula_id).
    columns: list[dict[str, Any]] = []
    for col in model.get("columns", []) or []:
        if not isinstance(col, dict) or not col.get("name"):
            continue
        props = col.get("properties", {}) or {}
        ctype = str(props.get("column_type", "")).upper()
        columns.append(
            {
                "name": col["name"],
                "description": (col.get("description") or "").strip(),
                "kind": "measure" if ctype == "MEASURE" else "attribute",
                "column_id": col.get("column_id"),
                "formula_id": col.get("formula_id"),
            }
        )

    return {
        "name": name,
        "guid": doc.get("guid"),
        "description": (model.get("description") or "").strip(),
        "tables": unique,
        "formulas": formulas,
        "columns": columns,
    }


# --------------------------------------------------------------------------- #
# Synapse notebook parsing (business logic + column derivations)
# --------------------------------------------------------------------------- #

import json as _json

_ALIAS_RE = re.compile(r"\.alias\(\s*[\"']([^\"']+)[\"']\s*\)")
_DEF_RE = re.compile(r"^def\s+([A-Za-z_]\w*)\s*\(", re.MULTILINE)
_DOCSTRING_RE = re.compile(r'"""(.*?)"""', re.DOTALL)
_MD_HEADER_RE = re.compile(r"^#+\s*(.+?)\s*$", re.MULTILINE)

# Hand-written, business-user-friendly summaries for the documented functions.
# Keyed by function name; missing functions simply show no blurb. Keep these in
# sync when functions are added/renamed in business_logic_func.
_PLAIN_ENGLISH: dict[str, str] = {
    "build_lead_refs":
        "Sets up the lookup tables used to connect Salesforce activities "
        "(tasks, calls, emails) back to the right lead. Built once per data "
        "load and reused by the activity-to-lead matching.",
    "channel_detail":
        "Classifies how a household was originally sourced into a detailed "
        "marketing channel (e.g. online, branding, advisor-driven), matching "
        "the ThoughtSpot 'Channel Detail' definition.",
    "client_segment":
        "Buckets a household into an AUM tier — 5M+, 1M–5M, 250k–1M, or "
        "<250k — using the larger of its terminated value or current total "
        "account value.",
    "combine_names":
        "Builds the household's display name from its contacts, leaving out "
        "anyone marked deceased (it never uses the raw lead name).",
    "deceased_flag":
        "Flags whether a contact is deceased — based on the name containing "
        "'deceased', a date of death, or a deceased indicator.",
    "employer_group":
        "Standardizes messy employer names and groups them into consistent "
        "employer categories used for reporting.",
    "finance_organic_2":
        "Labels a client as 'Acquisition' (came in through an acquired book "
        "of business) or 'Organic' (won directly by an advisor), matching the "
        "Finance_Organic_2 rules.",
    "get_division":
        "Assigns a household to a division/market: 'Airline' for the RAA "
        "business unit, 'Other Target Market' when a target-market flag is "
        "set, otherwise its standard division.",
    "get_filtered_lead_df":
        "Loads the set of leads used across the 360 build and filters out "
        "test/invalid records so downstream metrics only count real "
        "households.",
    "map_acq":
        "Works out a household's acquisition-source code from its acquisition "
        "source and business unit — how the client came to the firm.",
    "map_channel":
        "Rolls the detailed 'channel middle' value up into the high-level "
        "marketing channel (e.g. media-driven, advisor-driven, CRP).",
    "map_stage":
        "Translates a Salesforce opportunity stage name into the firm's "
        "standardized pipeline stage label.",
    "new_channel_middle":
        "Determines a household's 'channel middle' (how it was influenced or "
        "sourced), with a manual override for specific excluded households.",
    "normalize_billing_state":
        "Cleans up state values — turning abbreviations and variants into "
        "full, consistent state names — and groups them.",
    "pipeline_status_with_value":
        "Produces a pipeline status label prefixed with its stage number "
        "(e.g. '30 Proposal') so stages sort in the right order.",
    "resolve_activity_lead_id":
        "Traces a Salesforce task or event back to the lead it belongs to, "
        "covering both direct links and links through related records.",
}


def _notebook_cells(path: Path) -> list[dict[str, Any]]:
    try:
        doc = _json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ! failed to read notebook {path.name}: {exc}", file=sys.stderr)
        return []
    return (doc.get("properties", {}) or {}).get("cells", []) or []


def _cell_source(cell: dict[str, Any]) -> str:
    src = cell.get("source", "")
    if isinstance(src, list):
        return "".join(src)
    return str(src)


def _parse_business_logic(nb_dir: Path) -> dict[str, dict[str, Any]]:
    """Extract documented functions from business_logic_func.json."""
    path = nb_dir / "business_logic_func.json"
    funcs: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return funcs
    last_header = ""
    for cell in _notebook_cells(path):
        src = _cell_source(cell)
        if cell.get("cell_type") == "markdown":
            m = _MD_HEADER_RE.search(src.strip())
            if m:
                last_header = m.group(1).strip()
            continue
        for dm in _DEF_RE.finditer(src):
            name = dm.group(1)
            doc = ""
            ds = _DOCSTRING_RE.search(src[dm.start():])
            if ds:
                doc = ds.group(1).strip()
            funcs[name] = {
                "name": name,
                "title": last_header or name,
                "plain_english": _PLAIN_ENGLISH.get(name, ""),
                "description": doc,
                "source": src.strip(),
            }
    return funcs


def _extract_select_item(lines: list[str], idx: int) -> tuple[str, list[str]]:
    """Walk backward from a `.alias(...)` line to capture the select item
    expression (paren-balanced) plus any immediately preceding `#` comments."""
    block: list[str] = []
    i = idx
    while i >= 0 and len(block) < 22:
        block.append(lines[i])
        joined = "\n".join(reversed(block))
        balanced = joined.count("(") == joined.count(")")
        prev = lines[i - 1].strip() if i - 1 >= 0 else ""
        if balanced and (
            i == 0
            or prev == ""
            or prev.startswith("#")
            or prev.endswith(",")
            or prev.endswith("(")
            or prev.endswith("[")
        ):
            break
        i -= 1
    block.reverse()
    snippet = "\n".join(ln.rstrip() for ln in block).strip()
    comments: list[str] = []
    j = i - 1
    while j >= 0 and lines[j].strip().startswith("#"):
        comments.insert(0, lines[j].strip().lstrip("#").strip())
        j -= 1
    return snippet[:1500], comments


_NB_SKIP = ("_old", "_archive", "archived", "test_", "_test", "_v2", "backup")

# Bronze/silver source schemas -> the upstream system they represent. Read from
# `read_delta("<layer>", "<schema>/<table>")` calls in the load notebooks.
_READ_DELTA_RE = re.compile(r"read_delta\(\s*[\"'][^\"']*[\"']\s*,\s*[\"']([A-Za-z0-9_]+)/")
_SOURCE_SYSTEMS = {
    "sfp": "Salesforce",
    "sfp2": "Salesforce",
    "sfb2b": "Salesforce (B2B)",
    "tav": "Tamarac",
    "aip": "AIP (internal)",
    "hubspot": "HubSpot",
    "schwab": "Schwab",
    "fidelity": "Fidelity",
    "fnp": "FNP",
    "jira": "Jira",
    "on24": "ON24",
}
# Derived/warehouse layers and scratch schemas — not external source systems.
_SKIP_SCHEMAS = {"tho", "silver", "bronze", "gold", "gov", "dbo", "spark_temp", "temp"}


def _notebook_source_systems(text: str) -> list[str]:
    systems: list[str] = []
    for m in _READ_DELTA_RE.finditer(text):
        schema = m.group(1).lower()
        if schema in _SKIP_SCHEMAS:
            continue
        name = _SOURCE_SYSTEMS.get(schema, schema.upper())
        if name not in systems:
            systems.append(name)
    return systems


def _parse_column_logic(
    nb_dir: Path,
    tables_by_lower: dict[str, str],
    slug_by_name: dict[str, str],
    func_names: set[str],
) -> dict[str, dict[str, Any]]:
    """Map physical columns to the derivation logic that produces them, by
    scanning the tho_* load notebooks for `.alias("Col")` select items."""
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(nb_dir.glob("tho_*.json")):
        low = path.stem.lower()
        if any(x in low for x in _NB_SKIP):
            continue
        cand = path.stem[4:] if low.startswith("tho_") else path.stem
        table_name = tables_by_lower.get(cand.lower())

        lines: list[str] = []
        for cell in _notebook_cells(path):
            if cell.get("cell_type") != "code":
                continue
            src = cell.get("source", "")
            parts = src if isinstance(src, list) else [src]
            for ln in parts:
                lines.extend(ln.rstrip("\n").split("\n"))

        source_systems = _notebook_source_systems("\n".join(lines))

        for idx, ln in enumerate(lines):
            for am in _ALIAS_RE.finditer(ln):
                col = am.group(1)
                snippet, comments = _extract_select_item(lines, idx)
                used = sorted(
                    fn for fn in func_names
                    if re.search(r"\b" + re.escape(fn) + r"\s*\(", snippet)
                )
                # Keep only genuinely-derived columns (skip plain passthroughs).
                is_derived = bool(used) or bool(comments) or "when(" in snippet or "\n" in snippet
                if not is_derived:
                    continue
                key = f"{(table_name or path.stem).lower()}||{col.lower()}"
                if key in out:
                    continue
                out[key] = {
                    "table": table_name or path.stem,
                    "table_id": slug_by_name.get(table_name) if table_name else None,
                    "column": col,
                    "notebook": path.stem,
                    "source_systems": source_systems,
                    "expression": snippet,
                    "functions": used,
                    "comments": comments,
                }
    return out


# --------------------------------------------------------------------------- #
# Domain inference
# --------------------------------------------------------------------------- #

_DOMAIN_RULES = [
    ("Household", ("household", "hh_", "avhhid")),
    ("Account", ("account",)),
    ("Advisor", ("advisor", "user", "rls")),
    ("Pipeline", ("pipeline", "opportunity", "stage", "lead")),
    ("Activity", ("activity", "task", "event", "campaign", "zoom", "case")),
    ("Transactions", ("transaction", "distribution", "incomingfunds", "outflow")),
    ("Goals", ("goal", "netflows", "ncnm", "marketinggoals")),
    ("ML", ("prediction", "scoring", "term_pred")),
    ("Reference", ("datedimension", "acquisition", "custodian", "referral")),
    ("Logging", ("log", "tracker", "runlog")),
]


def _infer_domain(name: str) -> str:
    low = name.lower()
    for domain, hints in _DOMAIN_RULES:
        if any(h in low for h in hints):
            return domain
    return "Other"


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def build() -> None:
    tml_dir = _resolve_tml_dir()
    schema_index_path = _resolve_schema_index()
    print(f"TML source:    {tml_dir}")
    print(f"schema_index:  {schema_index_path or '(none)'}")

    enrichment = _load_schema_index(schema_index_path)
    idx = enrichment["tables_by_name"]
    deprecated = enrichment["deprecated"]

    # --- parse tables ---------------------------------------------------- #
    raw_tables: dict[str, dict[str, Any]] = {}  # bare_name.lower() -> parsed
    for f in sorted((tml_dir / "table").glob("*.table.tml")):
        parsed = _parse_table_tml(f)
        if parsed:
            raw_tables[parsed["name"].lower()] = parsed
    print(f"parsed {len(raw_tables)} tables")

    # --- parse worksheets ------------------------------------------------ #
    worksheets: list[dict[str, Any]] = []
    ws_membership: dict[str, list[str]] = {}  # table name -> [worksheet names]
    ws_dir = tml_dir / "worksheet"
    if ws_dir.is_dir():
        for f in sorted(ws_dir.glob("*.worksheet.tml")):
            ws = _parse_worksheet_tml(f)
            if not ws:
                continue
            worksheets.append(ws)
            for t in ws["tables"]:
                ws_membership.setdefault(t, [])
                if ws["name"] not in ws_membership[t]:
                    ws_membership[t].append(ws["name"])
    print(f"parsed {len(worksheets)} worksheets")

    # slug lookup by table name (for cross-links)
    slug_by_name = {p["name"]: slugify(p["name"]) for p in raw_tables.values()}

    # --- assemble per-table entries -------------------------------------- #
    _TABLES_DIR.mkdir(parents=True, exist_ok=True)
    # clear old generated table files
    for old in _TABLES_DIR.glob("*.yaml"):
        old.unlink()

    all_edges: list[dict[str, Any]] = []
    ai_tables: list[dict[str, Any]] = []
    written = 0

    for parsed in sorted(raw_tables.values(), key=lambda p: p["name"]):
        name = parsed["name"]
        bare = name.lower()
        slug = slug_by_name[name]
        meta = idx.get(bare, {})
        hot = meta.get("hot_columns", set())

        for col in parsed["columns"]:
            col["hot"] = col["name"].lower() in hot or col["db_column_name"].lower() in hot

        rels: list[dict[str, Any]] = []
        for j in parsed["joins"]:
            to_name = j.get("to")
            rels.append(
                {
                    "join_name": j.get("join_name"),
                    "to": to_name,
                    "to_id": slug_by_name.get(to_name, slugify(to_name) if to_name else None),
                    "type": j.get("type"),
                    "one_to_one": j.get("one_to_one"),
                    "on": j.get("on"),
                    "pairs": j.get("pairs"),
                }
            )
            # edge for the global graph
            for pair in j.get("pairs") or [{}]:
                all_edges.append(
                    {
                        "from": name,
                        "from_id": slug,
                        "to": to_name,
                        "to_id": slug_by_name.get(to_name, slugify(to_name) if to_name else None),
                        "from_col": pair.get("from_col"),
                        "to_col": pair.get("to_col"),
                        "type": j.get("type"),
                        "one_to_one": j.get("one_to_one"),
                        "join_name": j.get("join_name"),
                    }
                )

        entry = {
            "id": slug,
            "name": name,
            "schema": parsed["schema"],
            "db": parsed["db"],
            "db_table": parsed["db_table"],
            "guid": parsed["guid"],
            "business_name": meta.get("business_name"),
            "grain": meta.get("grain"),
            "pk": meta.get("pk"),
            "synonyms": meta.get("synonyms", []),
            "domain": _infer_domain(name),
            "deprecated": bare in deprecated,
            "spotter_enabled": parsed["spotter_enabled"],
            "description": "",  # curated in the UI later
            "notes": meta.get("notes"),
            "worksheets": ws_membership.get(name, []),
            "column_count": len(parsed["columns"]),
            "columns": parsed["columns"],
            "relationships": rels,
        }
        out_path = _TABLES_DIR / f"{slug}.yaml"
        out_path.write_text(
            yaml.safe_dump(entry, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )
        written += 1

        # compact AI rollup: only hot/PK columns to keep tokens small
        hot_cols = [c["name"] for c in parsed["columns"] if c["hot"]]
        ai_tables.append(
            {
                "name": name,
                "schema": parsed["schema"],
                "business_name": meta.get("business_name"),
                "grain": meta.get("grain"),
                "pk": meta.get("pk"),
                "synonyms": meta.get("synonyms", []),
                "deprecated": bare in deprecated,
                "hot_columns": hot_cols or [c["name"] for c in parsed["columns"][:12]],
            }
        )

    print(f"wrote {written} table files -> {_TABLES_DIR}")

    # --- de-duplicate edges ---------------------------------------------- #
    seen_edges: set[tuple] = set()
    edges: list[dict[str, Any]] = []
    for e in all_edges:
        key = (e["from_id"], e["to_id"], e.get("from_col"), e.get("to_col"))
        if key in seen_edges:
            continue
        seen_edges.add(key)
        edges.append(e)

    nodes = [
        {"id": slug_by_name[p["name"]], "name": p["name"], "domain": _infer_domain(p["name"])}
        for p in sorted(raw_tables.values(), key=lambda p: p["name"])
    ]

    _write(_DATA_DIR / "relationships.yaml", {"nodes": nodes, "edges": edges})

    # --- aggregate worksheet columns (unique field names across models) --- #
    ws_cols: dict[str, dict[str, Any]] = {}
    for ws in worksheets:
        ws_name = ws["name"]
        formulas = ws.get("formulas", {})
        for col in ws.get("columns", []):
            key = col["name"].lower()
            agg = ws_cols.setdefault(
                key,
                {
                    "name": col["name"],
                    "worksheets": [],
                    "sources": [],
                    "formulas": [],
                    "descriptions": [],
                    "kinds": set(),
                },
            )
            if ws_name not in agg["worksheets"]:
                agg["worksheets"].append(ws_name)
            agg["kinds"].add(col["kind"])
            desc = col.get("description")
            if desc and desc not in agg["descriptions"]:
                agg["descriptions"].append(desc)
            cid = col.get("column_id")
            if cid and "::" in cid:
                t, c = cid.split("::", 1)
                src = {"table": t, "column": c, "table_id": slug_by_name.get(t)}
                if src not in agg["sources"]:
                    agg["sources"].append(src)
            fid = col.get("formula_id")
            if fid:
                fx = formulas.get(fid) or formulas.get("name:" + str(fid))
                if fx and fx.get("expr"):
                    expr = fx["expr"]
                    if not any(f["expr"] == expr for f in agg["formulas"]):
                        agg["formulas"].append({"expr": expr, "worksheet": ws_name})

    ws_columns_out = []
    for agg in sorted(ws_cols.values(), key=lambda a: a["name"].lower()):
        agg["kinds"] = sorted(agg["kinds"])
        ws_columns_out.append(agg)

    # Lean worksheets.yaml (drop the heavy per-column/formula payload).
    worksheets_lean = [
        {
            "name": ws["name"],
            "guid": ws.get("guid"),
            "description": ws.get("description", ""),
            "tables": ws.get("tables", []),
            "column_count": len(ws.get("columns", [])),
        }
        for ws in worksheets
    ]

    _write(_DATA_DIR / "worksheets.yaml", {"worksheets": worksheets_lean})
    _write(_DATA_DIR / "worksheet_columns.yaml", {"columns": ws_columns_out})
    _write(_DATA_DIR / "glossary.yaml", {"glossary": enrichment["glossary"]})

    # --- business logic from the Synapse notebooks ----------------------- #
    nb_dir = _resolve_synapse_dir()
    business_logic: dict[str, dict[str, Any]] = {}
    column_logic: dict[str, dict[str, Any]] = {}
    if nb_dir:
        tables_by_lower = {p["name"].lower(): p["name"] for p in raw_tables.values()}
        business_logic = _parse_business_logic(nb_dir)
        column_logic = _parse_column_logic(
            nb_dir, tables_by_lower, slug_by_name, set(business_logic)
        )
        print(f"Synapse notebooks: {nb_dir}")
    else:
        print("Synapse notebooks: (not found — skipping business logic)")
    _write(
        _DATA_DIR / "business_logic.yaml",
        {"functions": sorted(business_logic.values(), key=lambda f: f["name"].lower())},
    )
    _write(_DATA_DIR / "column_logic.yaml", {"columns": list(column_logic.values())})
    _write(
        _DATA_DIR / "ai_index.yaml",
        {
            "note": (
                "Compact schema catalog for LLM system-prompt injection. "
                "Generated from ThoughtSpot TML + schema_index.yaml."
            ),
            "glossary": enrichment["glossary"],
            "tables": ai_tables,
            "join_hints": enrichment["join_hints"],
            "few_shot": enrichment["few_shot"],
        },
    )
    print(f"wrote relationships.yaml ({len(nodes)} nodes, {len(edges)} edges)")
    print(f"wrote worksheets.yaml, worksheet_columns.yaml ({len(ws_columns_out)} cols), glossary.yaml, ai_index.yaml")
    print(f"wrote business_logic.yaml ({len(business_logic)} functions), column_logic.yaml ({len(column_logic)} columns)")


def _write(path: Path, data: Any) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )


if __name__ == "__main__":
    build()
