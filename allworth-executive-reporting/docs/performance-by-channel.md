# Performance by Channel — Data Flow (Back End → Front End)

This document describes how the **Performance by Channel** reporting tab is
currently wired, from the Azure Synapse warehouse through the Flask API to the
React page that renders the KPI matrix.

> Route: `/reporting/kpi` (also the catch-all `*`) · Page title: **Performance by Channel** ·
> Access gated by `ToolGuard toolId="performance"`.

---

## 1. The big picture

```
Azure Synapse (DataWarehouse)
        │   3 T-SQL queries
        ▼
Flask builders  ──►  in-process cache (5 min TTL)
  _build_kpi_metrics()
  _build_net_flows()
  _build_detailed_metrics()
        │
        ▼
GET /api/all-metrics   (single combined response)
        │
        ▼
services/api.ts  ── fetchAllMetrics() + transformApiMetrics()  (snake_case → camelCase)
        │
        ▼
main.tsx  ── bootstrap() → renderApp(kpiMetrics, netFlows, detailedMetrics)
        │
        ▼
<Reporting/>  (presentational only — receives 3 datasets as props)
        │  time-bucketing + lookup maps
        ▼
Left column: <KpiTile/>  ·  Grid: <ExpandableRow/> → <KpiTile/>  ·  <TrendlineModal/>
```

Key fact: **`Reporting.tsx` fetches nothing.** It is a pure render component fed
three datasets. All data acquisition happens once, at bootstrap, in `main.tsx`.

---

## 2. Backend (`backend/app.py`)

Three builder functions each run one Synapse query and shape a JSON payload.
Every result is stored in a process-local cache with a default **5-minute TTL**
(`CACHE_TTL_SECONDS`, env-overridable — `backend/app.py:199`). The cache means
most requests never touch the database.

Connection settings (`backend/app.py:228`):

| Setting | Env var | Default |
|---|---|---|
| Server | `SYNAPSE_SERVER` | `allworthsynapse.sql.azuresynapse.net` |
| Database | `SYNAPSE_DATABASE` | `DataWarehouse` |
| ODBC driver | `ODBC_DRIVER` | `{ODBC Driver 18 for SQL Server}` |
| Auth method | `AUTH_METHOD` | `ActiveDirectoryInteractive` |

### 2.1 `_build_kpi_metrics()` — the channel matrix (`app.py:700`)

The main KPI grid data.

- **Source tables:** `aip.goals_20260109` (goals) `LEFT JOIN tho.Combined_Fact`
  (actuals) on `cf.Goal_First_Touch_ID = g.Unique_ID`.
- **Metrics:** `1 - Leads`, `2 - Appointments Completed`, `3 - New Clients`,
  `4 - NCNM`.
- **Window:** last 15 months (`DATEADD(month, -15, GETDATE())` → `EOMONTH(GETDATE())`).
- **Prior year:** a second CTE (`PriorYearData`) pulls actuals from ~15–27 months
  ago and shifts them forward one year (`DATEADD(year, 1, g.Date)`) so PY lines up
  with the current period.
- **Channel roll-up (pandas):** raw warehouse channels are mapped up to the five
  display channels via `CHANNEL_MAP` (`app.py:254`), then grouped and summed.
- **NCNM scaling:** NCNM actual/goal/PY are divided by 1,000,000 → **millions**.
- **Proration:** for the current (partial) month, PY and goal are prorated by
  `days_elapsed / days_in_month` into `py_prorated` / `goal_prorated`.
- **Total row:** a synthetic `channel = 'Total'` row is computed per metric/period
  by summing all channels.

### 2.2 `_build_net_flows()` — the left column (`app.py:792`)

Feeds the Net Flows column on the left of the page.

- **Source tables:** `tho.Household_Rollforward` (actual NCNM / ECNM /
  Distribution / Attrition / expenses) + `aip.Goals_Net_Flows_2025` (goals),
  joined on reporting-period keys; PY via a year-shifted CTE.
- **Emits 5 metrics**, all `channel = 'Total'`, in **millions**:
  `Net Flows`, `NCNM_NF`, `ECNM`, `Distributions`, `Attrition`.
- Same current-month proration as above.

### 2.3 `_build_detailed_metrics()` — drill-down granularity (`app.py:888`)

Powers the expand-a-row drill-down.

- Same query shape as the KPI matrix, but keeps the raw channel as
  **`channel_middle`**, then maps it to:
  - a **parent** display channel via `CHANNEL_PARENT_MAP` (`app.py:1000`), and
  - a **display name** via `CHANNEL_MIDDLE_DISPLAY` (`app.py:1019`).
