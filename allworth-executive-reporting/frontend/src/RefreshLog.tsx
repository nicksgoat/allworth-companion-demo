// src/RefreshLog.tsx
// Standalone page that surfaces the ADLS Gen2 Delta table
// `abfss://silver@dlallworthai.dfs.core.windows.net/logging/transformation_log/`
// in real time via the backend /api/transformation-log endpoint.
//
// This component is intentionally self-contained — it does NOT depend on the
// Synapse KPI data flow, so a Synapse outage cannot affect it.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchTransformationLog,
  type TransformationLogResponse,
  type TransformationLogRow,
} from './services/refreshLog';
import PipelineNav from './components/PipelineNav';
import SideNav from './components/SideNav';
import {
  TZ_OPTIONS,
  sameDayInTz,
  useTimezone,
  type TzKey,
} from './services/timezone';
import './Tamarac2.css';
import './RefreshLog.css';

const DEFAULT_LIMIT = 500;
const AUTO_REFRESH_MS = 30_000;
const FILTERABLE_COLUMNS = [
  'notebook_name',
  'start_time',
  'run_time_minutes',
  'result',
  'hours_since_refresh',
] as const;
const SORTABLE_COLUMNS = new Set<string>(FILTERABLE_COLUMNS);
const ERROR_COLUMN = 'error_message';
const ERROR_PREVIEW_CHARS = 140;
const HOURS_SINCE_REFRESH = 'hours_since_refresh';

type SortDir = 'asc' | 'desc';

const formatCell = (value: unknown): string => {
  if (value == null) return '';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value.toLocaleString() : '';
  }
  return String(value);
};

const compareValues = (a: unknown, b: unknown): number => {
  // nulls last
  const aNull = a == null || a === '';
  const bNull = b == null || b === '';
  if (aNull && bNull) return 0;
  if (aNull) return 1;
  if (bNull) return -1;
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  // Try numeric compare for numeric strings
  const na = typeof a === 'string' ? Number(a) : NaN;
  const nb = typeof b === 'string' ? Number(b) : NaN;
  if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
  // Try date compare
  if (typeof a === 'string' && typeof b === 'string') {
    const da = Date.parse(a);
    const db = Date.parse(b);
    if (Number.isFinite(da) && Number.isFinite(db)) return da - db;
  }
  return String(a).localeCompare(String(b));
};

