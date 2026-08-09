// src/ExecutiveReport.tsx
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell,
  ErrorBar, LabelList,
} from 'recharts';
import { ChartContainer, ChartLegend, ChartTooltip } from './components/ui/chart';
import { ToolPage } from './components/ToolPage';
import { chartTheme } from './theme';
import './ExecutiveReport.css';

// ─── Types (match backend/executive_report payload) ──────────────────────────

interface FlowsKpis {
  current_year: number;
  prior_year: number;
  ytd_through: string;
  appts_current: number;
  appts_prior: number;
  appts_yoy_pct: number | null;
  appt_paum_current: number;
  appt_paum_prior: number;
  appt_paum_yoy_pct: number | null;
}

interface ChannelRow {
  channel: string;
  appts: number;
  paum: number;
  converted_ytd: number;
}

interface FunnelRow {
  year: number;
  channel: string;
  leads: number;
  appts: number;
  clients: number;
  l2a_rate: number;
  a2c_rate: number;
}

interface Flows {
  kpis: FlowsKpis;
  appts_paum_by_channel: ChannelRow[];
  funnel_by_channel_yoy: FunnelRow[];
  client_vs_prospect?: ClientProspectRow[];
  a2c_by_channel_yoy?: A2cChannelRow[];
  engagement?: Engagement | null;
  top_advisors_prospect_paum?: TopAdvisorRow[];
  aum?: AumFlows | null;
}

interface AumFlows {
  bop_aum: number;
  current_aum: number;
  aum_growth_pct: number | null;
  net_flows_current: number;
  net_flows_prior: number;
  net_flows_yoy_pct: number | null;
  bop_period: string | null;
  current_period: string | null;
}

interface ClientProspectRow {
  type: string;
  current: number;
  prior: number;
  yoy_pct: number | null;
}

interface A2cChannelRow {
  channel: string;
  a2c_current: number | null;
  a2c_prior: number | null;
  delta_pp: number | null;
}

interface EngagementTypeRow {
  type: string;
  current: number;
  prior: number;
  yoy_pct: number | null;
}

interface Engagement {
  current_year: number;
  prior_year: number;
  events_current: number;
  events_prior: number;
  events_yoy_pct: number | null;
  by_type: EngagementTypeRow[];
  current_month_label: string;
  month_pace_current: number;
  month_pace_prior: number;
  month_pace_yoy_pct: number | null;
}

interface TopAdvisorRow {
  advisor: string;
  top_channel: string;
  appts: number;
  clients: number;
  a2c_rate: number;
  paum: number;
}

interface NcnmChannel { channel: string; projection: number; p25: number; p75: number; cv: number; }
interface NcnmComponent { component: string; label: string; total: number; description: string; }
interface NcnmDetailAB { channel: string; close_month: string; paum: number; ncnm_paum_ratio: number; expected_ncnm: number; }
interface NcnmDetailC { channel: string; stage: string; prospects: number; paum: number; expected_ncnm: number; }
interface NcnmPeriod { month: string; label: string; total: number; by_component: Record<string, number>; }
interface NcnmHistoryRow { month: string; actual: number; }
interface AdvisorCloseRow { advisor: string; clients: number; paum: number; ncnm: number; }
interface NcnmRecruiting { label: string; mtd: number; by_month: Record<string, number>; }

interface Ncnm {
  as_of: string;
  period_label: string;
  mtd_actual: number;
  remaining_expected: number;
  eom_projection: number;
  grand_total: number;
  confidence: { cv: number; low: number; high: number };
  by_channel: NcnmChannel[];
  by_component: NcnmComponent[];
  by_period?: NcnmPeriod[];
  forward_30day_total?: number;
  monthly_history?: NcnmHistoryRow[];
  closes_by_advisor?: AdvisorCloseRow[];
  component_detail: { A: NcnmDetailAB[]; B: NcnmDetailAB[]; C: NcnmDetailC[] };
  recruiting?: NcnmRecruiting;
}

interface Summary { summary: string; model: string | null; source: string; }