- Example: `referral`, `promoter`, `advisor driven` all roll up to parent
  **Advisor Enabled** while retaining their own sub-rows.

### 2.4 Combined endpoint `GET /api/all-metrics` (`app.py:969`)

The endpoint the frontend actually calls.

- Runs the three builders through `_safe_build`, so a single dataset's failure is
  isolated (returns `{ success: False, data: [] }`) rather than failing the whole
  response.
- Queries run **sequentially** on the shared Synapse connection to avoid
  "connection busy" errors; the cache keeps this cheap.
- Response shape:

```json
{
  "success": true,
  "kpiMetrics":      { "success": true, "data": [ ... ], "count": N },
  "netFlows":        { "success": true, "data": [ ... ], "count": N },
  "detailedMetrics": { "success": true, "data": [ ... ], "count": N }
}
```

Individual endpoints also exist and share the same builders + cache:
`GET /api/kpi-metrics`, `GET /api/net-flows`, `GET /api/kpi-metrics-detailed`.

### 2.5 Row shape returned by the builders

Each row in a `data` array (snake_case):

| Field | Meaning |
|---|---|
| `metric_name` | `Leads` / `Appointments` / `Clients` / `NCNM` (or net-flow metric) |
| `channel` | Display channel (`Total`, `Advisor Enabled`, `CRP`, `Paid Leads`, `Media`) |
| `channel_middle` | Sub-channel (detailed dataset only) |
| `period` | Month label, e.g. `"Jan 2026"` |
| `actual_value` | Actual |
| `goal_value` | Goal / plan |
| `py_actual_value` | Prior-year actual (full month) |
| `py_prorated` | Prior-year actual, prorated for current month |
| `goal_prorated` | Goal, prorated for current month |
| `currency` / `unit` | `USD` / `millions` for NCNM & net flows; else `count` |

### 2.6 Mapping constants

- **`METRIC_MAP`** (`app.py:246`) — `'1 - Leads' → 'Leads'`, etc.
- **`CHANNEL_MAP`** (`app.py:254`) — raw channel → one of the 5 display channels.
  E.g. `fidelity`/`schwab`/`crp` → **CRP**; `radio`/`other media`/`target market`/
  `media driven` → **Media**.
- **`CHANNEL_PARENT_MAP`** (`app.py:1000`) & **`CHANNEL_MIDDLE_DISPLAY`**
  (`app.py:1019`) — used only by the detailed builder.

---

## 3. Frontend transform (`frontend/src/services/api.ts`)

- **`fetchAllMetrics()`** — GETs `/api/all-metrics` (45s timeout). On any failure it
  falls back to `fetchAllMetricsSequential()`, which hits the three single
  endpoints one at a time.
- **`transformApiMetrics()`** — converts each raw row into the app's `KpiEntry`
  type (`frontend/src/types/kpi.ts`), i.e. snake_case → camelCase:
  `actual_value → actual`, `goal_value → goal`, `py_actual_value → pyActual`,
  `py_prorated → pyProrated`, `goal_prorated → goalProrated`,
  `channel_middle → channelMiddle`. A stable `id` is slugified from
  metric/channel/period.
- Same-origin `/api/` requests are automatically decorated with an Azure AD Bearer
  token by the global fetch wrapper installed via `installAuthFetch()` in
  `main.tsx` — services do **not** add auth headers themselves.

---

## 4. Bootstrap (`frontend/src/main.tsx`)

`bootstrap()` (`main.tsx:430`) runs on page load:

1. Render a loading screen.
2. If `DEMO_MODE`, render bundled `demoMetrics` (no auth, no backend) and stop.
3. Otherwise run Azure AD SSO (`ensureAuthenticated()`), then `installAuthFetch()`.
4. Render the page **shell** immediately with empty data + `isLoading=true` so the
   hero and controls are visible while data loads.
5. `await fetchAllMetrics()`, then `renderApp(kpiMetrics, netFlows, detailedMetrics)`
   with the real datasets.

`renderApp()` (`main.tsx:251`) wires the datasets into the router and passes them
to `<Reporting metrics=… netFlowsMetrics=… detailedMetrics=… isLoading=… />`.

> Note: `main.tsx` also contains a `parseMetricsFromRows()` ThoughtSpot fallback
> path. The primary path for this tab is the backend API described above.

---

## 5. The page (`frontend/src/Reporting.tsx`)

Presentational. Given the three prop datasets it:

