import { useEffect, useMemo, useState } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { InboxProvider, useInbox } from '../brief/store';
import { demoMetrics } from '../data/demoMetrics';
import { fetchKpiMetrics } from '../services/api';
import { crmApi } from '../services/crm';
import type { CrmClient } from '../services/crm';
import type { KpiDataset, KpiEntry } from '../types/kpi';
import './AccountToolWidgets.css';

const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

type WidgetKey = 'performance' | 'crm' | 'fee_calculator' | 'pipeline_review' | 'brief' | 'avantos';

interface AccountToolWidgetsProps {
  enabled: Record<WidgetKey, boolean>;
  accountLabel: string;
}

interface WidgetShellProps {
  eyebrow: string;
  title: string;
  href: string;
  children: ReactNode;
  status?: string;
}

function WidgetShell({ eyebrow, title, href, children, status }: WidgetShellProps) {
  return (
    <article className="account-tool-widget">
      <header className="account-tool-widget-header">
        <div>
          <p>{eyebrow}</p>
          <h3>{title}</h3>
        </div>
        {status && <span className="account-tool-widget-status">{status}</span>}
      </header>
      <div className="account-tool-widget-body">{children}</div>
      <a className="account-tool-widget-link" href={href}>
        Open full tool
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></svg>
      </a>
    </article>
  );
}

const METRICS = ['NCNM', 'Clients', 'Appointments', 'Leads'] as const;
type MetricName = typeof METRICS[number];

function periodValue(period: string): number {
  const parsed = Date.parse(period.includes('-') ? `${period}-01` : `1 ${period}`);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function latestTotal(data: KpiDataset, metric: MetricName): KpiEntry | null {
  return [...data]
    .filter((entry) => entry.metric === metric && entry.channel === 'Total')
    .sort((a, b) => periodValue(b.period) - periodValue(a.period))[0] ?? null;
}

function formatMetric(value: number, entry: KpiEntry): string {
  if (entry.currency === 'USD' && entry.unit === 'millions') return `$${value.toFixed(1)}M`;
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 }).format(value);
}

function PerformanceWidget() {
  const [metric, setMetric] = useState<MetricName>('NCNM');
  const [data, setData] = useState<KpiDataset>(DEMO_MODE ? demoMetrics : []);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (DEMO_MODE) return;
    void fetchKpiMetrics().then(setData).catch(() => setError(true));
  }, []);

  const entry = useMemo(() => latestTotal(data, metric), [data, metric]);
  const plan = entry ? (entry.goalProrated ?? entry.goal) : 0;
  const priorYear = entry ? (entry.pyProrated ?? entry.pyActual ?? 0) : 0;
  const progress = plan > 0 && entry ? Math.min((entry.actual / plan) * 100, 100) : 0;

  return (
    <WidgetShell eyebrow="Growth performance" title="Performance by Channel" href="/reporting/kpi" status={entry?.periodLabel ?? entry?.period}>
      <div className="account-widget-segment" role="group" aria-label="Performance metric">
        {METRICS.map((name) => (
          <button key={name} type="button" className={metric === name ? 'active' : ''} onClick={() => setMetric(name)}>{name}</button>
        ))}
      </div>
      {entry ? (
        <>
          <div className="performance-primary">
            <span>Actual</span>
            <strong>{formatMetric(entry.actual, entry)}</strong>
          </div>
          <div className="performance-track" aria-label={`${Math.round(progress)} percent of plan`}><span style={{ width: `${progress}%` }} /></div>
          <div className="performance-comparison">
            <div><span>Plan to date</span><strong>{formatMetric(plan, entry)}</strong></div>
            <div><span>Prior year to date</span><strong>{formatMetric(priorYear, entry)}</strong></div>
            <div><span>Against plan</span><strong className={entry.actual >= plan ? 'positive' : 'negative'}>{plan ? `${entry.actual >= plan ? '+' : ''}${(((entry.actual - plan) / plan) * 100).toFixed(1)}%` : '—'}</strong></div>
          </div>
        </>
      ) : (
        <p className="account-widget-empty">{error ? 'Performance data is unavailable.' : 'Loading performance…'}</p>
      )}
    </WidgetShell>
  );
}