const RefreshLog = () => {
  const [data, setData] = useState<TransformationLogResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sortCol, setSortCol] = useState<string>('start_time');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());
  const [tz, setTz, tzOption] = useTimezone();
  const [todayOnly, setTodayOnly] = useState<boolean>(true);
  const abortRef = useRef<AbortController | null>(null);

  const formatDateTimeInTz = useCallback(
    (value: unknown): string => {
      if (value == null || value === '') return '';
      const d = new Date(value as string | number);
      if (Number.isNaN(d.getTime())) return formatCell(value);
      return new Intl.DateTimeFormat(undefined, {
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        timeZone: tzOption.iana,
      }).format(d);
    },
    [tzOption.iana]
  );

  const load = useCallback(async (opts: { manual?: boolean } = {}) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const body = await fetchTransformationLog({
        limit: DEFAULT_LIMIT,
        noCache: opts.manual === true,
        signal: ctrl.signal,
      });
      setData(body);
    } catch (e) {
      if ((e as Error).name === 'AbortError') return;
      setError((e as Error).message || 'Unknown error');
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => abortRef.current?.abort();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const id = window.setInterval(() => { void load(); }, AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [autoRefresh, load]);

  const rawColumns = useMemo(() => data?.columns ?? [], [data]);
  const rawRows: TransformationLogRow[] = useMemo(() => data?.rows ?? [], [data]);

  // Insert a synthetic "hours_since_refresh" column right after start_time
  // (or at the end if start_time is absent). Value = whole hours between the
  // row's last_successful_run and now.
  const columns = useMemo(() => {
    if (rawColumns.length === 0) return rawColumns;
    if (rawColumns.includes(HOURS_SINCE_REFRESH)) return rawColumns;
    const idx = rawColumns.indexOf('start_time');
    const insertAt = idx >= 0 ? idx + 1 : rawColumns.length;
    return [
      ...rawColumns.slice(0, insertAt),
      HOURS_SINCE_REFRESH,
      ...rawColumns.slice(insertAt),
    ];
  }, [rawColumns]);

  const nowMs = data ? Date.parse(data.fetched_at) || Date.now() : Date.now();
  const augmentedRows: TransformationLogRow[] = useMemo(() => {
    return rawRows.map((row) => {
      const raw = row['last_successful_run'] ?? row['start_time'];
      const t = raw ? Date.parse(String(raw)) : NaN;
      const hours = Number.isFinite(t)
        ? Math.max(0, Math.floor((nowMs - t) / 3_600_000))
        : null;
      return { ...row, [HOURS_SINCE_REFRESH]: hours };
    });
  }, [rawRows, nowMs]);

  const displayRows = useMemo(() => {
    let result = augmentedRows;

    // Today-only filter (based on selected timezone)
    if (todayOnly) {
      const ref = new Date();
      result = result.filter((row) =>
        sameDayInTz(row['start_time'] as string | null | undefined, ref, tz)
      );
    }

    // Apply per-column filters
    const activeFilters = Object.entries(filters).filter(([, v]) => v.trim().length > 0);
    if (activeFilters.length > 0) {
      result = result.filter((row) =>
        activeFilters.every(([col, needle]) => {
          const cell = formatCell(row[col]).toLowerCase();
          return cell.includes(needle.trim().toLowerCase());
        })
      );
    }

    // Sort
    if (sortCol && columns.includes(sortCol)) {
      const dir = sortDir === 'asc' ? 1 : -1;
      result = [...result].sort((a, b) => compareValues(a[sortCol], b[sortCol]) * dir);
    }
    return result;
  }, [augmentedRows, filters, sortCol, sortDir, columns, todayOnly, tz]);

  const toggleSort = (col: string) => {
    if (!SORTABLE_COLUMNS.has(col)) return;
    if (sortCol === col) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
    } else {
      setSortCol(col);
      setSortDir('asc');
    }
  };

  const toggleExpand = (idx: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  const sortIndicator = (col: string) => {
    if (!SORTABLE_COLUMNS.has(col)) return '';
    if (sortCol !== col) return ' ↕';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  };

  return (
    <div className="t2-page has-sidenav">
      <SideNav />
      {/* Animated background orbs (Jarvis-style) */}
      <div className="t2-bg" aria-hidden="true">
        <div className="t2-orb t2-orb-1" />
        <div className="t2-orb t2-orb-2" />
        <div className="t2-orb t2-orb-3" />
        <div className="t2-orb t2-orb-4" />
        <div className="t2-orb t2-orb-5" />
      </div>

      <div className="t2-shell">
        <header className="t2-hero">
          <div className="t2-kicker-row">
            <div className="t2-kicker">Pipeline · Full Log</div>
            <PipelineNav />
          </div>
          <h1 className="t2-title">Transformation Log</h1>
          <p className="t2-lede">
            Every recorded run of the Tamarac notebook pipeline, sourced
            from{' '}
            <code className="refresh-log-code">
              {data?.source ?? 'loading…'}
            </code>
            . Click a column header to sort, or filter inline below.
          </p>

          <div className="t2-meta-row">
            <div className="refresh-log-meta">
              {data && (
                <>
                  <span>
                    <strong>{displayRows.length.toLocaleString()}</strong>
                    {displayRows.length !== augmentedRows.length && (
                      <>
                        {' '}of{' '}
                        <strong>{augmentedRows.length.toLocaleString()}</strong>
                      </>
                    )}{' '}
                    rows
                  </span>
                  <span>
                    Fetched {formatDateTimeInTz(data.fetched_at)} ·{' '}
                    {tzOption.short}
                  </span>
                </>
              )}
              {loading && !data && <span>Loading…</span>}
            </div>
            <div className="t2-actions">
              <label className="t2-toggle">
                <input
                  type="checkbox"
                  checked={todayOnly}
                  onChange={(e) => setTodayOnly(e.target.checked)}
                />
                <span>Today only</span>
              </label>
              <label className="t2-toggle">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                <span>Auto-refresh</span>
              </label>
              <select
                className="t2-tz-select"
                value={tz}
                onChange={(e) => setTz(e.target.value as TzKey)}
                aria-label="Display timezone"
              >
                {TZ_OPTIONS.map((o) => (
                  <option key={o.key} value={o.key}>
                    {o.label} ({o.short})
                  </option>
                ))}
              </select>
              <button
                className="t2-btn t2-btn-primary"
                onClick={() => {
                  void load({ manual: true });
                }}
                disabled={loading}
              >
                {loading ? 'Refreshing…' : 'Refresh'}
              </button>
            </div>
          </div>
        </header>

        {error && (
          <div className="t2-error-banner">
            <strong>Error:</strong> {error}
          </div>
        )}

        <section className="t2-card refresh-log-table-card">
          <div className="refresh-log-table-wrap">
            {columns.length === 0 && !loading && !error && (
              <div className="refresh-log-empty">No rows returned.</div>
            )}
            {columns.length > 0 && (
              <table className="refresh-log-table">
                <thead>
                  <tr>
                    {columns.map((c) => {
                      const sortable = SORTABLE_COLUMNS.has(c);
                      return (
                        <th
                          key={c}
                          className={sortable ? 'refresh-log-th-sortable' : undefined}
                          onClick={sortable ? () => toggleSort(c) : undefined}
                        >
                          {c}
                          {sortIndicator(c)}
                        </th>
                      );
                    })}
                  </tr>
                  <tr className="refresh-log-filter-row">
                    {columns.map((c) => (
                      <th key={c}>
                        {FILTERABLE_COLUMNS.includes(
                          c as (typeof FILTERABLE_COLUMNS)[number]
                        ) ? (
                          <input
                            className="refresh-log-filter-input"
                            type="text"
                            placeholder="Filter…"
                            value={filters[c] ?? ''}
                            onChange={(e) =>
                              setFilters((prev) => ({
                                ...prev,
                                [c]: e.target.value,
                              }))
                            }
                          />
                        ) : null}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {displayRows.map((row, i) => (
                    <tr key={i}>
                      {columns.map((c) => {
                        if (c === ERROR_COLUMN) {
                          const full = formatCell(row[c]);
                          const expanded = expandedRows.has(i);
                          const needsClip = full.length > ERROR_PREVIEW_CHARS;
                          const shown =
                            !needsClip || expanded
                              ? full
                              : full.slice(0, ERROR_PREVIEW_CHARS) + '…';
                          return (
                            <td key={c} className="refresh-log-td-error">
                              <div
                                className={
                                  expanded
                                    ? 'refresh-log-error-full'
                                    : 'refresh-log-error-clip'
                                }
                                title={!expanded && needsClip ? full : undefined}
                              >
                                {shown}
                              </div>
                              {needsClip && (
                                <button
                                  type="button"
                                  className="refresh-log-expand-btn"
                                  onClick={() => toggleExpand(i)}
                                >
                                  {expanded ? 'Collapse' : 'Expand'}
                                </button>
                              )}
                            </td>
                          );
                        }
                        if (c === 'start_time' || c === 'last_successful_run') {
                          return <td key={c}>{formatDateTimeInTz(row[c])}</td>;
                        }
                        if (c === HOURS_SINCE_REFRESH) {
                          const v = row[c];
                          return (
                            <td key={c} className="refresh-log-td-num">
                              {typeof v === 'number' ? v.toString() : '—'}
                            </td>
                          );
                        }
                        return <td key={c}>{formatCell(row[c])}</td>;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default RefreshLog;