1. **Time-buckets** the monthly-grained data using
   `frontend/src/utils/timeBuckets.ts`:
   - `buildBucketDescriptors(periods, mode)` builds the selectable periods for the
     active toggle — **Monthly** (5 most recent months), **Quarterly** (5 most
     recent quarters), **YTD** (one bucket per year).
   - `aggregateEntries(entries, memberPeriods, bucketKey)` sums the numeric fields
     (`actual`, `goal`, `pyActual`, `pyProrated`, `goalProrated`, `target`,
     `budget`) across the months in the bucket, per metric/channel/channelMiddle.
2. **Builds lookup maps** for O(1) rendering:
   - `metricsMap` keyed `` `${metric}-${channel}` ``
   - `netFlowsMap` keyed by metric
   - `detailedMetricsMap` keyed `` `${metric}-${channel}` `` → array of sub-rows
3. **Renders:**
   - **Left column** — fixed `NET_FLOW_METRICS`
     (`Net Flows`, `NCNM_NF`→"NCNM", `ECNM`, `Distributions`, `Attrition`) as
     `KpiTile`s.
   - **Grid** — fixed `CHANNELS` (`Total`, `Advisor Enabled`, `CRP`, `Paid Leads`,
     `Media`) × `METRICS` (`NCNM`, `Clients`, `Appointments`, `Leads`) as
     `ExpandableRow`s. Expanding a row shows its `channel_middle` sub-rows.
   - **Trendline** — right-clicking a tile opens `TrendlineModal` built from the
     last 12 months of matching entries across all three datasets.

### 5.1 Controls

- **Yellow threshold** (default 80%) — the cutoff between "near goal" (yellow) and
  "off track" (red).
- **Time bucket toggle** — Monthly / Quarterly / YTD.
- **Period selector** — the buckets for the active mode.
- **Prorated note** — shown when the active bucket includes the current
  (partial) month.

### 5.2 Tile status coloring (`frontend/src/components/KpiTile.tsx`)

- Uses prorated values for the current month (`pyProrated`/`goalProrated`), full
  values otherwise.
- **Positive metrics** (higher is better): green `≥ 100%` of plan, yellow `≥ threshold%`,
  red below.
- **Negative metrics** (`Distributions`, `Attrition` — less outflow is better):
  green when `|actual| ≤ |plan|`, yellow within threshold, red beyond.
- Formatting: NCNM/net-flows render as `$Xm` (millions); counts render plain;
  `percent` units render with `%`.

---

## 6. Where to change things

| Want to change… | Edit here |
|---|---|
| Which channels/metrics show & their order | `CHANNELS` / `METRICS` / `NET_FLOW_METRICS` in `Reporting.tsx:22-26` |
| How raw DB channels roll up | `CHANNEL_MAP`, `CHANNEL_PARENT_MAP`, `CHANNEL_MIDDLE_DISPLAY` in `app.py` |
| Metric label mapping | `METRIC_MAP` (`app.py:246`) |
| Source tables / date windows | the SQL inside the three `_build_*` functions |
| Cache freshness | `CACHE_TTL_SECONDS` env (default 300s) |
| Threshold default | `yellowThreshold` initial state in `Reporting.tsx` |
| Bucket rules (how many months/quarters) | `buildBucketDescriptors` in `utils/timeBuckets.ts` |

---

## 7. Current caveats

- **Hardcoded goals snapshot.** The KPI and detailed queries read from
  `aip.goals_20260109` — a dated snapshot table. Goal data will go stale unless
  that table name is bumped when a new goals snapshot lands. (Net flows use
  `aip.Goals_Net_Flows_2025`, also year-stamped.)
- **In-process cache only.** The 5-minute cache lives in the Flask process; it is
  not shared across workers/instances and resets on restart.
- **Sequential Synapse queries.** `/api/all-metrics` runs the three queries
  serially on one connection by design (to avoid "connection busy"); first
  cold-cache load pays the sum of the three query times.

---

## 8. File reference

| Layer | File |
|---|---|
| Page (render) | `frontend/src/Reporting.tsx`, `frontend/src/Reporting.css` |
| Tiles / rows | `frontend/src/components/KpiTile.tsx`, `ExpandableRow.tsx`, `TrendlineModal.tsx` |
| Time bucketing | `frontend/src/utils/timeBuckets.ts` |
| Types | `frontend/src/types/kpi.ts` |
| Fetch + transform | `frontend/src/services/api.ts` |
| Bootstrap / routing | `frontend/src/main.tsx` |
| API + builders + SQL | `backend/app.py` (`_build_kpi_metrics`, `_build_net_flows`, `_build_detailed_metrics`, `/api/all-metrics`) |