function CrmWidget() {
  const [query, setQuery] = useState('');
  const [clients, setClients] = useState<CrmClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError(false);
      void crmApi.getClients({ q: query, limit: 5 })
        .then((rows) => setClients(rows.slice(0, 4)))
        .catch(() => setError(true))
        .finally(() => setLoading(false));
    }, query ? 180 : 0);
    return () => window.clearTimeout(timer);
  }, [query]);

  return (
    <WidgetShell eyebrow="Client relationships" title="CRM" href="/crm" status={loading ? 'Searching…' : `${clients.length} in view`}>
      <label className="crm-widget-search">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search client or household" aria-label="Search CRM clients" />
      </label>
      {error ? <p className="account-widget-empty">CRM search is unavailable.</p> : (
        <div className="crm-widget-list">
          {clients.map((client) => (
            <a key={client.lead_id} href={`/crm?client=${encodeURIComponent(client.lead_id)}`}>
              <div><strong>{client.name}</strong><span>{client.advisor_name} · {client.segment || client.hh_status}</span></div>
              <div><strong>{currency(client.aum)}</strong><span>{client.state || '—'}</span></div>
            </a>
          ))}
          {!loading && !clients.length && <p className="account-widget-empty">No matching clients.</p>}
        </div>
      )}
    </WidgetShell>
  );
}

interface FeeTier { from: number; to: number | null; rate: number }
interface FeeSchedule { name: string; minQuarterly: number; tiers: FeeTier[] }
interface FeeResult { annualFee: number; quarterlyFee: number; effectiveRate: number; minApplied: boolean }

const FEE_SCHEDULES: Record<string, FeeSchedule> = {
  gm_schedule_new: {
    name: 'GM Schedule New',
    minQuarterly: 2_500,
    tiers: [
      { from: 0, to: 250_000, rate: 0.015 }, { from: 250_001, to: 750_000, rate: 0.0125 },
      { from: 750_001, to: 1_500_000, rate: 0.01 }, { from: 1_500_001, to: 3_000_000, rate: 0.008 },
      { from: 3_000_001, to: 5_000_000, rate: 0.007 }, { from: 5_000_001, to: 7_500_000, rate: 0.006 },
      { from: 7_500_001, to: 10_000_000, rate: 0.004 }, { from: 10_000_001, to: 50_000_000, rate: 0.0035 },
      { from: 50_000_001, to: null, rate: 0.003 },
    ],
  },
  airline: {
    name: 'New Airline Clients',
    minQuarterly: 0,
    tiers: [
      { from: 0, to: 500_000, rate: 0.012 }, { from: 500_001, to: 1_000_000, rate: 0.011 },
      { from: 1_000_001, to: 1_500_000, rate: 0.01 }, { from: 1_500_001, to: 2_000_000, rate: 0.009 },
      { from: 2_000_001, to: null, rate: 0.007 },
    ],
  },
};

function calculateLocalFee(aum: number, schedule: FeeSchedule): FeeResult {
  let remaining = aum;
  let annualFee = 0;
  for (const tier of schedule.tiers) {
    if (remaining <= 0) break;
    const band = tier.to === null ? remaining : tier.to - tier.from + (tier.from > 0 ? 1 : 0);
    const assets = Math.min(remaining, band);
    annualFee += assets * tier.rate;
    remaining -= assets;
  }
  let quarterlyFee = annualFee / 4;
  const minApplied = schedule.minQuarterly > 0 && quarterlyFee < schedule.minQuarterly;
  if (minApplied) {
    quarterlyFee = schedule.minQuarterly;
    annualFee = quarterlyFee * 4;
  }
  return { annualFee, quarterlyFee, effectiveRate: aum > 0 ? (annualFee / aum) * 100 : 0, minApplied };
}

