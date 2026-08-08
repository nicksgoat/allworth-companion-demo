// src/Tamarac.tsx
// Visual pipeline view of the Tamarac notebooks — Gantt-style timeline,
// colored by today's run status:
//   gray   = no run recorded today (not started)
//   yellow = currently running
//   green  = completed successfully today
//   red    = failed today

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  fetchTransformationLog,
  type TransformationLogResponse,
  type TransformationLogRow,
} from './services/refreshLog';
import PipelineNav from './components/PipelineNav';
import TimezonePicker from './components/TimezonePicker';
import {
  formatClockInTz,
  sameDayInTz,
  useTimezone,
  type TzKey,
} from './services/timezone';
import './Tamarac.css';

// Notebooks are selected dynamically from the transformation_log by
// refresh_group = 'tamarac'. Baseline order (used when nothing has run yet
// today) is derived from each notebook's earliest observed start_time in the
// fetched window, so upstream notebooks tend to sit on the left.
const REFRESH_GROUP = 'tamarac';

const AUTO_REFRESH_MS = 30_000;
const FETCH_LIMIT = 1000;

type Status = 'not_started' | 'running' | 'success' | 'failure';

interface NotebookState {
  name: string;
  status: Status;
  lastRun?: TransformationLogRow;
}

const sameLocalDay = (iso: string | null | undefined, ref: Date, tz: TzKey): boolean =>
  sameDayInTz(iso, ref, tz);

const normalizeResult = (v: unknown): string => {
  if (v == null) return '';
  return String(v).trim().toLowerCase();
};

const classifyRow = (row: TransformationLogRow, today: Date, tz: TzKey): Status | null => {
  const startTime = row['start_time'];
  if (!sameLocalDay(startTime as string, today, tz)) return null;
  const result = normalizeResult(row['result']);
  if (result === 'success') return 'success';
  if (result === 'failure' || result === 'failed' || result === 'error') return 'failure';
  // No terminal result yet → treat as currently running
  return 'running';
};

const buildStates = (
  rows: TransformationLogRow[],
  today: Date,
  tz: TzKey
): NotebookState[] => {
  // Group rows by notebook_name → pick the most recent row TODAY for status.
  // Only consider rows whose refresh_group matches the configured group.
  const byName = new Map<string, TransformationLogRow[]>();
  for (const row of rows) {
    const group = String(row['refresh_group'] ?? '').trim().toLowerCase();
    if (group !== REFRESH_GROUP) continue;
    const name = String(row['notebook_name'] ?? '');
    if (!name) continue;
    if (!byName.has(name)) byName.set(name, []);
    byName.get(name)!.push(row);
  }

  // Derive baseline order from earliest observed start_time per notebook.
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

  const baseStates = pipelineNotebooks.map((name, baselineIdx): NotebookState & { baselineIdx: number } => {
    const runs = (byName.get(name) ?? [])
      .slice()
      .sort((a, b) => {
        const ta = Date.parse(String(a['start_time'] ?? '')) || 0;
        const tb = Date.parse(String(b['start_time'] ?? '')) || 0;
        return tb - ta;
      });
    const todayRun = runs.find((r) => sameLocalDay(r['start_time'] as string, today, tz));
    if (!todayRun) {
      return { name, status: 'not_started', lastRun: runs[0], baselineIdx };
    }
    const status = classifyRow(todayRun, today, tz) ?? 'running';
    return { name, status, lastRun: todayRun, baselineIdx };
  });

  // Re-order: completed (by last_successful_run asc) → running (by start_time asc)
  // → failure (by start_time asc) → not_started (by baseline order).
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

// Greedy lane assignment: each bar goes into the first lane whose previous
// bar ended at or before this bar's start. Mirrors a Gantt "threaded" layout.
const assignLanes = (
  bars: Array<Omit<GanttBar, 'lane'>>
): GanttBar[] => {
  const sorted = bars
    .slice()
    .sort((a, b) => a.startMs - b.startMs || a.endMs - b.endMs);
  const laneEnds: number[] = [];
  const out: GanttBar[] = [];
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
    const runMin = typeof runMinRaw === 'number' ? runMinRaw : Number(runMinRaw);

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
    return { bars: [], minMs: nowMs, maxMs: nowMs, laneCount: 0, hasRunning: false };
  }

  const bars = assignLanes(raw);
  const minMs = Math.min(...bars.map((b) => b.startMs));
  // Only let the "now" edge extend the timeline while something is still running.
  // Once everything finishes today, freeze maxMs at the last bar's end so the
  // timeline stops growing and the bars stay readable.
  const lastEnd = Math.max(...bars.map((b) => b.endMs));
  const maxMs = hasRunning ? Math.max(lastEnd, nowMs) : lastEnd;
  const laneCount = Math.max(...bars.map((b) => b.lane)) + 1;
  return { bars, minMs, maxMs, laneCount, hasRunning };
};

