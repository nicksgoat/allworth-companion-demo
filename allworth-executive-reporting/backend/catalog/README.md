# Data Catalog — `tho` warehouse dictionary

Mounted at `/catalog` in the main Flask app. A searchable, visually explorable
dictionary of the `tho` data warehouse: tables, columns, types, join
relationships (ER graph), a business glossary, and column-level where-used
lineage. The structured data is designed to double as **AI context** for a
future MCP server.

## Layout

```
backend/catalog/
├── __init__.py
├── generate.py          # build step: TML + schema_index.yaml -> data/
├── loader.py            # loads data/ into memory, hot-reload, curation overlay
├── handler.py           # search / facets / table detail / graph / where-used
├── storage.py           # curated overlay writes + append-only history
├── routes.py            # Flask Blueprint (mount at /catalog)
├── templates/index.html # self-contained SPA shell
├── static/{app.js,styles.css}
└── data/                # GENERATED — do not hand-edit tables/*
    ├── tables/<slug>.yaml     one structured entry per table
    ├── relationships.yaml     ER graph nodes + edges
    ├── worksheets.yaml        worksheet -> member tables + description
    ├── worksheet_columns.yaml unique worksheet fields -> models, source table, formula, description
    ├── business_logic.yaml    documented functions from business_logic_func (name, docstring, source)
    ├── column_logic.yaml      physical column -> derivation (expression, functions, comments, notebook)
    ├── glossary.yaml          business term glossary
    ├── ai_index.yaml          compact rollup for LLM system-prompt injection
    └── overlays/<slug>.yaml   CURATED edits (survive regeneration)
```

## Regenerating the catalog data

`data/tables/*`, `relationships.yaml`, `worksheets.yaml`, `glossary.yaml` and
`ai_index.yaml` are generated from two sources:

1. The **ThoughtSpot TML** version-control repo (`table/*.tml` for columns +
   table-level `joins_with`, `worksheet/*.tml` for model grouping + AI
   descriptions).
2. The curated **`schema_index.yaml`** (business names, grain, PKs, synonyms,
   hot columns, glossary, join hints, few-shot SQL, deprecated list).

```powershell
$env:CATALOG_TML_DIR="C:\path\to\thoughtspot_tml_version_control"
$env:CATALOG_SCHEMA_INDEX="C:\path\to\schema_index.yaml"   # optional enrichment
$env:CATALOG_SYNAPSE_DIR="C:\path\to\allworthsynapse\notebook"  # optional business logic
python backend\catalog\generate.py
```

Or use the wrapper, which resolves the source paths and can pull first:

```powershell
.\scripts\refresh-catalog.ps1 -Pull
```

**Refresh cadence.** Generation is pure parsing (no Spark/compute), so it's cheap.
Weekly is a reasonable schedule for this reference metadata; add an on-demand run
for when someone ships a logic change they want reflected immediately. Wire
`refresh-catalog.ps1` into an Azure DevOps pipeline / GitHub Actions cron, or a
scheduled task, publishing the regenerated `data/` to the app's `CATALOG_DATA_DIR`
(or committing it back).

## SQL source of truth — `meta.Data_Dictionary_*`

The generated `data/` is also published to Synapse as the single source of truth
for the whole platform (frontends + the wealth-mcp AI). Four tables in the `meta`
schema of `DataWarehouse`:

| Table | Contents |
|---|---|
| `meta.Data_Dictionary_Table` | one row per table (business name, grain, PK, domain, synonyms, deprecated, worksheets) |
| `meta.Data_Dictionary_Column` | one row per column (type, kind, aggregation, PII/hot flags, derivation expression, source notebook/systems) |
| `meta.Data_Dictionary_Join` | ER edges (from/to table + column, join type, cardinality) |
| `meta.Data_Dictionary_Glossary` | business term glossary |