function currency(value: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

function FeeCalculatorWidget() {
  const [aumText, setAumText] = useState('2,000,000');
  const [scheduleKey, setScheduleKey] = useState('gm_schedule_new');
  const [result, setResult] = useState<FeeResult>(() => calculateLocalFee(2_000_000, FEE_SCHEDULES.gm_schedule_new));
  const [calculating, setCalculating] = useState(false);
  const [error, setError] = useState('');

  const calculate = async (event: FormEvent) => {
    event.preventDefault();
    const aum = Number(aumText.replace(/[^0-9.]/g, ''));
    if (!Number.isFinite(aum) || aum <= 0) {
      setError('Enter a valid AUM greater than zero.');
      return;
    }
    setCalculating(true);
    setError('');
    try {
      if (!DEMO_MODE) {
        const response = await fetch('/fee-calculator/api/calculate', {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ aum, schedule: scheduleKey }),
        });
        const payload = await response.json() as { success: boolean; data?: { annual_fee: number; quarterly_fee: number; effective_rate_pct: number; min_fee_applied: boolean }; error?: string };
        if (!response.ok || !payload.success || !payload.data) throw new Error(payload.error ?? 'Calculation failed');
        setResult({ annualFee: payload.data.annual_fee, quarterlyFee: payload.data.quarterly_fee, effectiveRate: payload.data.effective_rate_pct, minApplied: payload.data.min_fee_applied });
      } else {
        setResult(calculateLocalFee(aum, FEE_SCHEDULES[scheduleKey]));
      }
      setAumText(new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(aum));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Calculation failed.');
    } finally {
      setCalculating(false);
    }
  };

  return (
    <WidgetShell eyebrow="Client pricing" title="Fee Calculator" href="/fee-calculator" status="Tiered fee">
      <form className="fee-widget-form" onSubmit={calculate}>
        <label><span>Household AUM</span><div className="fee-widget-money"><b>$</b><input value={aumText} onChange={(event) => setAumText(event.target.value)} inputMode="decimal" aria-label="Household assets under management" /></div></label>
        <label><span>Schedule</span><select value={scheduleKey} onChange={(event) => setScheduleKey(event.target.value)}>{Object.entries(FEE_SCHEDULES).map(([key, value]) => <option key={key} value={key}>{value.name}</option>)}</select></label>
        <button type="submit" disabled={calculating}>{calculating ? 'Calculating…' : 'Calculate'}</button>
      </form>
      {error ? <p className="account-widget-error">{error}</p> : (
        <div className="fee-widget-result" aria-live="polite">
          <div><span>Annual fee</span><strong>{currency(result.annualFee)}</strong></div>
          <div><span>Quarterly</span><strong>{currency(result.quarterlyFee)}</strong></div>
          <div><span>Effective rate</span><strong>{result.effectiveRate.toFixed(3)}%</strong></div>
          {result.minApplied && <small>Quarterly minimum applied</small>}
        </div>
      )}
    </WidgetShell>
  );
}

interface PipelineProspect { lead_id: string; name: string; paum: number; stage: string; score: number; was_stale: boolean; advisor_name: string }

const DEMO_PIPELINE: PipelineProspect[] = [
  { lead_id: 'preview-101', name: 'Harbor Ridge Household', paum: 8_400_000, stage: '7 - Verbal Commitment Received', score: 92, was_stale: false, advisor_name: 'Morgan Lee' },
  { lead_id: 'preview-102', name: 'Evergreen Family', paum: 5_750_000, stage: '6 - Proposal Delivered', score: 81, was_stale: true, advisor_name: 'Jordan Patel' },
  { lead_id: 'preview-103', name: 'Northstar Household', paum: 3_200_000, stage: '5 - Discovery', score: 67, was_stale: true, advisor_name: 'Casey Grant' },
  { lead_id: 'preview-104', name: 'Stonebridge Family', paum: 2_600_000, stage: '8 - Onboarding', score: 63, was_stale: false, advisor_name: 'Taylor Brooks' },
];