const Tamarac = () => {
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
    const id = window.setInterval(() => { void load(); }, AUTO_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [autoRefresh, load]);

  const today = useMemo(() => new Date(), [fetchedAt]); // refresh 'today' on each fetch
  const [tz, setTz, tzOption] = useTimezone();
  const states = useMemo(() => buildStates(rows, today, tz), [rows, today, tz]);

  // Tick every 15s so running bars extend to "now" live.
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
  // Pixels-per-minute scale so bars stay readable when the day only spans
  // an hour or two in the morning. Wider timeline than the viewport will
  // scroll horizontally inside .tamarac-gantt-wrap.
  const PX_PER_MIN = 40;
  const LANE_HEIGHT = 52;
  const AXIS_HEIGHT = 28;
  const spanMin = totalSpanMs / 60_000;
  const timelineWidthPx = Math.max(900, Math.ceil(spanMin * PX_PER_MIN));

  const summary = useMemo(() => {
    const counts = { not_started: 0, running: 0, success: 0, failure: 0 };
    for (const s of states) counts[s.status] += 1;
    return counts;
  }, [states]);

  return (
    <div className="tamarac-page">
      <PipelineNav />

      <header className="tamarac-header">
        <div>
          <h1 className="tamarac-title">Tamarac Pipeline — Today</h1>
          <p className="tamarac-subtitle">
            {today.toLocaleDateString(undefined, {
              weekday: 'long',
              year: 'numeric',
              month: 'long',
              day: 'numeric',
              timeZone: tzOption.iana,
            })}{' '}
            · {tzOption.short}
          </p>
        </div>
        <div className="tamarac-controls">
          <label className="tamarac-checkbox">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (30s)
          </label>
          <TimezonePicker value={tz} onChange={setTz} />
          <button
            className="tamarac-button"
            onClick={() => { void load({ manual: true }); }}
            disabled={loading}
          >
            {loading ? 'Refreshing…' : 'Refresh now'}
          </button>
        </div>
      </header>

      <div className="tamarac-legend">
        <span className="tamarac-legend-item"><span className="tamarac-dot status-success" /> Completed ({summary.success})</span>
        <span className="tamarac-legend-item"><span className="tamarac-dot status-running" /> Running ({summary.running})</span>
        <span className="tamarac-legend-item"><span className="tamarac-dot status-failure" /> Failed ({summary.failure})</span>
        <span className="tamarac-legend-item"><span className="tamarac-dot status-not_started" /> Not started ({summary.not_started})</span>
        {fetchedAt && (
          <span className="tamarac-legend-fetched">Updated {formatClock(new Date(fetchedAt).getTime(), tz)}</span>
        )}
      </div>

      {error && (
        <div className="tamarac-error">
          <strong>Error:</strong> {error}
        </div>
      )}

      <div className="tamarac-gantt-wrap">
        {gantt.bars.length === 0 ? (
          <div className="tamarac-empty">No pipeline runs yet today.</div>
        ) : (
          <div
            className="tamarac-gantt"
            ref={(el) => {
              if (el) {
                el.style.height = `${gantt.laneCount * LANE_HEIGHT + AXIS_HEIGHT}px`;
                el.style.width = `${timelineWidthPx}px`;
              }
            }}
          >
            {/* time axis — tick every N minutes, scaled to actual duration */}
            <div className="tamarac-axis">
              {(() => {
                const tickMin = spanMin <= 60 ? 5 : spanMin <= 180 ? 10 : 15;
                const ticks: number[] = [];
                // align first tick to a clean minute boundary >= minMs
                const startMin = Math.ceil(gantt.minMs / 60_000 / tickMin) * tickMin;
                for (
                  let m = startMin;
                  m * 60_000 <= gantt.maxMs;
                  m += tickMin
                ) {
                  ticks.push(m * 60_000);
                }
                return ticks.map((ms) => {
                  const leftPx = ((ms - gantt.minMs) / totalSpanMs) * timelineWidthPx;
                  return (
                    <div
                      key={ms}
                      className="tamarac-axis-tick"
                      ref={(el) => {
                        if (el) el.style.left = `${leftPx}px`;
                      }}
                    >
                      <span className="tamarac-axis-label">{formatClock(ms, tz)}</span>
                    </div>
                  );
                });
              })()}
            </div>

            {/* bars */}
            {gantt.bars.map((b) => {
              const leftPx = ((b.startMs - gantt.minMs) / totalSpanMs) * timelineWidthPx;
              const widthPx = Math.max(
                24,
                ((b.endMs - b.startMs) / totalSpanMs) * timelineWidthPx
              );
              const top = AXIS_HEIGHT + b.lane * LANE_HEIGHT;
              return (
                <div
                  key={b.name}
                  className={`tamarac-bar status-${b.status}`}
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
                  <span className="tamarac-bar-label">{b.name}</span>
                  <span className="tamarac-bar-meta">
                    {formatClock(b.startMs, tz)}–{formatClock(b.endMs, tz)} ·{' '}
                    {b.durationMin.toFixed(1)}m
                  </span>
                </div>
              );
            })}

            {/* live "now" marker — only show while something is still running today */}
            {gantt.hasRunning &&
              nowTick >= gantt.minMs &&
              nowTick <= gantt.maxMs && (
                <div
                  className="tamarac-now"
                  ref={(el) => {
                    if (el)
                      el.style.left = `${
                        ((nowTick - gantt.minMs) / totalSpanMs) * timelineWidthPx
                      }px`;
                  }}
                >
                  <span className="tamarac-now-label">now</span>
                </div>
              )}
          </div>
        )}

        {pending.length > 0 && (
          <div className="tamarac-pending">
            <div className="tamarac-pending-title">
              Not started today ({pending.length})
            </div>
            <div className="tamarac-pending-list">
              {pending.map((s) => (
                <span key={s.name} className="tamarac-chip status-not_started">
                  {s.name}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default Tamarac;
