// src/PipelineReview.tsx
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { ChartContainer, ChartTooltip } from './components/ui/chart';
import { resolveUserEmail } from './services/auth';
import { ToolChart, ToolEmptyState, ToolMetric, ToolMetricGrid, ToolPage } from './components/ToolPage';
import { chartTheme } from './theme';
import './PipelineReview.css';
import { useWorkspace } from './components/WorkspaceContext';

// ─── Types ───────────────────────────────────────────────────────────────────

interface Prospect {
  id: string;
  snapshot_week: string;
  report_date: string | null;
  lead_id: string;
  name: string;
  paum: number;
  stage: string;
  days_in_stage: number;
  avg_dwell: number;
  score: number;
  reasons: string;
  channel: string;
  advisor_name: string;
  sales_person: string;
  region: string;
  expected_close_date: string | null;
  last_activity_date: string | null;
  next_activity_date: string | null;
  was_stale: boolean;
  sf_url: string;
}

interface Summary {
  snapshot_week: string;
  report_date: string | null;
  total_prospects: number;
  total_paum: number;
  weighted_pipeline: number;
  verbal_onboarding_paum: number;
  verbal_onboarding_count: number;
  closing_next_30_count: number;
  closing_next_30_paum: number;
  conversions_count: number;
  conversions_paum: number;
}

interface SnapshotResponse {
  week: string | null;
  prospects: Prospect[];
  summary: Summary | null;
}

type TrendPoint = Summary;

interface WeekOption {
  snapshot_week: string;
  report_date: string | null;
}

interface ClosedLead {
  lead_id: string;
  name: string;
  paum: number;
  channel: string;
  stage_prev: string;
  advisor_name: string;
  sales_person: string;
  region: string;
  close_date: string | null;
  days_closed: number;
  sf_url: string;
}

interface MoveLead {
  lead_id: string;
  name: string;
  stage: string;
  score: number;
  paum: number;
  prior_stage?: string;
}

interface Movement {
  week: string | null;
  prior_week: string | null;
  new: MoveLead[];
  advanced: MoveLead[];
  dropped: MoveLead[];
}

type ProgressStatus = 'won' | 'advanced' | 're-engaged' | 'stable' | 'dropped';

interface ProgressRow {
  lead_id: string;
  name: string;
  paum: number;
  channel: string;
  advisor_name: string;
  sales_person: string;
  region: string;
  stage_prev: string;
  score_prev: number | null;
  stage_now: string | null;
  score_now: number | null;
  status: ProgressStatus;
  note: string;
  sf_url: string;
}

interface ProgressAgg { count: number; paum: number }

interface ProgressData {
  week: string | null;
  rows: ProgressRow[];
  totals: {
    prior_prospects: number;
    won: ProgressAgg;
    advanced: ProgressAgg;
    re_engaged: ProgressAgg;
    stable: ProgressAgg;
    dropped: ProgressAgg;
  };
}

interface FilterOptions {
  regions: string[];
  channels: string[];
  stages: string[];
  advisors: string[];
}

type SortKey = 'score' | 'paum' | 'days_in_stage' | 'name' | 'advisor_name';

// ─── Channel styling (matches the emailed report) ────────────────────────────

const CHANNEL_ORDER = ['Advisor Driven', 'CRP', 'Media Driven', 'Paid Leads'];
const CHANNEL_COLORS: Record<string, string> = {
  'Advisor Driven': '#173D67',
  CRP: '#3E71B7',
  'Media Driven': '#289FDA',
  'Paid Leads': '#A99C6C',
};
const channelColor = (c: string): string => CHANNEL_COLORS[c] ?? '#1F3864';

// Stage close probabilities + verbal/onboarding set (mirror the build notebook) — used to
// recompute the header KPIs from the filtered prospect set when filters are active.
const STAGE_CLOSE_PROB: Record<string, number> = {
  '5 - Discovery': 0.30,
  '6 - Proposal Delivered': 0.48,
  '7 - Verbal Commitment Received': 0.95,
  '8 - Onboarding': 0.98,
};
const VERBAL_ONBOARDING = new Set(['7 - Verbal Commitment Received', '8 - Onboarding']);

// Week-over-week progress status → label + badge class (mirrors the emailed report).
const PROGRESS_BADGE: Record<ProgressStatus, { label: string; cls: string }> = {
  won: { label: 'Won', cls: 'won' },
  advanced: { label: 'Advanced', cls: 'advanced' },
  're-engaged': { label: 'Re-engaged', cls: 'reengaged' },
  stable: { label: 'Stable', cls: 'stable' },
  dropped: { label: 'Dropped', cls: 'dropped' },
};