function PipelineWidget() {
  const [prospects, setProspects] = useState<PipelineProspect[]>(DEMO_MODE ? DEMO_PIPELINE : []);
  const [atRiskOnly, setAtRiskOnly] = useState(false);
  const [worked, setWorked] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem('home-pipeline-worked') ?? '[]') as string[]); } catch { return new Set(); }
  });
  const [loading, setLoading] = useState(!DEMO_MODE);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (DEMO_MODE) return;
    void fetch('/pipeline-review/api/snapshot')
      .then(async (response) => {
        const payload = await response.json() as { success: boolean; data?: { prospects: PipelineProspect[] } };
        if (!response.ok || !payload.success || !payload.data) throw new Error('Pipeline unavailable');
        setProspects(payload.data.prospects);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const visible = prospects.filter((prospect) => !worked.has(prospect.lead_id) && (!atRiskOnly || prospect.was_stale)).slice(0, 3);
  const atRiskCount = prospects.filter((prospect) => prospect.was_stale && !worked.has(prospect.lead_id)).length;
  const toggleWorked = (id: string) => {
    setWorked((current) => {
      const next = new Set(current);
      next.has(id) ? next.delete(id) : next.add(id);
      try { localStorage.setItem('home-pipeline-worked', JSON.stringify([...next])); } catch { /* local state still works */ }
      return next;
    });
  };

  return (
    <WidgetShell eyebrow="Prospect focus" title="Pipeline Review" href="/pipeline-review" status={DEMO_MODE ? 'Preview data' : `${prospects.length} open`}>
      <div className="pipeline-widget-toolbar">
        <span><strong>{atRiskCount}</strong> at risk</span>
        <label><input type="checkbox" checked={atRiskOnly} onChange={(event) => setAtRiskOnly(event.target.checked)} /> At risk only</label>
      </div>
      {loading ? <p className="account-widget-empty">Loading pipeline…</p> : error ? <p className="account-widget-empty">Pipeline data is unavailable.</p> : (
        <div className="pipeline-widget-list">
          {visible.map((prospect) => (
            <div className="pipeline-widget-row" key={prospect.lead_id}>
              <button type="button" onClick={() => toggleWorked(prospect.lead_id)} aria-label={`Mark ${prospect.name} worked`} title="Mark worked"><span /></button>
              <div><strong>{prospect.name}</strong><span>{prospect.stage.replace(/^\d+\s*-\s*/, '')} · {prospect.advisor_name}</span></div>
              <div><strong>{currency(prospect.paum)}</strong><span>Score {prospect.score}{prospect.was_stale ? ' · At risk' : ''}</span></div>
            </div>
          ))}
          {!visible.length && <p className="account-widget-empty">No unworked prospects in this view.</p>}
        </div>
      )}
    </WidgetShell>
  );
}

function ExecutiveBriefWidgetContent() {
  const { ready, reconnect, mode, emails, markDone } = useInbox();
  const [show, setShow] = useState<'action' | 'important'>('action');
  const visible = useMemo(() => emails
    .filter((email) => !email.completed && (show === 'important' ? email.category === 'important' : ['needs_decision', 'needs_response'].includes(email.category)))
    .sort((a, b) => ({ critical: 4, high: 3, medium: 2, low: 1 }[b.priority] - { critical: 4, high: 3, medium: 2, low: 1 }[a.priority]))
    .slice(0, 3), [emails, show]);

  return (
    <WidgetShell eyebrow="Executive inbox" title="Executive Brief" href="/brief" status={mode === 'mock' ? 'Preview data' : `${visible.length} in view`}>
      <div className="account-widget-segment brief-widget-segment" role="group" aria-label="Inbox view">
        <button type="button" className={show === 'action' ? 'active' : ''} onClick={() => setShow('action')}>Needs action</button>
        <button type="button" className={show === 'important' ? 'active' : ''} onClick={() => setShow('important')}>Important</button>
      </div>
      {!ready ? <p className="account-widget-empty">Loading inbox…</p> : reconnect ? <p className="account-widget-empty">Reconnect Outlook in the full tool to view your inbox.</p> : (
        <div className="brief-widget-list">
          {visible.map((email) => (
            <div className="brief-widget-row" key={email.id}>
              <span className={`brief-widget-priority ${email.priority}`} aria-label={`${email.priority} priority`} />
              <div><strong>{email.subject}</strong><span>{email.senderName} · {email.request}</span></div>
              <button type="button" onClick={() => markDone(email.id)} aria-label={`Mark ${email.subject} done`}>Done</button>
            </div>
          ))}
          {!visible.length && <p className="account-widget-empty">Nothing waiting in this view.</p>}
        </div>
      )}
    </WidgetShell>
  );
}

function ExecutiveBriefWidget() {
  return <InboxProvider><ExecutiveBriefWidgetContent /></InboxProvider>;
}

interface CockpitHousehold {
  household_id: string;
  name: string;
  health_band: 'healthy' | 'watch' | 'at_risk';
  health_score?: number;
  open_alerts: number;
  open_tasks: number;
  drift_flagged: boolean;
}

const DEMO_COCKPIT: CockpitHousehold[] = [
  { household_id: 'hh-201', name: 'Evergreen Family', health_band: 'at_risk', health_score: 42, open_alerts: 2, open_tasks: 1, drift_flagged: true },
  { household_id: 'hh-202', name: 'Northstar Household', health_band: 'watch', health_score: 68, open_alerts: 1, open_tasks: 2, drift_flagged: false },
  { household_id: 'hh-203', name: 'Harbor Ridge Household', health_band: 'healthy', health_score: 91, open_alerts: 0, open_tasks: 1, drift_flagged: false },
];

function AvantosWidget() {
  const [households, setHouseholds] = useState<CockpitHousehold[]>(DEMO_MODE ? DEMO_COCKPIT : []);
  const [filter, setFilter] = useState<'all' | 'at_risk'>('all');
  const [loading, setLoading] = useState(!DEMO_MODE);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (DEMO_MODE) return;
    void fetch('/api/avantos/cockpit')
      .then(async (response) => {
        if (!response.ok) throw new Error('Cockpit unavailable');
        const payload = await response.json() as { households?: CockpitHousehold[] };
        setHouseholds(payload.households ?? []);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  const visible = households.filter((household) => filter === 'all' || household.health_band === 'at_risk').slice(0, 3);
  const atRisk = households.filter((household) => household.health_band === 'at_risk').length;
  return (
    <WidgetShell eyebrow="Advisor console" title="Avantos" href="/avantos" status={`${atRisk} at risk`}>
      <div className="account-widget-segment avantos-widget-segment" role="group" aria-label="Avantos household filter">
        <button type="button" className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>Priority book</button>
        <button type="button" className={filter === 'at_risk' ? 'active' : ''} onClick={() => setFilter('at_risk')}>At risk</button>
      </div>
      {loading ? <p className="account-widget-empty">Loading household health…</p> : error ? <p className="account-widget-empty">Avantos data is unavailable.</p> : (
        <div className="avantos-widget-list">
          {visible.map((household) => (
            <a key={household.household_id} href={`/planning?household=${encodeURIComponent(household.household_id)}`}>
              <span className={`avantos-health ${household.health_band}`} />
              <div><strong>{household.name}</strong><span>{household.open_alerts} alerts · {household.open_tasks} tasks{household.drift_flagged ? ' · Drift' : ''}</span></div>
              <b>{household.health_score ?? '—'}</b>
            </a>
          ))}
          {!visible.length && <p className="account-widget-empty">No households in this view.</p>}
        </div>
      )}
    </WidgetShell>
  );
}

export default function AccountToolWidgets({ enabled, accountLabel }: AccountToolWidgetsProps) {
  const count = Object.values(enabled).filter(Boolean).length;
  if (!count) return null;
  return (
    <section className="account-tools" aria-labelledby="account-tools-title">
      <div className="account-tools-heading">
        <div><p>Account dashboard</p><h2 id="account-tools-title">Work from here</h2></div>
        <span>{accountLabel}</span>
      </div>
      <div className="account-tools-grid">
        {enabled.performance && <PerformanceWidget />}
        {enabled.crm && <CrmWidget />}
        {enabled.fee_calculator && <FeeCalculatorWidget />}
        {enabled.pipeline_review && <PipelineWidget />}
        {enabled.brief && <ExecutiveBriefWidget />}
        {enabled.avantos && <AvantosWidget />}
      </div>
    </section>
  );
}
