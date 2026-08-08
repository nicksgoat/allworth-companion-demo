// src/Tamarac2.tsx
// Jarvis-styled variant of the Tamarac pipeline view.
// Local-only design experiment — mirrors the logic of Tamarac.tsx but wraps
// the content in Jarvis's light glass-morphism chrome.

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
  formatClockInTz,
  sameDayInTz,
  useTimezone,
  type TzKey,
} from './services/timezone';
import './Tamarac2.css';

// Notebooks are selected dynamically from the transformation_log by
// refresh_group = 'tamarac'. Baseline order is derived from each notebook's
// earliest observed start_time in the fetched window.
const REFRESH_GROUP = 'tamarac';

const AUTO_REFRESH_MS = 30_000;
const FETCH_LIMIT = 1000;

type Status = 'not_started' | 'running' | 'success' | 'failure';

interface NotebookState {
  name: string;
  status: Status;
  lastRun?: TransformationLogRow;
}

const sameLocalDay = (
  iso: string | null | undefined,
  ref: Date,
  tz: TzKey
): boolean => sameDayInTz(iso, ref, tz);

const normalizeResult = (v: unknown): string => {
  if (v == null) return '';
  return String(v).trim().toLowerCase();
};

const classifyRow = (
  row: TransformationLogRow,
  today: Date,
  tz: TzKey
): Status | null => {
  const startTime = row['start_time'];
  if (!sameLocalDay(startTime as string, today, tz)) return null;
  const result = normalizeResult(row['result']);
  if (result === 'success') return 'success';
  if (result === 'failure' || result === 'failed' || result === 'error') return 'failure';
  return 'running';
};

const assignLanes = <T extends { startMs: number; endMs: number }>(
  items: T[]
): Array<T & { lane: number }> => {
  const sorted = items
    .slice()
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  const laneEnds: number[] = [];
  const out: Array<T & { lane: number }> = [];
  for (const b of sorted) {
    let lane = laneEnds.findIndex((end) => end <= b.startMs);
    if (lane === -1) {
      lane = laneEnds.length;
      laneEnds.push(b.endMs);
    } else {
      laneEnds[lane] = b.endMs;
    }
    out.push({ ...b, lane });
  }
  return out;
};

const buildStates = (
  rows: TransformationLogRow[],
  today: Date,
  tz: TzKey
): NotebookState[] => {
  const byName = new Map<string, TransformationLogRow[]>();
  for (const row of rows) {
    const group = String(row['refresh_group'] ?? '').trim().toLowerCase();
    if (group !== REFRESH_GROUP) continue;
    const name = String(row['notebook_name'] ?? '');
    if (!name) continue;
    if (!byName.has(name)) byName.set(name, []);
    byName.get(name)!.push(row);
  }

  const earliestStart = (runs: TransformationLogRow[]): number => {
    let min = Number.POSITIVE_INFINITY;
    for (const r of runs) {
      const t = Date.parse(String(r['start_time'] ?? ''));
      if (Number.isFinite(t) && t < min) min = t;
    }
    return min;
  };
  const pipelineNotebooks = Array.from(byName.entries())
    .sort((a, b) => {
      const ea = earliestStart(a[1]);
      const eb = earliestStart(b[1]);
      if (ea !== eb) return ea - eb;
      return a[0].localeCompare(b[0]);
    })
    .map(([name]) => name);

  const baseStates = pipelineNotebooks.map(
    (name, baselineIdx): NotebookState & { baselineIdx: number } => {
      const runs = (byName.get(name) ?? [])
        .slice()
        .sort((a, b) => {
          const ta = Date.parse(String(a['start_time'] ?? '')) || 0;
          const tb = Date.parse(String(b['start_time'] ?? '')) || 0;
          return tb - ta;
        });
      const todayRun = runs.find((r) =>
        sameLocalDay(r['start_time'] as string, today, tz)
      );
      if (!todayRun) {
        return { name, status: 'not_started', lastRun: runs[0], baselineIdx };
      }
      const status = classifyRow(todayRun, today, tz) ?? 'running';
      return { name, status, lastRun: todayRun, baselineIdx };
    }
  );

  const statusRank: Record<Status, number> = {
    success: 0,
    running: 1,
    failure: 2,
    not_started: 3,
  };
  const finishTime = (s: NotebookState): number => {
    const v = s.lastRun?.['last_successful_run'];
    const t = v ? Date.parse(String(v)) : NaN;
    return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
  };
  const startTime = (s: NotebookState): number => {
    const v = s.lastRun?.['start_time'];
    const t = v ? Date.parse(String(v)) : NaN;
    return Number.isFinite(t) ? t : Number.POSITIVE_INFINITY;
  };

  return baseStates
    .slice()
    .sort((a, b) => {
      const ra = statusRank[a.status];
      const rb = statusRank[b.status];
      if (ra !== rb) return ra - rb;
      if (a.status === 'success') {
        const fa = finishTime(a);
        const fb = finishTime(b);
        if (fa !== fb) return fa - fb;
      }
      if (a.status === 'running' || a.status === 'failure') {
        const sa = startTime(a);
        const sb = startTime(b);
        if (sa !== sb) return sa - sb;
      }
      return a.baselineIdx - b.baselineIdx;
    })
    .map(({ baselineIdx: _unused, ...rest }) => {
      void _unused;
      return rest;
    });
};