// Scoring key (mirrors score_prospect in the Synapse notebook). Data-driven so the
// panel renders as consistent point pills instead of ad-hoc list markup.
const SCORING_KEY: { title: string; items: { label: string; pts: number }[] }[] = [
  {
    title: 'Velocity & Timing',
    items: [
      { label: 'Same-day advisor call', pts: 25 },
      { label: 'Dual-touch week (call + event)', pts: 15 },
      { label: 'Fast mover (<7d old, past Discovery)', pts: 15 },
      { label: 'Activity in last 7 days', pts: 10 },
      { label: 'No activity >30d', pts: -5 },
    ],
  },
  {
    title: 'Prospect Size',
    items: [
      { label: 'Marquee (≥$10M)', pts: 40 },
      { label: 'High-value (≥$5M)', pts: 30 },
      { label: 'Qualified (≥$2M)', pts: 20 },
      { label: 'Money-in-motion source', pts: 10 },
    ],
  },
  {
    title: 'Stage & Movement',
    items: [
      { label: 'Onboarding / Verbal', pts: 35 },
      { label: 'Proposal Delivered', pts: 20 },
      { label: 'Verbal overdue — paperwork push', pts: 20 },
      { label: 'Close expected ≤21d', pts: 10 },
      { label: 'Dwell risk (>1.5× avg)', pts: -10 },
    ],
  },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

const fmtMoney = (v: number): string => {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1e6).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

const fmtDate = (s: string | null): string => {
  if (!s) return '—';
  const d = new Date(`${s}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
};

// Week-of report date for the selector, e.g. "Jul 13, 2026" (falls back to the ISO week).
const fmtWeekLabel = (w: WeekOption): string => {
  if (!w.report_date) return w.snapshot_week;
  const d = new Date(`${w.report_date}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? w.snapshot_week
    : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
};

const daysBetween = (from: Date, s: string | null): number | null => {
  if (!s) return null;
  const d = new Date(`${s}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  return Math.round((from.getTime() - d.getTime()) / 86_400_000);
};

interface Status { label: string; cls: string; }

const dwellStatus = (days: number, avg: number): Status => {
  if (avg > 0 && days > avg * 1.5) return { label: 'Overdue', cls: 'overdue' };
  if (avg > 0 && days > avg) return { label: 'At Risk', cls: 'at-risk' };
  return { label: 'On Track', cls: 'on-track' };
};

// Parse a fetch Response as JSON, but turn empty/non-JSON bodies (backend down,
// proxy 502, HTML error page) into a readable error instead of the browser's
// cryptic "Unexpected end of JSON input".
async function fetchJson<T = { success: boolean; data?: unknown; error?: string }>(url: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new Error('Cannot reach the server. Is the backend running?');
  }
  const text = await res.text();
  if (!text) {
    throw new Error(
      res.ok
        ? 'Server returned an empty response.'
        : `Server error (HTTP ${res.status}). The backend may be starting or unreachable.`,
    );
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`Unexpected non-JSON response (HTTP ${res.status}).`);
  }
}

const workedStorageKey = (email: string | null, week: string): string =>
  `pipeline-review:worked:${email ?? 'anon'}:${week}`;

const loadWorked = (email: string | null, week: string): Set<string> => {
  try {
    const raw = localStorage.getItem(workedStorageKey(email, week));
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch {
    return new Set();
  }
};

const saveWorked = (email: string | null, week: string, worked: Set<string>): void => {
  try {
    localStorage.setItem(workedStorageKey(email, week), JSON.stringify([...worked]));
  } catch {
    /* ignore quota / privacy-mode errors */
  }
};

// ─── Component ───────────────────────────────────────────────────────────────

export default function PipelineReview() {
  const { household } = useWorkspace();
  const [weeks, setWeeks] = useState<WeekOption[]>([]);
  const [activeWeek, setActiveWeek] = useState<string>('');
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [trend, setTrend] = useState<TrendPoint[]>([]);
  const [movement, setMovement] = useState<Movement | null>(null);
  const [closed, setClosed] = useState<ClosedLead[]>([]);
  const [progress, setProgress] = useState<ProgressData | null>(null);
  const [filters, setFilters] = useState<FilterOptions>({ regions: [], channels: [], stages: [], advisors: [] });
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // filter state
  const [selectedRegions, setSelectedRegions] = useState<Set<string>>(new Set());
  const [selectedChannels, setSelectedChannels] = useState<Set<string>>(new Set());
  const [selectedStages, setSelectedStages] = useState<Set<string>>(new Set());
  const [atRiskOnly, setAtRiskOnly] = useState<boolean>(false);
  const [minScore, setMinScore] = useState<number>(0);
  const [minPaum, setMinPaum] = useState<number>(0);
  const [search, setSearch] = useState<string>('');

  useEffect(() => { if (household?.name) setSearch(household.name); }, [household?.name]);
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // per-user "worked" check-off state (localStorage)
  const [email, setEmail] = useState<string | null>(null);
  const [worked, setWorked] = useState<Set<string>>(new Set());
  const [showWorked, setShowWorked] = useState<boolean>(true);

  // resolve user email once (keys the check-off storage)
  useEffect(() => {
    void resolveUserEmail().then(setEmail).catch(() => setEmail(null));
  }, []);

  // initial load: weeks + filters + trend
  useEffect(() => {
    void (async () => {
      try {
        const [weeksRes, filtersRes, trendRes] = await Promise.all([
          fetchJson<{ success: boolean; data: WeekOption[] }>('/pipeline-review/api/weeks'),
          fetchJson<{ success: boolean; data: FilterOptions }>('/pipeline-review/api/filters'),
          fetchJson<{ success: boolean; data: TrendPoint[] }>('/pipeline-review/api/trend'),
        ]);
        if (weeksRes.success) {
          setWeeks(weeksRes.data);
          setActiveWeek(weeksRes.data[0]?.snapshot_week ?? '');
        }
        if (filtersRes.success) setFilters(filtersRes.data);
        if (trendRes.success) setTrend(trendRes.data);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load');
      }
    })();
  }, []);

  // load the snapshot whenever the active week changes
  useEffect(() => {
    if (!activeWeek) { setLoading(false); return; }
    setLoading(true);
    void (async () => {
      try {
        const [snapRes, moveRes, closedRes, progRes] = await Promise.all([
          fetchJson<{ success: boolean; data: SnapshotResponse; error?: string }>(`/pipeline-review/api/snapshot?week=${encodeURIComponent(activeWeek)}`),
          fetchJson<{ success: boolean; data: Movement }>(`/pipeline-review/api/movement?week=${encodeURIComponent(activeWeek)}`),
          fetchJson<{ success: boolean; data: { week: string | null; closed: ClosedLead[] } }>(`/pipeline-review/api/closed?week=${encodeURIComponent(activeWeek)}`),
          fetchJson<{ success: boolean; data: ProgressData }>(`/pipeline-review/api/progress?week=${encodeURIComponent(activeWeek)}`),
        ]);
        if (!snapRes.success) throw new Error(snapRes.error || 'Failed to load snapshot');
        const data = snapRes.data;
        setProspects(data.prospects);
        setSummary(data.summary);
        setMovement(moveRes.success ? moveRes.data : null);
        setClosed(closedRes.success ? closedRes.data.closed : []);
        setProgress(progRes.success ? progRes.data : null);
        setError(null);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load snapshot');
      } finally {
        setLoading(false);
      }
    })();
  }, [activeWeek]);

  // reload worked-set when the week or user changes
  useEffect(() => {
    if (activeWeek) setWorked(loadWorked(email, activeWeek));
  }, [email, activeWeek]);

  const toggleWorked = useCallback((leadId: string) => {
    setWorked((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) next.delete(leadId); else next.add(leadId);
      saveWorked(email, activeWeek, next);
      return next;
    });
  }, [email, activeWeek]);

  const toggleSetValue = (setter: React.Dispatch<React.SetStateAction<Set<string>>>, value: string) => {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(value)) next.delete(value); else next.add(value);
      return next;
    });
  };

  const paumCeiling = useMemo(
    () => Math.max(10_000_000, ...prospects.map((p) => p.paum)),
    [prospects],
  );

  // apply filters + sort
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    const rows = prospects.filter((p) => {
      if (selectedRegions.size && !selectedRegions.has(p.region)) return false;
      if (selectedChannels.size && !selectedChannels.has(p.channel)) return false;
      if (selectedStages.size && !selectedStages.has(p.stage)) return false;
      if (atRiskOnly && !p.was_stale) return false;
      if (p.score < minScore) return false;
      if (p.paum < minPaum) return false;
      if (!showWorked && worked.has(p.lead_id)) return false;
      if (q) {
        const hay = `${p.name} ${p.advisor_name} ${p.sales_person}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    const dir = sortDir === 'asc' ? 1 : -1;
    rows.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
    // worked rows sink to the bottom while still visible
    rows.sort((a, b) => Number(worked.has(a.lead_id)) - Number(worked.has(b.lead_id)));
    return rows;
  }, [prospects, selectedRegions, selectedChannels, selectedStages, atRiskOnly,
      minScore, minPaum, search, sortKey, sortDir, showWorked, worked]);

  const filteredTotals = useMemo(() => ({
    count: visible.length,
    paum: visible.reduce((s, p) => s + p.paum, 0),
    workedCount: visible.filter((p) => worked.has(p.lead_id)).length,
  }), [visible, worked]);

  // Any active filter → the whole UI (KPIs, WoW, closed, at-risk) reflects the selection.
  const anyFilterActive = useMemo(
    () => search.trim() !== '' || selectedRegions.size > 0 || selectedChannels.size > 0
      || selectedStages.size > 0 || atRiskOnly || minScore > 0 || minPaum > 0,
    [search, selectedRegions, selectedChannels, selectedStages, atRiskOnly, minScore, minPaum],
  );

  // Shared region/channel/stage/PAUM/search predicate for the closed + progress tables.
  // (score / at-risk / worked are prospect-only and don't apply to those record types.)
  const matchesShared = useCallback(
    (r: { region: string; channel: string; paum: number; name: string; advisor_name: string; sales_person: string; stage?: string }) => {
      if (selectedRegions.size && !selectedRegions.has(r.region)) return false;
      if (selectedChannels.size && !selectedChannels.has(r.channel)) return false;
      if (selectedStages.size && r.stage !== undefined && !selectedStages.has(r.stage)) return false;
      if (r.paum < minPaum) return false;
      const q = search.trim().toLowerCase();
      if (q && !`${r.name} ${r.advisor_name} ${r.sales_person}`.toLowerCase().includes(q)) return false;
      return true;
    },
    [selectedRegions, selectedChannels, selectedStages, minPaum, search],
  );

  // Header KPIs: authoritative week summary when unfiltered; recomputed from the filtered
  // focus list when any filter is active (so the whole page stays coherent).
  const kpi = useMemo(() => {
    if (!anyFilterActive) {
      return {
        weighted: summary?.weighted_pipeline ?? 0,
        voPaum: summary?.verbal_onboarding_paum ?? 0,
        voCount: summary?.verbal_onboarding_count ?? 0,
        close30Count: summary?.closing_next_30_count ?? 0,
        close30Paum: summary?.closing_next_30_paum ?? 0,
        totalCount: summary?.total_prospects ?? 0,
        totalPaum: summary?.total_paum ?? 0,
      };
    }
    const today = new Date();
    let weighted = 0, voPaum = 0, voCount = 0, c30 = 0, c30p = 0, totalPaum = 0;
    for (const p of visible) {
      totalPaum += p.paum;
      weighted += p.paum * (STAGE_CLOSE_PROB[p.stage] ?? 0);
      if (VERBAL_ONBOARDING.has(p.stage)) { voPaum += p.paum; voCount += 1; }
      const d = daysBetween(today, p.expected_close_date);
      if (d !== null && d >= -30 && d <= 14) { c30 += 1; c30p += p.paum; }
    }
    return {
      weighted, voPaum, voCount, close30Count: c30, close30Paum: c30p,
      totalCount: visible.length, totalPaum,
    };
  }, [anyFilterActive, summary, visible]);

  const setSort = (key: SortKey) => {
    if (key === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir(key === 'name' || key === 'advisor_name' ? 'asc' : 'desc'); }
  };

  const clearFilters = () => {
    setSelectedRegions(new Set());
    setSelectedChannels(new Set());
    setSelectedStages(new Set());
    setAtRiskOnly(false);
    setMinScore(0);
    setMinPaum(0);
    setSearch('');
  };

  const exportExcel = async () => {
    try {
      const body = {
        week: activeWeek,
        prospects: visible.map((p) => ({ ...p, worked: worked.has(p.lead_id) })),
      };
      const res = await fetch('/pipeline-review/api/export-excel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pipeline_review_${activeWeek || 'latest'}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Export failed');
    }
  };

  const trendData = useMemo(
    () => trend.map((t) => ({
      ...t,
      paumM: t.total_paum / 1e6,
      weightedM: t.weighted_pipeline / 1e6,
    })),
    [trend],
  );

  // prior-week summary (for the WoW deltas on the header KPIs)
  const priorSummary = useMemo(() => {
    const idx = trend.findIndex((t) => t.snapshot_week === activeWeek);
    return idx > 0 ? trend[idx - 1] : null;
  }, [trend, activeWeek]);

  // week-over-week direction lookups
  const newSet = useMemo(
    () => new Set((movement?.new ?? []).map((m) => m.lead_id)),
    [movement],
  );
  const advancedSet = useMemo(
    () => new Set((movement?.advanced ?? []).map((m) => m.lead_id)),
    [movement],
  );

  // focus list grouped by channel (report layout), preserving the filtered+sorted order
  const grouped = useMemo(() => {
    const map = new Map<string, Prospect[]>();
    for (const p of visible) {
      const arr = map.get(p.channel);
      if (arr) arr.push(p);
      else map.set(p.channel, [p]);
    }
    const ordered = CHANNEL_ORDER.filter((c) => map.has(c));
    const extras = [...map.keys()].filter((c) => !CHANNEL_ORDER.includes(c));
    return [...ordered, ...extras].map((c) => [c, map.get(c) as Prospect[]] as const);
  }, [visible]);

  // closed leads (filtered) grouped by channel
  const closedView = useMemo(
    () => closed.filter((c) => matchesShared({ ...c, stage: c.stage_prev })),
    [closed, matchesShared],
  );
  const closedGrouped = useMemo(() => {
    const map = new Map<string, ClosedLead[]>();
    for (const c of closedView) {
      const arr = map.get(c.channel);
      if (arr) arr.push(c);
      else map.set(c.channel, [c]);
    }
    const ordered = CHANNEL_ORDER.filter((c) => map.has(c));
    const extras = [...map.keys()].filter((c) => !CHANNEL_ORDER.includes(c));
    return [...ordered, ...extras].map((c) => [c, map.get(c) as ClosedLead[]] as const);
  }, [closedView]);

  const closedPaum = useMemo(() => closedView.reduce((s, c) => s + c.paum, 0), [closedView]);

  // week-over-week progress: apply the shared filter, then split into shown vs. an
  // "omitted" footer (stable + low-value dropped), mirroring the emailed report. Tiles are
  // recomputed from the filtered rows so the counts match what's displayed.
  const progressFiltered = useMemo(
    () => (progress ? progress.rows.filter((r) => matchesShared({ ...r, stage: r.stage_prev })) : []),
    [progress, matchesShared],
  );
  const progressAgg = useMemo(() => {
    const mk = () => ({ count: 0, paum: 0 });
    const agg = {
      prior_prospects: progressFiltered.length,
      won: mk(), advanced: mk(), re_engaged: mk(), stable: mk(), dropped: mk(),
    };
    for (const r of progressFiltered) {
      const key = r.status === 're-engaged' ? 're_engaged' : r.status;
      const bucket = agg[key as 'won' | 'advanced' | 're_engaged' | 'stable' | 'dropped'];
      bucket.count += 1;
      bucket.paum += r.paum;
    }
    return agg;
  }, [progressFiltered]);
  const progressView = useMemo(() => {
    if (!progress) return null;
    const shown: ProgressRow[] = [];
    let omittedStable = 0;
    let omittedDropped = 0;
    for (const r of progressFiltered) {
      if (r.status === 'stable') { omittedStable += 1; continue; }
      if (r.status === 'dropped' && r.paum < 2_000_000) { omittedDropped += 1; continue; }
      shown.push(r);
    }
    return { shown, omittedStable, omittedDropped };
  }, [progress, progressFiltered]);

  // at-risk flags (report footer): overdue verbals, high-score w/ no next activity, dropped.
  // Derived from the filtered focus list so the section respects the active filters.
  const riskFlags = useMemo(() => {
    const today = new Date();
    const staleVerbals = visible
      .filter((p) => p.stage.toLowerCase().includes('verbal'))
      .map((p) => ({ p, overdue: daysBetween(today, p.expected_close_date) }))
      .filter((x) => x.overdue !== null && x.overdue > 30)
      .sort((a, b) => (b.overdue ?? 0) - (a.overdue ?? 0));
    const noNextActivity = visible
      .filter((p) => p.score >= 40 && !p.next_activity_date)
      .sort((a, b) => b.score - a.score);
    const dropped = movement?.dropped ?? [];
    return { staleVerbals, noNextActivity, dropped };
  }, [visible, movement]);

  return (
    <ToolPage
      eyebrow="Growth operations"
      title="Weekly Pipeline Review"
      description={`High-value prospect focus list · ${summary?.report_date ?? activeWeek}`}
      width="full"
      className="pr-root"
      actions={<>
          <label className="pr-week-select">
            Week
            <select value={activeWeek} onChange={(e) => setActiveWeek(e.target.value)}>
              {weeks.map((w) => (
                <option key={w.snapshot_week} value={w.snapshot_week}>{fmtWeekLabel(w)}</option>
              ))}
            </select>
          </label>
          <button className="pr-btn" onClick={exportExcel} disabled={!visible.length}>
            Export XLSX
          </button>
      </>}
    >

      {error && <div className="pr-error">{error}</div>}

      <div className="pr-layout">
        {/* Global filter rail — sticky, drives every section in the content column */}
        <aside className="pr-filters">
          <div className="pr-filter-head">
            <h3>Filters</h3>
            <button className="pr-link" onClick={clearFilters}>Reset</button>
          </div>

          <input
            className="pr-search"
            type="search"
            placeholder="Search name / advisor…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <label className="pr-check pr-check-strong">
            <input type="checkbox" checked={atRiskOnly} onChange={(e) => setAtRiskOnly(e.target.checked)} />
            At-risk only
          </label>
          <label className="pr-check pr-check-strong">
            <input type="checkbox" checked={showWorked} onChange={(e) => setShowWorked(e.target.checked)} />
            Show worked
          </label>

          <div className="pr-slider">
            <span>Min score: {minScore}</span>
            <input type="range" min={0} max={160} step={5} value={minScore}
              onChange={(e) => setMinScore(Number(e.target.value))} />
          </div>
          <div className="pr-slider">
            <span>Min PAUM: {fmtMoney(minPaum)}</span>
            <input type="range" min={0} max={paumCeiling} step={250_000} value={minPaum}
              onChange={(e) => setMinPaum(Number(e.target.value))} />
          </div>

          <FilterGroup title="Region" options={filters.regions} selected={selectedRegions}
            onToggle={(v) => toggleSetValue(setSelectedRegions, v)} />
          <FilterGroup title="Channel" options={filters.channels} selected={selectedChannels}
            onToggle={(v) => toggleSetValue(setSelectedChannels, v)} />
          <FilterGroup title="Stage" options={filters.stages} selected={selectedStages}
            onToggle={(v) => toggleSetValue(setSelectedStages, v)} />
        </aside>

        <div className="pr-content">

      {/* KPI cards — weighted pipeline, verbal/onboarding, closing next 30 */}
      <ToolMetricGrid className="pr-kpis">
        <ToolMetric
          label="Weighted pipeline"
          value={fmtMoney(kpi.weighted)}
          detail={<span className="pr-metric-detail">Probability-adjusted PAUM<Delta cur={kpi.weighted} prior={priorSummary?.weighted_pipeline} fmt={fmtMoney} /></span>}
        />
        <ToolMetric
          label="Verbal + onboarding"
          value={fmtMoney(kpi.voPaum)}
          detail={<span className="pr-metric-detail">{kpi.voCount} prospects near close<Delta cur={kpi.voPaum} prior={priorSummary?.verbal_onboarding_paum} fmt={fmtMoney} /></span>}
        />
        <ToolMetric
          label="Closing in next 30"
          value={kpi.close30Count}
          detail={<span className="pr-metric-detail">{fmtMoney(kpi.close30Paum)} expected<Delta cur={kpi.close30Count} prior={priorSummary?.closing_next_30_count} fmt={(n) => String(n)} /></span>}
        />
        <ToolMetric label="Total prospects" value={kpi.totalCount} detail={`${fmtMoney(kpi.totalPaum)} PAUM`} />
        <ToolMetric label="Closed this week" value={closedView.length} detail={`${fmtMoney(closedPaum)} won`} tone="positive" />
        <ToolMetric label="Worked (you)" value={`${filteredTotals.workedCount}/${filteredTotals.count}`} detail="Checked off this week" />
      </ToolMetricGrid>

      {/* Trend bar charts */}
      <section className="pr-charts">
        <ToolChart title="Pipeline size" description="PAUM, $M">
          {trendData.length ? (
            <ChartContainer width="100%" height={230}>
              <BarChart data={trendData} margin={{ top: 8, right: 16, bottom: 0, left: -4 }} barCategoryGap="30%">
                <CartesianGrid stroke={chartTheme.grid} vertical={false} />
                <XAxis dataKey="snapshot_week" tick={{ fontSize: 11, fill: chartTheme.axis }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: chartTheme.axis }} axisLine={false} tickLine={false} width={44} />
                <ChartTooltip cursor={{ fill: 'rgba(23,61,103,0.04)' }} contentStyle={chartTheme.tooltip} formatter={(v) => [`$${Number(v).toFixed(1)}M`, 'PAUM']} />
                <Bar dataKey="paumM" name="PAUM ($M)" fill={chartTheme.actual} radius={[3, 3, 0, 0]} maxBarSize={64} />
              </BarChart>
            </ChartContainer>
          ) : (
            <ToolEmptyState title="No history yet" detail="Trends appear after the first snapshot loads." />
          )}
        </ToolChart>
        <ToolChart title="Weekly closes" description="Count">
          {trendData.length ? (
            <ChartContainer width="100%" height={230}>
              <BarChart data={trendData} margin={{ top: 8, right: 16, bottom: 0, left: -4 }} barCategoryGap="30%">
                <CartesianGrid stroke={chartTheme.grid} vertical={false} />
                <XAxis dataKey="snapshot_week" tick={{ fontSize: 11, fill: chartTheme.axis }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: chartTheme.axis }} axisLine={false} tickLine={false} width={44} allowDecimals={false} />
                <ChartTooltip cursor={{ fill: 'rgba(67,100,52,0.05)' }} contentStyle={chartTheme.tooltip} formatter={(v) => [Number(v), 'Closes']} />
                <Bar dataKey="conversions_count" name="Closes" fill={chartTheme.positive} radius={[3, 3, 0, 0]} maxBarSize={64} />
              </BarChart>
            </ChartContainer>
          ) : (
            <ToolEmptyState title="No history yet" detail="Weekly closes appear after the first snapshot loads." />
          )}
        </ToolChart>
      </section>

      {/* Week-over-week progress */}
      {progress && progress.totals.prior_prospects > 0 && (
        <section className="pr-progress">
          <div className="pr-progress-head">
            <div>
              <h2>Week-over-Week Progress</h2>
              <p className="pr-progress-sub">
                Tracking {progressAgg.prior_prospects} prospects from last week&apos;s report
                {progressAgg.won.count > 0 && (
                  <> · <strong>{progressAgg.won.count} converted this week — {fmtMoney(progressAgg.won.paum)} PAUM</strong></>
                )}
              </p>
            </div>
          </div>

          <div className="pr-progress-tiles">
            <div className="pr-ptile pr-ptile-won">
              <span className="pr-ptile-count">{progressAgg.won.count}</span>
              <span className="pr-ptile-label">Won</span>
              <span className="pr-ptile-sub">{fmtMoney(progressAgg.won.paum)} PAUM</span>
            </div>
            <div className="pr-ptile pr-ptile-advanced">
              <span className="pr-ptile-count">{progressAgg.advanced.count}</span>
              <span className="pr-ptile-label">Advanced</span>
              <span className="pr-ptile-sub">{fmtMoney(progressAgg.advanced.paum)} PAUM</span>
            </div>
            <div className="pr-ptile pr-ptile-reengaged">
              <span className="pr-ptile-count">{progressAgg.re_engaged.count}</span>
              <span className="pr-ptile-label">Re-engaged</span>
              <span className="pr-ptile-sub">{fmtMoney(progressAgg.re_engaged.paum)} PAUM</span>
            </div>
            <div className="pr-ptile pr-ptile-stable">
              <span className="pr-ptile-count">{progressAgg.stable.count}</span>
              <span className="pr-ptile-label">Stable</span>
              <span className="pr-ptile-sub">{fmtMoney(progressAgg.stable.paum)} PAUM</span>
            </div>
            <div className="pr-ptile pr-ptile-dropped">
              <span className="pr-ptile-count">{progressAgg.dropped.count}</span>
              <span className="pr-ptile-label">Dropped</span>
              <span className="pr-ptile-sub">{fmtMoney(progressAgg.dropped.paum)} PAUM</span>
            </div>
          </div>

          {progressView && progressView.shown.length > 0 && (
            <table className="pr-table pr-progress-table">
              <thead>
                <tr>
                  <th>Prospect</th>
                  <th>Sales Person</th>
                  <th>Advisor</th>
                  <th className="pr-num">PAUM</th>
                  <th>Channel</th>
                  <th>Last Week</th>
                  <th>This Week</th>
                  <th>Score Change</th>
                  <th>Status</th>
                  <th>Note</th>
                </tr>
              </thead>
              <tbody>
                {progressView.shown.map((r) => {
                  const badge = PROGRESS_BADGE[r.status] ?? { label: r.status, cls: 'stable' };
                  const delta = r.score_prev != null && r.score_now != null ? r.score_now - r.score_prev : null;
                  const scoreChange =
                    delta != null
                      ? `${r.score_prev} → ${r.score_now} (${delta >= 0 ? '+' : ''}${delta})`
                      : '—';
                  return (
                    <tr key={r.lead_id}>
                      <td>
                        {r.sf_url
                          ? <a className="pr-name" href={r.sf_url} target="_blank" rel="noreferrer">{r.name}</a>
                          : <span className="pr-name">{r.name}</span>}
                      </td>
                      <td>{r.sales_person || '—'}</td>
                      <td>{r.advisor_name || '—'}</td>
                      <td className="pr-num">{fmtMoney(r.paum)}</td>
                      <td>{r.channel || '—'}</td>
                      <td><span className="pr-stage">{r.stage_prev.replace(/^\d+\s*-\s*/, '') || '—'}</span></td>
                      <td><span className="pr-stage">{r.stage_now ? r.stage_now.replace(/^\d+\s*-\s*/, '') : '—'}</span></td>
                      <td className="pr-score-change">{scoreChange}</td>
                      <td><span className={`pr-pstatus pr-pstatus-${badge.cls}`}>{badge.label}</span></td>
                      <td className="pr-progress-note">{r.note || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}

          {progressView && (progressView.omittedStable > 0 || progressView.omittedDropped > 0) && (
            <p className="pr-progress-foot">
              {progressView.omittedStable} stable
              {progressView.omittedDropped > 0 && <> and {progressView.omittedDropped} low-priority dropped</>} prospects omitted.
            </p>
          )}
        </section>
      )}

      {/* Scoring key */}
      <section className="pr-scoring">
        <div className="pr-scoring-head">
          <h3>Scoring Key</h3>
          <span className="pr-scoring-note">Higher score = higher priority to work this week</span>
        </div>
        <div className="pr-scoring-grid">
          {SCORING_KEY.map((col) => (
            <div className="pr-score-col" key={col.title}>
              <h4>{col.title}</h4>
              <ul>
                {col.items.map((it) => (
                  <li key={it.label}>
                    <span className="pr-score-label">{it.label}</span>
                    <span className={`pr-pts ${it.pts < 0 ? 'neg' : 'pos'}`}>
                      {it.pts > 0 ? `+${it.pts}` : it.pts}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

        {/* Focus list grouped by channel */}
        <div className="pr-list">
          <div className="pr-list-head">
            <span>{filteredTotals.count} prospects · {fmtMoney(filteredTotals.paum)} PAUM</span>
            <div className="pr-sort">
              <span>Sort:</span>
              <button className={sortKey === 'score' ? 'on' : ''} onClick={() => setSort('score')}>Score</button>
              <button className={sortKey === 'paum' ? 'on' : ''} onClick={() => setSort('paum')}>PAUM</button>
              <button className={sortKey === 'days_in_stage' ? 'on' : ''} onClick={() => setSort('days_in_stage')}>Days</button>
              <button className={sortKey === 'name' ? 'on' : ''} onClick={() => setSort('name')}>Name</button>
            </div>
          </div>

          {loading ? (
            <div className="pr-loading">Loading…</div>
          ) : !visible.length ? (
            <div className="pr-empty">No prospects match the current filters.</div>
          ) : (
            grouped.map(([channel, rows]) => {
              const groupPaum = rows.reduce((s, p) => s + p.paum, 0);
              return (
                <div className="pr-group" key={channel}>
                  <div className="pr-group-head" style={{ background: channelColor(channel) }}>
                    <span className="pr-group-name">{channel}</span>
                    <span className="pr-group-stat">{rows.length} · {fmtMoney(groupPaum)}</span>
                  </div>
                  <table className="pr-table">
                    <thead>
                      <tr>
                        <th className="pr-col-check">✓</th>
                        <th className="pr-col-dir">Dir</th>
                        <th>Prospect</th>
                        <th>Status</th>
                        <th className="pr-num">PAUM</th>
                        <th>Stage</th>
                        <th className="pr-num">Days / Avg</th>
                        <th>Last</th>
                        <th>Next</th>
                        <th className="pr-num">Score</th>
                        <th>Advisor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((p) => {
                        const isWorked = worked.has(p.lead_id);
                        const st = dwellStatus(p.days_in_stage, p.avg_dwell);
                        const dir = newSet.has(p.lead_id)
                          ? { label: 'NEW', cls: 'new' }
                          : advancedSet.has(p.lead_id)
                            ? { label: '↗', cls: 'up' }
                            : { label: '–', cls: 'flat' };
                        return (
                          <tr key={p.lead_id} className={isWorked ? 'pr-worked' : ''}>
                            <td className="pr-col-check">
                              <input type="checkbox" checked={isWorked}
                                onChange={() => toggleWorked(p.lead_id)} title="Mark as worked" />
                            </td>
                            <td className="pr-col-dir">
                              <span className={`pr-dir pr-dir-${dir.cls}`}>{dir.label}</span>
                            </td>
                            <td>
                              <a className="pr-name" href={p.sf_url} target="_blank" rel="noreferrer">{p.name}</a>
                              {p.sales_person && <span className="pr-sales">{p.sales_person}</span>}
                            </td>
                            <td><span className={`pr-status pr-status-${st.cls}`}>{st.label}</span></td>
                            <td className="pr-num">{fmtMoney(p.paum)}</td>
                            <td><span className="pr-stage">{p.stage.replace(/^\d+\s*-\s*/, '')}</span></td>
                            <td className="pr-num">{p.days_in_stage}<span className="pr-avg"> / {p.avg_dwell}</span></td>
                            <td>{fmtDate(p.last_activity_date)}</td>
                            <td>{fmtDate(p.next_activity_date)}</td>
                            <td className="pr-num" title={p.reasons || undefined}>
                              <span className="pr-score">{p.score}</span>
                              {p.reasons && <span className="pr-info">ⓘ</span>}
                            </td>
                            <td>{p.advisor_name}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              );
            })
          )}

          {/* Closed in last week */}
          {closedView.length > 0 && (
            <section className="pr-closed">
              <h2>Closed in Last Week · {closedView.length} · {fmtMoney(closedPaum)}</h2>
              {closedGrouped.map(([channel, rows]) => (
                <div className="pr-group" key={`closed-${channel}`}>
                  <div className="pr-group-head" style={{ background: channelColor(channel) }}>
                    <span className="pr-group-name">{channel}</span>
                    <span className="pr-group-stat">
                      {rows.length} · {fmtMoney(rows.reduce((s, c) => s + c.paum, 0))}
                    </span>
                  </div>
                  <table className="pr-table">
                    <thead>
                      <tr>
                        <th>Prospect</th>
                        <th className="pr-num">PAUM</th>
                        <th>Prev Stage</th>
                        <th>Advisor</th>
                        <th>Sales</th>
                        <th>Closed</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((c) => (
                        <tr key={c.lead_id}>
                          <td><a className="pr-name" href={c.sf_url} target="_blank" rel="noreferrer">{c.name}</a></td>
                          <td className="pr-num">{fmtMoney(c.paum)}</td>
                          <td><span className="pr-stage">{c.stage_prev.replace(/^\d+\s*-\s*/, '')}</span></td>
                          <td>{c.advisor_name || '—'}</td>
                          <td>{c.sales_person || '—'}</td>
                          <td>{fmtDate(c.close_date)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </section>
          )}

          {/* At-risk flags */}
          {(riskFlags.staleVerbals.length > 0 || riskFlags.noNextActivity.length > 0 || riskFlags.dropped.length > 0) && (
            <section className="pr-risks">
              <h2>At-Risk Flags</h2>

              {riskFlags.staleVerbals.length > 0 && (
                <div className="pr-group pr-risk-card">
                  <div className="pr-group-head pr-risk-head-overdue">
                    <span className="pr-group-name">⚠ Overdue Verbals — paperwork push</span>
                    <span className="pr-group-stat">
                      {riskFlags.staleVerbals.length} · {fmtMoney(riskFlags.staleVerbals.reduce((s, x) => s + x.p.paum, 0))}
                    </span>
                  </div>
                  <table className="pr-table">
                    <thead>
                      <tr>
                        <th>Prospect</th>
                        <th className="pr-num">PAUM</th>
                        <th className="pr-num">Overdue</th>
                        <th>Advisor</th>
                        <th>Sales</th>
                      </tr>
                    </thead>
                    <tbody>
                      {riskFlags.staleVerbals.map(({ p, overdue }) => (
                        <tr key={p.lead_id}>
                          <td><a className="pr-name" href={p.sf_url} target="_blank" rel="noreferrer">{p.name}</a></td>
                          <td className="pr-num">{fmtMoney(p.paum)}</td>
                          <td className="pr-num"><span className="pr-badge pr-badge-overdue">{overdue}d</span></td>
                          <td>{p.advisor_name || '—'}</td>
                          <td>{p.sales_person || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {riskFlags.noNextActivity.length > 0 && (
                <div className="pr-group pr-risk-card">
                  <div className="pr-group-head pr-risk-head-nonext">
                    <span className="pr-group-name">◷ High score, no next activity</span>
                    <span className="pr-group-stat">
                      {riskFlags.noNextActivity.length} · {fmtMoney(riskFlags.noNextActivity.reduce((s, p) => s + p.paum, 0))}
                    </span>
                  </div>
                  <table className="pr-table">
                    <thead>
                      <tr>
                        <th>Prospect</th>
                        <th className="pr-num">Score</th>
                        <th className="pr-num">PAUM</th>
                        <th>Stage</th>
                        <th>Advisor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {riskFlags.noNextActivity.map((p) => (
                        <tr key={p.lead_id}>
                          <td><a className="pr-name" href={p.sf_url} target="_blank" rel="noreferrer">{p.name}</a></td>
                          <td className="pr-num"><span className="pr-score">{p.score}</span></td>
                          <td className="pr-num">{fmtMoney(p.paum)}</td>
                          <td><span className="pr-stage">{p.stage.replace(/^\d+\s*-\s*/, '')}</span></td>
                          <td>{p.advisor_name || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {riskFlags.dropped.length > 0 && (
                <div className="pr-group pr-risk-card">
                  <div className="pr-group-head pr-risk-head-dropped">
                    <span className="pr-group-name">↓ Dropped from pipeline vs prior week</span>
                    <span className="pr-group-stat">
                      {riskFlags.dropped.length} · {fmtMoney(riskFlags.dropped.reduce((s, m) => s + m.paum, 0))}
                    </span>
                  </div>
                  <table className="pr-table">
                    <thead>
                      <tr>
                        <th>Prospect</th>
                        <th className="pr-num">PAUM</th>
                        <th>Was Stage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {riskFlags.dropped.map((m) => (
                        <tr key={m.lead_id}>
                          <td><span className="pr-name">{m.name}</span></td>
                          <td className="pr-num">{fmtMoney(m.paum)}</td>
                          <td><span className="pr-stage">{m.stage.replace(/^\d+\s*-\s*/, '')}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          )}
        </div>
        </div>
      </div>
    </ToolPage>
  );
}

// ─── Small presentational helpers ────────────────────────────────────────────

function Delta({ cur, prior, fmt }: { cur: number; prior: number | undefined; fmt: (n: number) => string }) {
  if (prior == null) return null;
  const d = cur - prior;
  if (Math.abs(d) < 1e-9) return <span className="pr-kpi-delta flat">▬ flat WoW</span>;
  return (
    <span className={`pr-kpi-delta ${d > 0 ? 'up' : 'down'}`}>
      {d > 0 ? '▲' : '▼'} {fmt(Math.abs(d))} WoW
    </span>
  );
}


// ─── Filter group (checkbox list) ────────────────────────────────────────────

function FilterGroup({ title, options, selected, onToggle }: {
  title: string;
  options: string[];
  selected: Set<string>;
  onToggle: (value: string) => void;
}) {
  if (!options.length) return null;
  return (
    <div className="pr-filter-group">
      <h4>{title}</h4>
      {options.map((opt) => (
        <label key={opt} className="pr-check">
          <input type="checkbox" checked={selected.has(opt)} onChange={() => onToggle(opt)} />
          {opt}
        </label>
      ))}
    </div>
  );
}