- `sql_export.py` — pure transform: reads `data/` → four relational row sets.
- `sql/data_dictionary.sql` — DDL (Synapse **dedicated** pool: `meta` schema, `REPLICATE`/`HEAP`).
- `sql_publish.py` — (re)creates the tables and loads the rows (full replace each run).

```powershell
# Dry run — writes CSVs to data/sql_export/, no DB:
python -m catalog.sql_publish --dry-run

# Publish to Synapse (AAD token via Azure CLI):
$env:AUTH_METHOD="AccessToken"
$env:AZURE_SQL_ACCESS_TOKEN=(az account get-access-token --resource https://database.windows.net/ --query accessToken -o tsv)
python -m catalog.sql_publish
```

Or regenerate **and** publish in one step:

```powershell
.\scripts\refresh-catalog.ps1 -Pull -Publish
```

The wealth-mcp `data_dictionary` tool reads these tables at runtime, so a publish
is immediately reflected in the AI's business-context lookups.

## Env vars

| Var | Purpose |
|---|---|
| `CATALOG_TML_DIR` | (generate) path to `thoughtspot_tml_version_control`. |
| `CATALOG_SCHEMA_INDEX` | (generate) path to `schema_index.yaml` enrichment. |
| `CATALOG_SYNAPSE_DIR` | (generate) path to `allworthsynapse/notebook` for business-logic parsing. |
| `CATALOG_DATA_DIR` | Override the served data dir (mount a shared volume). |
| `AUTH_METHOD` | (publish) `AccessToken` (default), `ServicePrincipal`, `SqlPassword`, or `ActiveDirectoryInteractive`. |
| `AZURE_SQL_ACCESS_TOKEN` | (publish) AAD token when `AUTH_METHOD=AccessToken`. |
| `CATALOG_RELOAD_CHECK_SECONDS` | Hot-reload poll interval (default 30). |
| `CATALOG_USER` | Dev-mode identity fallback for curation attribution. |
| `CATALOG_ADMIN_TOKEN` | Required for `POST /catalog/api/admin/reload`. |

Identity for curation history is pulled from `X-MS-Client-Principal-Name`
(Azure Easy Auth) or `X-User-Email`, matching Jarvis.

## API

- `GET  /catalog/` — SPA shell.
- `GET  /catalog/api/tables?q=&schema=&domain=&kind=&pii=&deprecated=` — faceted list.
- `GET  /catalog/api/tables/<slug>` — full table detail (+ inbound relationships).
- `GET  /catalog/api/graph?worksheet=<name>` — ER graph nodes + edges.
- `GET  /catalog/api/worksheets` — worksheet list (for the graph selector).
- `GET  /catalog/api/columns/<column>/where-used` — column lineage.
- `GET  /catalog/api/glossary` — business glossary.
- `GET  /catalog/api/facets` — facet counts.
- `PUT  /catalog/api/tables/<slug>/curation` — write curated description / notes /
  column descriptions (stored in `overlays/`, logged to history).
- `GET  /catalog/api/tables/<slug>/history`, `GET /catalog/api/history` — audit log.
- `GET  /catalog/api/me`, `POST /catalog/api/admin/reload`.

## AI / MCP readiness (structure, not yet wired)

The data layer is intentionally shaped so an MCP server can read the same files
(point it at `CATALOG_DATA_DIR`) and expose:

- **Resources** — `catalog://table/<slug>` (per-table YAML),
  `catalog://ai-index` (`ai_index.yaml`, a token-efficient warehouse summary
  for system-prompt injection), `catalog://glossary`.
- **Tools** — `search_catalog(q, facets)` → `handler.list_tables`;
  `get_table(slug)` → `handler.get_table`;
  `related_tables(slug)` → relationships from the table entry;
  `where_used(column)` → `handler.where_used`.

`handler.py` has **no Flask imports**, so those functions can back the MCP tools
directly. `ai_index.yaml` is the recommended context payload: glossary + one
compact line per table (business name, grain, PK, synonyms, hot columns) plus
join hints and few-shot SQL — the successor to the standalone `schema_index.yaml`.