interface Highlights {
  concerns: string[];
  bright_spots: string[];
  watch: string[];
  actions: string[];
}

interface ReportPayload {
  generated_at: string;
  flows: Flows;
  ncnm: Ncnm;
  summary: Summary;
  highlights?: Highlights;
}

// ─── Formatting helpers ──────────────────────────────────────────────────────

const fmtMoney = (v: number | null | undefined): string => {
  if (v == null) return '—';
  const a = Math.abs(v);
  const sign = v < 0 ? '-' : '';
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(1)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
};
const fmtInt = (v: number | null | undefined): string => (v == null ? '—' : v.toLocaleString());
const fmtPct = (v: number | null | undefined): string => (v == null ? 'n/a' : `${(v * 100).toFixed(1)}%`);
const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// 'YYYY-MM' → "Mon 'YY"
const monthLabel = (ym: string): string => {
  const [y, m] = ym.split('-');
  const mi = Number(m) - 1;
  if (mi < 0 || mi > 11) return ym;
  return `${MONTH_ABBR[mi]} '${y.slice(2)}`;
};
const fmtSignedPct = (v: number | null | undefined): string =>
  v == null ? 'n/a' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`;

const CHANNEL_COLORS: Record<string, string> = {
  'Advisor Driven': chartTheme.actual,
  CRP: chartTheme.comparison,
  'Media Driven': chartTheme.comparison,
  'Paid Leads': chartTheme.neutral,
};

// Render the AI summary: bold **headers** become styled section labels.
function renderSummary(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter((p) => p.length > 0);
  return parts.map((part, i) => {
    const m = part.match(/^\*\*([^*]+)\*\*$/);
    if (m) return <strong key={i} className="er-summary-head">{m[1]}</strong>;
    if (part.trim().startsWith('_') && part.trim().endsWith('_')) {
      return <em key={i} className="er-summary-note">{part.replace(/_/g, '')}</em>;
    }
    return <span key={i}>{part}</span>;
  });
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function ExecutiveReport() {
  const [data, setData] = useState<ReportPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fullFirm, setFullFirm] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/executive-report/api/report');
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || `HTTP ${res.status}`);
      setData(json.data as ReportPayload);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load report');
    } finally {
      setLoading(false);
    }
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const res = await fetch('/executive-report/api/refresh', { method: 'POST' });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || `HTTP ${res.status}`);
      setData(json.data as ReportPayload);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Refresh failed');
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const ncnm = data?.ncnm;
  const flows = data?.flows;
  const kpis = flows?.kpis;
  const aum = flows?.aum;

  // "Full firm flows" toggle adds Advisor Recruiting NCNM (excluded from the
  // forecast model) 1:1 to the MTD actual, the EoM projection, and each trailing
  // actual bar — so the confidence band and remaining-expected stay unchanged.
  const recruiting = ncnm?.recruiting;
  const hasRecruiting = (recruiting?.mtd ?? 0) > 0 || Object.keys(recruiting?.by_month ?? {}).length > 0;
  const recruitMtd = fullFirm ? (recruiting?.mtd ?? 0) : 0;
  const mtdActualAdj = (ncnm?.mtd_actual ?? 0) + recruitMtd;
  const eomProjectionAdj = (ncnm?.eom_projection ?? 0) + recruitMtd;
  const confLowAdj = (ncnm?.confidence.low ?? 0) + recruitMtd;
  const confHighAdj = (ncnm?.confidence.high ?? 0) + recruitMtd;

  const channelChartData = useMemo(
    () => (ncnm?.by_channel ?? []).map((c) => ({ name: c.channel, value: c.projection })),
    [ncnm],
  );

  // Forecast vs actual: trailing monthly NCNM actuals + current month split into
  // actual-so-far (MTD) and forecast remainder, with a low/high whisker on EoM.
  // Follows the "full firm flows" toggle: when on, trailing bars add that month's
  // Advisor Recruiting NCNM and the current month adds recruiting MTD 1:1 (matching
  // the KPI tiles), so the whole chart reflects full-firm flows.
  const forecastActualData = useMemo(() => {
    if (!ncnm) return [] as Array<Record<string, number | string | number[] | null>>;
    const recByMonth = fullFirm ? (ncnm.recruiting?.by_month ?? {}) : {};
    const recMtd = fullFirm ? (ncnm.recruiting?.mtd ?? 0) : 0;
    const rows: Array<Record<string, number | string | number[] | null>> = (ncnm.monthly_history ?? []).map((h) => {
      const actual = h.actual + (recByMonth[h.month] ?? 0);
      return {
        name: monthLabel(h.month),
        actual,
        // null (not 0) so the trailing months omit the "Forecast (remaining)" tooltip row
        remaining: null,
        total: actual,
      };
    });
    const curLabel = ncnm.as_of ? monthLabel(ncnm.as_of.slice(0, 7)) : 'This mo.';
    const eom = ncnm.eom_projection + recMtd;
    const low = ncnm.confidence.low + recMtd;
    const high = ncnm.confidence.high + recMtd;
    rows.push({
      name: curLabel,
      actual: ncnm.mtd_actual + recMtd,
      remaining: ncnm.remaining_expected,
      total: eom,
      // upper whisker span (EoM → P75) so the label can clear the error bar cap
      errHigh: Math.max(0, high - eom),
      // asymmetric error relative to the top of the stack (EoM projection)
      err: [Math.max(0, eom - low), Math.max(0, high - eom)],
    });
    return rows;
  }, [ncnm, fullFirm]);

  // Y-axis headroom: recharts sizes the domain from the stacked bar totals and
  // ignores the error bar, so on live data the whisker cap (P75) and the
  // current-month label render above the auto max and get clipped. Extend the
  // domain to the highest whisker cap plus a margin for the label text.
  const forecastYMax = useMemo(() => {
    let m = 0;
    for (const r of forecastActualData) {
      const total = (r.total as number) ?? 0;
      const errHigh = (r.errHigh as number) ?? 0;
      m = Math.max(m, total + errHigh);
    }
    return m > 0 ? Math.ceil((m * 1.12) / 1e6) * 1e6 : 0;
  }, [forecastActualData]);

  // Renders the stack total above every bar. Anchored on the `actual` segment
  // (non-zero for all months so it always fires); for the current month we climb
  // past the forecast segment and the whisker cap so the EoM total stays legible.
  const renderBarTotal = useCallback(
    (props: { x?: string | number; y?: string | number; width?: string | number; height?: string | number; index?: number }) => {
      const x = Number(props.x ?? 0);
      const y = Number(props.y ?? 0);
      const width = Number(props.width ?? 0);
      const height = Number(props.height ?? 0);
      const { index } = props;
      const row = index != null ? forecastActualData[index] : undefined;
      if (!row) return null;
      const actual = row.actual as number;
      const remaining = (row.remaining as number) ?? 0;
      const errHigh = (row.errHigh as number) ?? 0;
      let labelY = y - 6;
      if (remaining > 0 && actual > 0 && height > 0) {
        labelY = y - ((remaining + errHigh) / actual) * height - 8;
      }
      return (
        <text x={x + width / 2} y={labelY} textAnchor="middle" fontSize={11} fontWeight={600} fill={chartTheme.actual}>
          {fmtMoney(row.total as number)}
        </text>
      );
    },
    [forecastActualData],
  );

  const topCloses = ncnm?.closes_by_advisor ?? [];
  const advisorClosesData = useMemo(
    () => topCloses.map((c) => ({ name: c.advisor, paum: c.paum, ncnm: c.ncnm, clients: c.clients })),
    [topCloses],
  );

  const a2cChartData = useMemo(
    () =>
      (flows?.a2c_by_channel_yoy ?? [])
        .filter((r) => r.a2c_current != null || r.a2c_prior != null)
        .map((r) => ({
          name: r.channel,
          prior: r.a2c_prior != null ? +(r.a2c_prior * 100).toFixed(1) : 0,
          current: r.a2c_current != null ? +(r.a2c_current * 100).toFixed(1) : 0,
        })),
    [flows],
  );

  const highlights = data?.highlights;
  const topAdvisors = flows?.top_advisors_prospect_paum ?? [];

  const currentFunnel = useMemo(
    () => (flows?.funnel_by_channel_yoy ?? []).filter((r) => r.year === kpis?.current_year),
    [flows, kpis],
  );
  const priorFunnelMap = useMemo(() => {
    const map = new Map<string, FunnelRow>();
    (flows?.funnel_by_channel_yoy ?? [])
      .filter((r) => r.year === kpis?.prior_year)
      .forEach((r) => map.set(r.channel, r));
    return map;
  }, [flows, kpis]);

  return (
    <ToolPage
      eyebrow="Executive analytics"
      title="Executive Report"
      description={ncnm ? `Company flows and NCNM forecast · ${ncnm.period_label}` : 'Company flows and NCNM forecast'}
      width="full"
      className="er-root"
      actions={<>
          {data && (
            <span className="er-generated">
              Refreshed {new Date(data.generated_at).toLocaleString()}
            </span>
          )}
          <button className="er-btn" onClick={refresh} disabled={loading || refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh data'}
          </button>
      </>}
    >

      {error && <div className="er-error">Error: {error}</div>}

      {loading && !data && (
        <div className="er-loading">Building executive report… (first load queries the warehouse)</div>
      )}

      {data && ncnm && flows && kpis && (
        <div className="er-main">
          {hasRecruiting && (
            <div className="er-flow-toggle">
              <label className="er-switch">
                <input
                  type="checkbox"
                  checked={fullFirm}
                  onChange={(e) => setFullFirm(e.target.checked)}
                />
                <span className="er-switch-track"><span className="er-switch-thumb" /></span>
                <span className="er-switch-label">
                  Full firm flows
                  <span className="er-switch-note">
                    {fullFirm
                      ? `Including ${fmtMoney(recruiting?.mtd ?? 0)} Advisor Recruiting NCNM this month`
                      : 'Modeled channels only — toggle to add Advisor Recruiting NCNM'}
                  </span>
                </span>
              </label>
            </div>
          )}

          {/* KPI hero cards */}
          <section className="er-kpi-grid">
            {aum && (
              <div className="er-kpi" style={{ borderTopColor: chartTheme.actual }}>
                <p className="er-kpi-label">BoP AUM</p>
                <p className="er-kpi-value">{fmtMoney(aum.bop_aum)}</p>
                <p className={`er-kpi-sub ${(aum.aum_growth_pct ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                  {fmtMoney(aum.current_aum)} now · {fmtSignedPct(aum.aum_growth_pct)} YTD
                </p>
              </div>
            )}
            {aum && (
              <div className="er-kpi" style={{ borderTopColor: chartTheme.comparison }}>
                <p className="er-kpi-label">Net Flows YTD</p>
                <p className="er-kpi-value">{fmtMoney(aum.net_flows_current)}</p>
                <p className={`er-kpi-sub ${(aum.net_flows_yoy_pct ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                  {fmtSignedPct(aum.net_flows_yoy_pct)} vs {kpis.prior_year}
                </p>
              </div>
            )}
            <div className="er-kpi" style={{ borderTopColor: chartTheme.actual }}>
              <p className="er-kpi-label">EoM NCNM Projection{fullFirm ? ' · Full Firm' : ''}</p>
              <p className="er-kpi-value">{fmtMoney(eomProjectionAdj)}</p>
              <p className="er-kpi-sub">
                Range {fmtMoney(confLowAdj)} – {fmtMoney(confHighAdj)}
              </p>
            </div>
            <div className="er-kpi" style={{ borderTopColor: chartTheme.comparison }}>
              <p className="er-kpi-label">MTD NCNM Actual{fullFirm ? ' · Full Firm' : ' · Modeled'}</p>
              <p className="er-kpi-value">{fmtMoney(mtdActualAdj)}</p>
              <p className="er-kpi-sub">
                {fullFirm && recruitMtd > 0
                  ? `Incl. ${fmtMoney(recruitMtd)} recruiting · remaining ${fmtMoney(ncnm.remaining_expected)}`
                  : `Remaining expected ${fmtMoney(ncnm.remaining_expected)}`}
              </p>
            </div>
            <div className="er-kpi" style={{ borderTopColor: chartTheme.neutral }}>
              <p className="er-kpi-label">YTD Appointments</p>
              <p className="er-kpi-value">{fmtInt(kpis.appts_current)}</p>
              <p className={`er-kpi-sub ${(kpis.appts_yoy_pct ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                {fmtSignedPct(kpis.appts_yoy_pct)} vs {kpis.prior_year}
              </p>
            </div>
            <div className="er-kpi" style={{ borderTopColor: chartTheme.comparison }}>
              <p className="er-kpi-label">YTD Appointment PAUM</p>
              <p className="er-kpi-value">{fmtMoney(kpis.appt_paum_current)}</p>
              <p className={`er-kpi-sub ${(kpis.appt_paum_yoy_pct ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                {fmtSignedPct(kpis.appt_paum_yoy_pct)} vs {kpis.prior_year}
              </p>
            </div>
          </section>

          {/* NCNM forecast vs actual — trailing actuals + current-month projection */}
          {forecastActualData.length > 0 && (
            <section className="er-panel">
              <h2>
                NCNM — Trailing Actuals + Current-Month Projection
                <span className="er-panel-total"> · EoM {fmtMoney(eomProjectionAdj)} ({fmtMoney(confLowAdj)}–{fmtMoney(confHighAdj)}){fullFirm ? ' · full firm' : ''}</span>
              </h2>
              <ChartContainer width="100%" height={280}>
                <BarChart data={forecastActualData} margin={{ top: 12, right: 16, left: 8, bottom: 8 }}>
                  <CartesianGrid stroke={chartTheme.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis domain={[0, forecastYMax || 'auto']} tickFormatter={(v) => fmtMoney(v as number)} tick={{ fontSize: 11 }} width={64} />
                  <ChartTooltip contentStyle={chartTheme.tooltip} formatter={(v, n) => [fmtMoney(v as number), n as string]} />
                  <ChartLegend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="actual" name="Actual NCNM" stackId="ncnm" fill={chartTheme.actual} radius={[0, 0, 0, 0]}>
                    <LabelList content={renderBarTotal} />
                  </Bar>
                  <Bar dataKey="remaining" name="Forecast (remaining)" stackId="ncnm" fill={chartTheme.neutral} radius={[3, 3, 0, 0]}>
                    <ErrorBar dataKey="err" width={6} strokeWidth={1.5} stroke={chartTheme.actual} direction="y" />
                  </Bar>
                </BarChart>
              </ChartContainer>
              <p className="er-chart-note">
                Bars show completed monthly NCNM. The final bar is the current month: booked
                month-to-date ({fmtMoney(mtdActualAdj)}) plus forecast remainder
                ({fmtMoney(ncnm.remaining_expected)}); the whisker marks the P25–P75 range.
                {fullFirm ? ' Includes Advisor Recruiting NCNM (full firm flows).' : ''}
              </p>
            </section>
          )}

          {/* NCNM component breakdown + channel chart */}
          <section className="er-two-col">
            <div className="er-panel">
              <h2>NCNM Forecast Components</h2>
              <div className="er-components">
                {ncnm.by_component.map((c) => (
                  <div key={c.component} className="er-component">
                    <div className="er-component-top">
                      <span className="er-component-badge">{c.component}</span>
                      <span className="er-component-total">{fmtMoney(c.total)}</span>
                    </div>
                    <p className="er-component-label">{c.label}</p>
                    <p className="er-component-desc">{c.description}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="er-panel">
              <h2>Projected NCNM by Channel</h2>
              <ChartContainer width="100%" height={220}>
                <BarChart data={channelChartData} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
                  <CartesianGrid stroke={chartTheme.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => fmtMoney(v as number)} tick={{ fontSize: 11 }} width={64} />
                  <ChartTooltip contentStyle={chartTheme.tooltip} formatter={(v) => fmtMoney(v as number)} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                    {channelChartData.map((d) => (
                      <Cell key={d.name} fill={CHANNEL_COLORS[d.name] ?? chartTheme.actual} />
                    ))}
                  </Bar>
                </BarChart>
              </ChartContainer>
            </div>
          </section>

          {/* Closes this month by advisor — PAUM + accompanying NCNM */}
          {advisorClosesData.length > 0 && (
            <section className="er-panel">
              <h2>Closes This Month by Advisor — PAUM &amp; NCNM</h2>
              <ChartContainer width="100%" height={Math.max(200, advisorClosesData.length * 52)}>
                <BarChart
                  data={advisorClosesData}
                  layout="vertical"
                  margin={{ top: 8, right: 80, left: 12, bottom: 8 }}
                  barGap={2}
                >
                  <CartesianGrid stroke={chartTheme.grid} horizontal={false} />
                  <XAxis type="number" tickFormatter={(v) => fmtMoney(v as number)} tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={130} interval={0} />
                  <ChartTooltip
                    contentStyle={chartTheme.tooltip}
                    formatter={(v, n) => [fmtMoney(v as number), n]}
                    labelFormatter={(label, payload) => {
                      const p = payload?.[0]?.payload as { clients?: number } | undefined;
                      return p?.clients != null ? `${label} · ${p.clients} new client${p.clients === 1 ? '' : 's'}` : String(label);
                    }}
                  />
                  <ChartLegend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="paum" name="Closed PAUM" fill={chartTheme.actual} radius={[0, 3, 3, 0]}>
                    <LabelList dataKey="paum" position="right" formatter={(v) => fmtMoney(v as number)} style={{ fontSize: 11, fill: chartTheme.actual }} />
                  </Bar>
                  <Bar dataKey="ncnm" name="NCNM (all to date)" fill={chartTheme.comparison} radius={[0, 3, 3, 0]}>
                    <LabelList dataKey="ncnm" position="right" formatter={(v) => fmtMoney(v as number)} style={{ fontSize: 11, fill: chartTheme.comparison }} />
                  </Bar>
                </BarChart>
              </ChartContainer>
              <p className="er-chart-note">
                Ranked by new-client PAUM closed month-to-date. NCNM is the total net-new-client
                money booked to date for those same households.
              </p>
            </section>
          )}

          {/* NCNM 30-day forward: this-month tail vs next-month opening */}
          {ncnm.by_period && ncnm.by_period.length > 0 && (
            <section className="er-panel">
              <h2>
                30-Day Forward NCNM — Tail vs Opening
                {ncnm.forward_30day_total != null && (
                  <span className="er-panel-total"> · {fmtMoney(ncnm.forward_30day_total)} total</span>
                )}
              </h2>
              <table className="er-table">
                <thead>
                  <tr>
                    <th>Window</th>
                    <th className="num">A · Tail funding</th>
                    <th className="num">B · Unfunded</th>
                    <th className="num">C · Pipeline</th>
                    <th className="num">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {ncnm.by_period.map((p) => (
                    <tr key={p.month}>
                      <td className="er-strong">{p.label}</td>
                      <td className="num muted">{fmtMoney(p.by_component.A)}</td>
                      <td className="num muted">{fmtMoney(p.by_component.B)}</td>
                      <td className="num muted">{fmtMoney(p.by_component.C)}</td>
                      <td className="num">{fmtMoney(p.total)}</td>
                    </tr>
                  ))}
                  {ncnm.forward_30day_total != null && (
                    <tr className="er-total-row">
                      <td>Total</td>
                      <td className="num">{fmtMoney(ncnm.by_period.reduce((s, p) => s + (p.by_component.A ?? 0), 0))}</td>
                      <td className="num">{fmtMoney(ncnm.by_period.reduce((s, p) => s + (p.by_component.B ?? 0), 0))}</td>
                      <td className="num">{fmtMoney(ncnm.by_period.reduce((s, p) => s + (p.by_component.C ?? 0), 0))}</td>
                      <td className="num">{fmtMoney(ncnm.forward_30day_total)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </section>
          )}

          {/* NCNM channel confidence table */}
          <section className="er-panel">
            <h2>NCNM by Channel — Confidence Range</h2>
            <table className="er-table">
              <thead>
                <tr>
                  <th>Channel</th>
                  <th className="num">Projection</th>
                  <th className="num">P25</th>
                  <th className="num">P75</th>
                  <th className="num">CV</th>
                </tr>
              </thead>
              <tbody>
                {ncnm.by_channel.map((c) => (
                  <tr key={c.channel}>
                    <td style={{ color: CHANNEL_COLORS[c.channel] ?? chartTheme.actual, fontWeight: 600 }}>{c.channel}</td>
                    <td className="num">{fmtMoney(c.projection)}</td>
                    <td className="num muted">{fmtMoney(c.p25)}</td>
                    <td className="num muted">{fmtMoney(c.p75)}</td>
                    <td className="num muted">{fmtPct(c.cv)}</td>
                  </tr>
                ))}
                <tr className="er-total-row">
                  <td>Total</td>
                  <td className="num">{fmtMoney(ncnm.grand_total)}</td>
                  <td className="num">{fmtMoney(ncnm.confidence.low)}</td>
                  <td className="num">{fmtMoney(ncnm.confidence.high)}</td>
                  <td className="num">{fmtPct(ncnm.confidence.cv)}</td>
                </tr>
              </tbody>
            </table>
          </section>

          {/* A2C rate by channel — prior vs current year */}
          {a2cChartData.length > 0 && (
            <section className="er-panel">
              <h2>Appt-to-Client Rate by Channel — {kpis.prior_year} vs {kpis.current_year}</h2>
              <ChartContainer width="100%" height={260}>
                <BarChart data={a2cChartData} margin={{ top: 8, right: 12, left: 0, bottom: 8 }}>
                  <CartesianGrid stroke={chartTheme.grid} />
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} width={44} />
                  <ChartTooltip contentStyle={chartTheme.tooltip} formatter={(v) => `${v}%`} />
                  <ChartLegend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="prior" name={`${kpis.prior_year}`} fill={chartTheme.prior} radius={[3, 3, 0, 0]} />
                  <Bar dataKey="current" name={`${kpis.current_year}`} fill={chartTheme.actual} radius={[3, 3, 0, 0]} />
                </BarChart>
              </ChartContainer>
            </section>
          )}

          {/* Channel funnel YoY */}
          <section className="er-panel">
            <h2>Conversion Funnel by Channel — {kpis.current_year} YTD vs {kpis.prior_year}</h2>
            <table className="er-table">
              <thead>
                <tr>
                  <th>Channel</th>
                  <th className="num">Leads</th>
                  <th className="num">Appts</th>
                  <th className="num">Clients</th>
                  <th className="num">L2A</th>
                  <th className="num">A2C</th>
                  <th className="num">A2C Δ YoY</th>
                </tr>
              </thead>
              <tbody>
                {currentFunnel.map((r) => {
                  const prior = priorFunnelMap.get(r.channel);
                  const a2cDelta = prior ? r.a2c_rate - prior.a2c_rate : null;
                  return (
                    <tr key={r.channel}>
                      <td className="er-strong">{r.channel}</td>
                      <td className="num">{fmtInt(r.leads)}</td>
                      <td className="num">{fmtInt(r.appts)}</td>
                      <td className="num">{fmtInt(r.clients)}</td>
                      <td className="num muted">{fmtPct(r.l2a_rate)}</td>
                      <td className="num">{fmtPct(r.a2c_rate)}</td>
                      <td className={`num ${a2cDelta == null ? 'muted' : a2cDelta >= 0 ? 'pos' : 'neg'}`}>
                        {a2cDelta == null ? '—' : fmtSignedPct(a2cDelta)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>

          {/* Appointment PAUM by channel */}
          <section className="er-panel">
            <h2>Appointment PAUM by Channel — {kpis.current_year} YTD</h2>
            <table className="er-table">
              <thead>
                <tr>
                  <th>Channel</th>
                  <th className="num">Appts</th>
                  <th className="num">Appt PAUM</th>
                  <th className="num">Converted YTD</th>
                </tr>
              </thead>
              <tbody>
                {flows.appts_paum_by_channel.map((r) => (
                  <tr key={r.channel}>
                    <td className="er-strong">{r.channel}</td>
                    <td className="num">{fmtInt(r.appts)}</td>
                    <td className="num">{fmtMoney(r.paum)}</td>
                    <td className="num">{fmtInt(r.converted_ytd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* Top advisors by prospect PAUM (media / paid channels) */}
          {topAdvisors.length > 0 && (
            <section className="er-panel">
              <h2>Top Advisors by Prospect PAUM — Media &amp; Paid Channels ({kpis.current_year} YTD)</h2>
              <table className="er-table">
                <thead>
                  <tr>
                    <th>Advisor</th>
                    <th>Top channel</th>
                    <th className="num">Appts</th>
                    <th className="num">Clients</th>
                    <th className="num">A2C</th>
                    <th className="num">Prospect PAUM</th>
                  </tr>
                </thead>
                <tbody>
                  {topAdvisors.map((r) => (
                    <tr key={r.advisor}>
                      <td className="er-strong">{r.advisor}</td>
                      <td className="muted">{r.top_channel}</td>
                      <td className="num">{fmtInt(r.appts)}</td>
                      <td className="num">{fmtInt(r.clients)}</td>
                      <td className={`num ${r.a2c_rate < 0.1 ? 'neg' : ''}`}>{fmtPct(r.a2c_rate)}</td>
                      <td className="num">{fmtMoney(r.paum)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          {/* AI summary */}
          <section className="er-summary-card">
            <div className="er-summary-title">
              <span>Executive Summary</span>
              <span className="er-summary-src">
                {data.summary.source === 'llm' ? `AI · ${data.summary.model}` : 'Deterministic'}
              </span>
            </div>
            <div className="er-summary-body">{renderSummary(data.summary.summary)}</div>
          </section>

          {/* Structured highlights — concerns / bright spots / watch / actions */}
          {highlights &&
            (highlights.concerns.length > 0 ||
              highlights.bright_spots.length > 0 ||
              highlights.watch.length > 0 ||
              highlights.actions.length > 0) && (
              <section className="er-highlights">
                <div className="er-two-col">
                  {highlights.concerns.length > 0 && (
                    <div className="er-panel er-hl er-hl-concern">
                      <h2>⚠ Needs Immediate Attention</h2>
                      <ul className="er-hl-list">
                        {highlights.concerns.map((t, i) => <li key={i}>{t}</li>)}
                      </ul>
                    </div>
                  )}
                  <div className="er-hl-col">
                    {highlights.bright_spots.length > 0 && (
                      <div className="er-panel er-hl er-hl-bright">
                        <h2>↑ Bright Spots</h2>
                        <ul className="er-hl-list">
                          {highlights.bright_spots.map((t, i) => <li key={i}>{t}</li>)}
                        </ul>
                      </div>
                    )}
                    {highlights.watch.length > 0 && (
                      <div className="er-panel er-hl er-hl-watch">
                        <h2>~ Watch</h2>
                        <ul className="er-hl-list">
                          {highlights.watch.map((t, i) => <li key={i}>{t}</li>)}
                        </ul>
                      </div>
                    )}
                  </div>
                </div>
                {highlights.actions.length > 0 && (
                  <div className="er-actions">
                    <div className="er-actions-title">Priority Actions</div>
                    <ol>
                      {highlights.actions.map((t, i) => <li key={i}>{t}</li>)}
                    </ol>
                  </div>
                )}
              </section>
            )}

          <footer className="er-footer">
            Allworth Financial · Growth Analytics · Data as of {ncnm.as_of}. NCNM is a probabilistic
            forecast; warehouse data refreshes daily.
          </footer>
        </div>
      )}
    </ToolPage>
  );
}