const formatClock = (ms: number, tz: TzKey): string => formatClockInTz(ms, tz);

interface GanttBar {
  name: string;
  status: Status;
  startMs: number;
  endMs: number;
  lane: number;
  durationMin: number;
}

const buildGantt = (
  states: NotebookState[],
  nowMs: number
): {
  bars: GanttBar[];
  minMs: number;
  maxMs: number;
  laneCount: number;
  hasRunning: boolean;
} => {
  const raw: Array<Omit<GanttBar, 'lane'>> = [];
  let hasRunning = false;
  for (const s of states) {
    if (s.status === 'not_started' || !s.lastRun) continue;
    const startMs = Date.parse(String(s.lastRun['start_time'] ?? ''));
    if (!Number.isFinite(startMs)) continue;

    let endMs: number;
    const runMinRaw = s.lastRun['run_time_minutes'];
    const runMin =
      typeof runMinRaw === 'number' ? runMinRaw : Number(runMinRaw);

    if (s.status === 'running') {
      endMs = nowMs;
      hasRunning = true;
    } else if (Number.isFinite(runMin) && runMin > 0) {
      endMs = startMs + runMin * 60_000;
    } else {
      const lsr = Date.parse(String(s.lastRun['last_successful_run'] ?? ''));
      endMs = Number.isFinite(lsr) && lsr > startMs ? lsr : startMs + 60_000;
    }

    raw.push({
      name: s.name,
      status: s.status,
      startMs,
      endMs,
      durationMin: Math.max(0, (endMs - startMs) / 60_000),
    });
  }

  if (raw.length === 0) {
    return {
      bars: [],
      minMs: nowMs,
      maxMs: nowMs,
      laneCount: 0,
      hasRunning: false,
    };
  }

  const bars = assignLanes(raw);
  const minMs = Math.min(...bars.map((b) => b.startMs));
  const lastEnd = Math.max(...bars.map((b) => b.endMs));
  const maxMs = hasRunning ? Math.max(lastEnd, nowMs) : lastEnd;
  const laneCount = Math.max(...bars.map((b) => b.lane)) + 1;
  return { bars, minMs, maxMs, laneCount, hasRunning };
};

const Tamarac2 = () => {
  const [rows, setRows] = useState<TransformationLogRow[]>([]);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async (opts: { manual?: boolean } = {}) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const body: TransformationLogResponse = await fetchTransformationLog({
        limit: FETCH_LIMIT,
        noCache: opts.manual === true,
        signal: ctrl.signal,
      });
      setRows(body.rows);
      setFetchedAt(body.fetched_at);
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
    const id = window.setInterval(() => {
      void load();
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [autoRefresh, load]);

  const today = useMemo(() => new Date(), [fetchedAt]);
  const [tz, setTz, tzOption] = useTimezone();
  const states = useMemo(() => buildStates(rows, today, tz), [rows, today, tz]);

  const [nowTick, setNowTick] = useState<number>(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNowTick(Date.now()), 15_000);
    return () => window.clearInterval(id);
  }, []);

  const gantt = useMemo(() => buildGantt(states, nowTick), [states, nowTick]);
  const pending = useMemo(
    () => states.filter((s) => s.status === 'not_started'),
    [states]
  );
  const totalSpanMs = Math.max(1, gantt.maxMs - gantt.minMs);
  const PX_PER_MIN = 40;
  const LANE_HEIGHT = 56;
  const AXIS_HEIGHT = 32;
  const spanMin = totalSpanMs / 60_000;
  const timelineWidthPx = Math.max(900, Math.ceil(spanMin * PX_PER_MIN));

  const summary = useMemo(() => {
    const counts = { not_started: 0, running: 0, success: 0, failure: 0 };
    for (const s of states) counts[s.status] += 1;
    return counts;
  }, [states]);

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
            <div className="t2-kicker">Pipeline · Today</div>
            <PipelineNav />
          </div>
          <h1 className="t2-title">Tamarac Transformations</h1>
          <p className="t2-lede">
            Live view of this morning&rsquo;s notebook runs, threaded by
            overlap. First to finish sits leftmost; not&#8209;yet&#8209;run
            notebooks appear below.
          </p>

          <div className="t2-meta-row">
            <div className="t2-legend">
              <span className="t2-legend-item">
                <span className="t2-dot t2-dot-success" /> Completed{' '}
                <strong>{summary.success}</strong>
              </span>
              <span className="t2-legend-item">
                <span className="t2-dot t2-dot-running" /> Running{' '}
                <strong>{summary.running}</strong>
              </span>
              <span className="t2-legend-item">
                <span className="t2-dot t2-dot-failure" /> Failed{' '}
                <strong>{summary.failure}</strong>
              </span>
              <span className="t2-legend-item">
                <span className="t2-dot t2-dot-pending" /> Pending{' '}
                <strong>{summary.not_started}</strong>
              </span>
            </div>
            <div className="t2-actions">
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
          {fetchedAt && (
            <div className="t2-fetched">
              Updated {formatClock(new Date(fetchedAt).getTime(), tz)} · {tzOption.short}
            </div>
          )}
        </header>

        {error && (
          <div className="t2-error-banner">
            <strong>Error:</strong> {error}
          </div>
        )}

        <section className="t2-card">
          <div className="t2-card-header">
            <h2>Timeline</h2>
            <span className="t2-card-meta">
              {spanMin > 0
                ? `${spanMin.toFixed(0)} min span · ${gantt.laneCount} parallel ${
                    gantt.laneCount === 1 ? 'thread' : 'threads'
                  }`
                : ''}
            </span>
          </div>

          <div className="t2-gantt-wrap">
            {gantt.bars.length === 0 ? (
              <div className="t2-empty">No pipeline runs yet today.</div>
            ) : (
              <div
                className="t2-gantt"
                ref={(el) => {
                  if (el) {
                    el.style.height = `${
                      gantt.laneCount * LANE_HEIGHT + AXIS_HEIGHT + 8
                    }px`;
                    el.style.width = `${timelineWidthPx}px`;
                  }
                }}
              >
                <div className="t2-axis">
                  {(() => {
                    const tickMin =
                      spanMin <= 60 ? 5 : spanMin <= 180 ? 10 : 15;
                    const ticks: number[] = [];
                    const startMin =
                      Math.ceil(gantt.minMs / 60_000 / tickMin) * tickMin;
                    for (
                      let m = startMin;
                      m * 60_000 <= gantt.maxMs;
                      m += tickMin
                    ) {
                      ticks.push(m * 60_000);
                    }
                    return ticks.map((ms) => {
                      const leftPx =
                        ((ms - gantt.minMs) / totalSpanMs) * timelineWidthPx;
                      return (
                        <div
                          key={ms}
                          className="t2-axis-tick"
                          ref={(el) => {
                            if (el) el.style.left = `${leftPx}px`;
                          }}
                        >
                          <span className="t2-axis-label">
                            {formatClock(ms, tz)}
                          </span>
                        </div>
                      );
                    });
                  })()}
                </div>

                {gantt.bars.map((b) => {
                  const leftPx =
                    ((b.startMs - gantt.minMs) / totalSpanMs) * timelineWidthPx;
                  const widthPx = Math.max(
                    28,
                    ((b.endMs - b.startMs) / totalSpanMs) * timelineWidthPx
                  );
                  const top = AXIS_HEIGHT + b.lane * LANE_HEIGHT;
                  return (
                    <div
                      key={b.name}
                      className={`t2-bar t2-bar-${b.status}`}
                      ref={(el) => {
                        if (!el) return;
                        el.style.left = `${leftPx}px`;
                        el.style.width = `${widthPx}px`;
                        el.style.top = `${top}px`;
                      }}
                      title={`${b.name}\n${formatClock(b.startMs, tz)} → ${formatClock(
                        b.endMs,
                        tz
                      )}  (${b.durationMin.toFixed(1)} min)`}
                    >
                      <span className="t2-bar-label">{b.name}</span>
                      <span className="t2-bar-meta">
                        {formatClock(b.startMs, tz)}–{formatClock(b.endMs, tz)} ·{' '}
                        {b.durationMin.toFixed(1)}m
                      </span>
                    </div>
                  );
                })}

                {gantt.hasRunning &&
                  nowTick >= gantt.minMs &&
                  nowTick <= gantt.maxMs && (
                    <div
                      className="t2-now"
                      ref={(el) => {
                        if (el)
                          el.style.left = `${
                            ((nowTick - gantt.minMs) / totalSpanMs) *
                            timelineWidthPx
                          }px`;
                      }}
                    >
                      <span className="t2-now-label">now</span>
                    </div>
                  )}
              </div>
            )}
          </div>
        </section>

        {pending.length > 0 && (
          <section className="t2-card t2-card-secondary">
            <div className="t2-card-header">
              <h2>Pending</h2>
              <span className="t2-card-meta">
                {pending.length} not started today
              </span>
            </div>
            <div className="t2-pending-list">
              {pending.map((s) => (
                <span key={s.name} className="t2-chip">
                  {s.name}
                </span>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default Tamarac2;
