// src/Crm.tsx
// CRM tool — a Wealthbox-style Client 360 in the Allworth glass theme.
// Stitches the Synapse warehouse (households, advisors, activities, pipeline)
// into two lenses: a CLIENT view (searchable book → contact record with an
// activity timeline + opportunities) and an ADVISOR view (roster → an advisor's
// book of business). Opportunities and activities open the shared right-side
// flyout. Data comes from services/crm (read-only /api/crm, demo data offline).

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Area,
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  crmApi,
  type ClientQuery,
  type CrmAccount,
  type CrmActivity,
  type CrmAdvisor,
  type CrmAllocationSlice,
  type CrmBook,
  type CrmClient,
  type CrmClientDetail,
  type CrmFilters,
  type CrmFlowPoint,
  type CrmOpportunity,
  type CrmPlanLink,
  type CrmPortfolio,
  type CrmTask,
} from './services/crm';
import { resolveUserEmail } from './services/auth';
import SideNav from './components/SideNav';
import ShareTool from './components/ShareTool';
import CrmFlyout, { type FlyoutField } from './components/CrmFlyout';
import './Crm.css';

// ── formatting helpers ───────────────────────────────────────────────────────

const usd0 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

const compactUsd = (n: number): string => {
  if (!n) return '$0';
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return usd0.format(n);
};

const initials = (name: string): string =>
  (name || '?')
    .replace(/[^A-Za-z0-9 &]/g, '')
    .split(/[ &]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join('') || '?';

const fmtDate = (v: string): string => (v ? v.slice(0, 10) : '');

// ── activity icon ─────────────────────────────────────────────────────────────

const activityIcon = (type: string) => {
  const t = (type || '').toLowerCase();
  const wrap = (path: React.ReactNode) => (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{path}</svg>
  );
  if (t.includes('call')) return wrap(<><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3 19.5 19.5 0 0 1-6-6 19.8 19.8 0 0 1-3-8.6A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8.1 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.5 2.8.6a2 2 0 0 1 1.7 2Z" /></>);
  if (t.includes('meeting') || t.includes('appointment') || t.includes('event')) return wrap(<><rect x="3" y="4" width="18" height="18" rx="2" /><path d="M16 2v4" /><path d="M8 2v4" /><path d="M3 10h18" /></>);
  if (t.includes('task')) return wrap(<><path d="M9 11l3 3L22 4" /><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" /></>);
  return wrap(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>);
};

// ── shared small pieces ───────────────────────────────────────────────────────

const StatusChip = ({ value }: { value: string }) => {
  const v = (value || '').toLowerCase();
  const tone = v.includes('active') || v.includes('client') ? 'ok'
    : v.includes('prospect') || v.includes('proposal') ? 'warn'
    : 'muted';
  return <span className={`crm-chip crm-chip-${tone}`}>{value || '—'}</span>;
};

const Avatar = ({ name, size = 'md' }: { name: string; size?: 'md' | 'lg' }) => (
  <div className={`crm-avatar crm-avatar-${size}`} aria-hidden>{initials(name)}</div>
);

// ── asset allocation panel (stacked bar + legend) ───────────────────────

const ALLOC_COLORS = ['#00205c', '#4a7bb8', '#c75b12', '#157a4c', '#8a94a8', '#6b4fa0', '#b3894a', '#3d8f8f', '#c4c9d4'];

function AllocationPanel({ allocation, title, asOf }: { allocation: CrmAllocationSlice[]; title: string; asOf?: string | null }) {
  if (allocation.length === 0) return null;
  return (
    <div className="crm-book-panel">
      <div className="crm-section-label">{title}{asOf ? ` · as of ${asOf}` : ''}</div>
      <div className="crm-alloc-bar">
        {allocation.map((s, i) => (
          <div
            key={s.label}
            className="crm-alloc-seg"
            style={{ width: `${Math.max(1.5, s.pct)}%`, background: ALLOC_COLORS[i % ALLOC_COLORS.length] }}
            title={`${s.label} · ${s.pct}%`}
          />
        ))}
      </div>
      <div className="crm-alloc-legend">
        {allocation.map((s, i) => (
          <div key={s.label} className="crm-alloc-row">
            <span className="crm-alloc-swatch" style={{ background: ALLOC_COLORS[i % ALLOC_COLORS.length] }} />
            <span className="crm-alloc-label">{s.label}</span>
            <span className="crm-alloc-pct">{s.pct}%</span>
            <span className="crm-alloc-value">{compactUsd(s.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── monthly performance chart (MTD % bars + cumulative line) ───────────────

function PerformanceChart({ performance }: { performance: { period: string; mtd_pct: number }[] }) {
  const data = useMemo(() => {
    let cum = 1;
    return performance.map((p) => {
      cum *= 1 + p.mtd_pct / 100;
      return { ...p, label: monthLabel(p.period), cum_pct: Number(((cum - 1) * 100).toFixed(2)) };
    });
  }, [performance]);
  if (data.length === 0) return null;
  const trailing = data[data.length - 1].cum_pct;
  return (
    <div className="crm-chart-card">
      <div className="crm-section-label">
        Performance · monthly return & cumulative ({trailing >= 0 ? '+' : ''}{trailing}% trailing)
      </div>
      <ResponsiveContainer width="100%" height={210}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="rgba(0,32,92,0.07)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#8a94a8' }} tickLine={false} axisLine={false} />
          <YAxis tickFormatter={(v: number) => `${v}%`} tick={{ fontSize: 11, fill: '#8a94a8' }} tickLine={false} axisLine={false} width={48} />
          <Tooltip
            formatter={(value, key) => [`${Number(value ?? 0).toFixed(2)}%`, key === 'mtd_pct' ? 'Monthly' : 'Cumulative']}
            contentStyle={{ borderRadius: 10, border: '1px solid rgba(0,32,92,0.12)', fontSize: 12 }}
          />
          <Bar dataKey="mtd_pct" radius={[3, 3, 0, 0]} maxBarSize={16}>
            {data.map((p) => (
              <Cell key={p.period} fill={p.mtd_pct >= 0 ? '#157a4c' : '#b3261e'} />
            ))}
          </Bar>
          <Line type="monotone" dataKey="cum_pct" stroke="#00205c" strokeWidth={2} dot={false} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── AUM + net-flows chart (shared by client portfolio + advisor book) ───────

const monthLabel = (period: string): string => {
  const [y, m] = period.split('-');
  const names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${names[(Number(m) || 1) - 1]} ${(y || '').slice(2)}`;
};

function FlowsChart({ flows, title }: { flows: CrmFlowPoint[]; title: string }) {
  const data = useMemo(
    () => flows.map((f) => ({ ...f, label: monthLabel(f.period) })),
    [flows],
  );
  if (data.length === 0) return <div className="crm-empty">No rollforward history.</div>;
  return (
    <div className="crm-chart-card">
      <div className="crm-section-label">{title}</div>
      <ResponsiveContainer width="100%" height={230}>
        <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="rgba(0,32,92,0.07)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#8a94a8' }} tickLine={false} axisLine={false} />
          <YAxis yAxisId="aum" tickFormatter={(v: number) => compactUsd(v)} tick={{ fontSize: 11, fill: '#8a94a8' }} tickLine={false} axisLine={false} width={62} />
          <YAxis yAxisId="flow" orientation="right" tickFormatter={(v: number) => compactUsd(v)} tick={{ fontSize: 11, fill: '#8a94a8' }} tickLine={false} axisLine={false} width={62} />
          <Tooltip
            formatter={(value, key) => [
              compactUsd(Number(value ?? 0)),
              key === 'total_value' ? 'AUM' : 'Net flows',
            ]}
            contentStyle={{ borderRadius: 10, border: '1px solid rgba(0,32,92,0.12)', fontSize: 12 }}
          />
          <Area yAxisId="aum" type="monotone" dataKey="total_value" stroke="#00205c" strokeWidth={2} fill="rgba(0,32,92,0.08)" />
          <Bar yAxisId="flow" dataKey="ncnm" fill="#c75b12" radius={[3, 3, 0, 0]} maxBarSize={16} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── client record ─────────────────────────────────────────────────────────────

type RecordTab = 'activity' | 'portfolio' | 'opportunities' | 'details';

function ClientRecord({ leadId, onOpenAdvisor }: { leadId: string; onOpenAdvisor: (id: string) => void }) {
  const [client, setClient] = useState<CrmClientDetail | null>(null);
  const [activities, setActivities] = useState<CrmActivity[]>([]);
  const [opps, setOpps] = useState<CrmOpportunity[]>([]);
  const [accounts, setAccounts] = useState<CrmAccount[]>([]);
  const [flows, setFlows] = useState<CrmFlowPoint[]>([]);
  const [portfolio, setPortfolio] = useState<CrmPortfolio | null>(null);
  const [plan, setPlan] = useState<CrmPlanLink | null>(null);
  const [tab, setTab] = useState<RecordTab>('activity');
  const [error, setError] = useState<string | null>(null);
  const [flyoutOpp, setFlyoutOpp] = useState<CrmOpportunity | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setError(null);
    setClient(null);
    setPlan(null);
    setPortfolio(null);
    Promise.all([
      crmApi.getClient(leadId, ctrl.signal),
      crmApi.getClientActivities(leadId, ctrl.signal),
      crmApi.getClientOpportunities(leadId, ctrl.signal),
      crmApi.getClientAccounts(leadId, ctrl.signal),
      crmApi.getClientFlows(leadId, ctrl.signal),
    ])
      .then(([c, a, o, ac, fl]) => {
        setClient(c);
        setActivities(a);
        setOpps(o);
        setAccounts(ac);
        setFlows(fl);
        // Cross-app: look up this household's financial plan by name.
        crmApi.findPlan(c.name, ctrl.signal)
          .then((p) => { if (!ctrl.signal.aborted) setPlan(p); })
          .catch(() => { if (!ctrl.signal.aborted) setPlan(null); });
        // Portfolio analytics load after the record so the page paints fast.
        crmApi.getClientPortfolio(leadId, ctrl.signal)
          .then((p) => { if (!ctrl.signal.aborted) setPortfolio(p); })
          .catch(() => { if (!ctrl.signal.aborted) setPortfolio(null); });
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Failed to load client');
      });
    return () => ctrl.abort();
  }, [leadId]);

  if (error) return <div className="crm-error">{error}</div>;
  if (!client) return <div className="crm-empty">Loading client…</div>;

  const totalCash = accounts.reduce((s, a) => s + a.current_cash, 0);
  const rmdDue = accounts.filter((a) => a.rmd_satisfied === 'No' && a.rmd_total > 0);
  const latest = flows.length ? flows[flows.length - 1] : null;
  const trailingNcnm = flows.slice(-12).reduce((s, f) => s + f.ncnm, 0);

  const oppFields = (o: CrmOpportunity): FlyoutField[] => [
    { label: 'Amount (PAUM)', value: compactUsd(o.paum) },
    { label: 'Stage', value: <StatusChip value={o.stage} /> },
    { label: 'Days in stage', value: o.days_in_stage },
    { label: 'Score', value: o.score },
    { label: 'Channel', value: o.channel || '—' },
    { label: 'Assigned to', value: o.advisor_name || '—' },
    { label: 'Region', value: o.region || '—' },
    { label: 'Expected close', value: fmtDate(o.expected_close_date) || '—' },
    { label: 'Last activity', value: fmtDate(o.last_activity_date) || '—' },
    { label: 'Next activity', value: fmtDate(o.next_activity_date) || '—' },
  ];

  return (
    <div className="crm-record">
      <div className="crm-record-header">
        <Avatar name={client.name} size="lg" />
        <div className="crm-record-headmain">
          <h2 className="crm-record-name">{client.name}</h2>
          {client.job_title && <div className="crm-record-sub">{client.job_title}</div>}
          <div className="crm-record-tags">
            <StatusChip value={client.hh_status} />
            {client.segment && <span className="crm-chip crm-chip-muted">{client.segment}</span>}
            {client.channel && <span className="crm-chip crm-chip-muted">{client.channel}</span>}
            {client.advisor_name && (
              <button type="button" className="crm-chip crm-chip-link" onClick={() => onOpenAdvisor(client.advisor_id)}>
                {client.advisor_name}
              </button>
            )}
          </div>
          <div className="crm-record-links">
            {plan ? (
              <a className="crm-applink" href="/planning">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" /></svg>
                Financial plan: {plan.name}
              </a>
            ) : (
              <a className="crm-applink crm-applink-muted" href="/planning">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="9" /><path d="M12 8v8" /><path d="M8 12h8" /></svg>
                No plan yet — create in Planning
              </a>
            )}
            {opps.length > 0 && (
              <a className="crm-applink" href="/pipeline-review">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 3v18h18" /><path d="m7 14 4-4 3 3 5-6" /></svg>
                In pipeline ({opps.length})
              </a>
            )}
            {client.sf_url && (
              <a className="crm-applink" href={client.sf_url} target="_blank" rel="noreferrer">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M7 17 17 7" /><path d="M8 7h9v9" /></svg>
                Salesforce
              </a>
            )}
          </div>
        </div>
        <div className="crm-record-aum">
          <div className="crm-record-aum-value">{compactUsd(latest?.total_value || client.aum)}</div>
          <div className="crm-record-aum-label">Assets under management</div>
          {flows.length > 0 && (
            <div className={`crm-record-flow ${trailingNcnm >= 0 ? 'up' : 'down'}`}>
              {trailingNcnm >= 0 ? '▲' : '▼'} {compactUsd(Math.abs(trailingNcnm))} net flows · 12 mo
            </div>
          )}
        </div>
      </div>

      <div className="crm-record-tabs">
        {(['activity', 'portfolio', 'opportunities', 'details'] as RecordTab[]).map((t) => (
          <button key={t} type="button" className={`crm-tab${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}>
            {t === 'activity' ? 'Activity'
              : t === 'portfolio' ? `Portfolio${accounts.length ? ` (${accounts.length})` : ''}`
              : t === 'opportunities' ? `Opportunities${opps.length ? ` (${opps.length})` : ''}`
              : 'Details'}
          </button>
        ))}
      </div>

      {tab === 'activity' && (
        <div className="crm-feed">
          {activities.length === 0 && <div className="crm-empty">No activity recorded.</div>}
          {activities.map((a) => (
            <div key={a.id} className="crm-feed-item">
              <div className={`crm-feed-icon${a.status?.toLowerCase() === 'completed' ? ' done' : ''}`}>{activityIcon(a.activity_type)}</div>
              <div className="crm-feed-body">
                <div className="crm-feed-subject">{a.subject || a.activity_type || 'Activity'}</div>
                <div className="crm-feed-meta">
                  <span className="crm-feed-type">{a.activity_type || 'activity'}</span>
                  {a.owner_name && <span>· {a.owner_name}</span>}
                  {a.status && <span>· {a.status}</span>}
                  {a.call_disposition && <span>· {a.call_disposition}</span>}
                </div>
              </div>
              <div className="crm-feed-time">{fmtDate(a.created)}</div>
            </div>
          ))}
        </div>
      )}

      {tab === 'portfolio' && (
        <div className="crm-portfolio">
          <div className="crm-ministats">
            <div className="crm-ministat">
              <div className="crm-ministat-value">{compactUsd(latest?.total_value || client.aum)}</div>
              <div className="crm-ministat-label">Total value</div>
            </div>
            <div className="crm-ministat">
              <div className="crm-ministat-value">{compactUsd(totalCash)}</div>
              <div className="crm-ministat-label">Cash</div>
            </div>
            <div className="crm-ministat">
              <div className={`crm-ministat-value ${trailingNcnm >= 0 ? 'pos' : 'neg'}`}>{compactUsd(trailingNcnm)}</div>
              <div className="crm-ministat-label">Net flows · 12 mo</div>
            </div>
            <div className="crm-ministat">
              <div className={`crm-ministat-value${rmdDue.length ? ' neg' : ''}`}>
                {rmdDue.length ? compactUsd(rmdDue.reduce((s, a) => s + a.rmd_total, 0)) : '—'}
              </div>
              <div className="crm-ministat-label">RMD outstanding</div>
            </div>
            {portfolio && (
              <>
                <div className="crm-ministat">
                  <div className={`crm-ministat-value${portfolio.ytd_pct != null ? (portfolio.ytd_pct >= 0 ? ' pos' : ' neg') : ''}`}>
                    {portfolio.ytd_pct != null ? `${portfolio.ytd_pct >= 0 ? '+' : ''}${portfolio.ytd_pct.toFixed(2)}%` : '—'}
                  </div>
                  <div className="crm-ministat-label">YTD return (TWR)</div>
                </div>
                <div className="crm-ministat">
                  <div className="crm-ministat-value">{portfolio.beta ? portfolio.beta.toFixed(2) : '—'}</div>
                  <div className="crm-ministat-label">Beta</div>
                </div>
                <div className="crm-ministat">
                  <div className="crm-ministat-value">{portfolio.duration ? portfolio.duration.toFixed(1) : '—'}</div>
                  <div className="crm-ministat-label">Duration</div>
                </div>
                <div className="crm-ministat">
                  <div className="crm-ministat-value">{portfolio.yield_pct ? `${portfolio.yield_pct.toFixed(2)}%` : '—'}</div>
                  <div className="crm-ministat-label">Weighted yield</div>
                </div>
              </>
            )}
          </div>

          {portfolio && (
            <div className="crm-portfolio-grid">
              <AllocationPanel allocation={portfolio.allocation} title="Asset allocation" asOf={portfolio.as_of} />
              <PerformanceChart performance={portfolio.performance} />
            </div>
          )}

          <FlowsChart flows={flows} title="AUM & net flows (Tamarac rollforward)" />

          {portfolio && portfolio.holdings.length > 0 && (
            <>
              <div className="crm-section-label">Top holdings</div>
              <div className="crm-table-wrap crm-holdings">
                <table className="crm-table">
                  <thead>
                    <tr><th>Symbol</th><th>Custodian</th><th className="num">Market value</th><th className="num">Cost basis</th><th className="num">Unrealized G/L</th></tr>
                  </thead>
                  <tbody>
                    {portfolio.holdings.map((h) => (
                      <tr key={`${h.symbol}-${h.custodian}`}>
                        <td><span className="crm-cell-name">{h.symbol}</span></td>
                        <td>{h.custodian || '—'}</td>
                        <td className="num">{compactUsd(h.market_value)}</td>
                        <td className="num">{compactUsd(h.cost_basis)}</td>
                        <td className={`num crm-gl ${h.unrealized >= 0 ? 'pos' : 'neg'}`}>
                          {h.unrealized >= 0 ? '+' : ''}{compactUsd(h.unrealized)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <div className="crm-section-label">Accounts (Tamarac)</div>
          {accounts.length === 0 ? (
            <div className="crm-empty">No managed accounts linked to this household.</div>
          ) : (
            <div className="crm-table-wrap">
              <table className="crm-table">
                <thead>
                  <tr><th>Account</th><th>Type</th><th>Custodian</th><th>Taxable</th><th className="num">Cash</th><th className="num">RMD due</th><th className="num">Value</th></tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.account_id}>
                      <td><div className="crm-cell-name">{a.account_name || '—'}</div></td>
                      <td>{a.account_type || a.master_category || '—'}</td>
                      <td>{a.custodian || '—'}</td>
                      <td>{a.taxable || '—'}</td>
                      <td className="num">{compactUsd(a.current_cash)}</td>
                      <td className="num">
                        {a.rmd_satisfied === 'No' && a.rmd_total > 0
                          ? <span className="crm-chip crm-chip-warn">{compactUsd(a.rmd_total)}</span>
                          : '—'}
                      </td>
                      <td className="num">{compactUsd(a.total_value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'opportunities' && (
        <div className="crm-oppgrid">
          {opps.length === 0 && <div className="crm-empty">No open opportunities.</div>}
          {opps.map((o) => (
            <button key={`${o.lead_id}-${o.stage}`} type="button" className="crm-oppcard" onClick={() => setFlyoutOpp(o)}>
              <div className="crm-oppcard-top">
                <span className="crm-oppcard-amount">{compactUsd(o.paum)}</span>
                <StatusChip value={o.stage} />
              </div>
              <div className="crm-oppcard-meta">{o.days_in_stage} days in stage · score {o.score}</div>
            </button>
          ))}
        </div>
      )}

      {tab === 'details' && (
        <div className="crm-details">
          {[
            ['Email', client.email],
            ['Phone', client.phone],
            ['Address', [client.address, client.state, client.zip].filter(Boolean).join(', ')],
            ['Segment', client.segment],
            ['Channel', client.channel],
            ['Stage', client.stage],
            ['Primary advisor', client.advisor_name],
            ['Managed assets', compactUsd(client.aum)],
            ['Billed assets', compactUsd(client.aum_billed)],
            ['Household ID', client.hhid],
            ['Lead ID', client.lead_id],
          ].map(([label, value]) => (
            <div key={label} className="crm-detail">
              <div className="crm-detail-label">{label}</div>
              <div className="crm-detail-value">{value || '—'}</div>
            </div>
          ))}
        </div>
      )}

      <CrmFlyout
        open={!!flyoutOpp}
        kicker="Opportunity"
        title={flyoutOpp?.name || ''}
        fields={flyoutOpp ? oppFields(flyoutOpp) : []}
        linkHref={flyoutOpp?.sf_url || undefined}
        onClose={() => setFlyoutOpp(null)}
      />
    </div>
  );
}

// ── clients view ──────────────────────────────────────────────────────────────

function ClientsView({ onOpen, advisor, initialQuery }: { onOpen: (leadId: string) => void; advisor?: string; initialQuery?: string }) {
  const [clients, setClients] = useState<CrmClient[]>([]);
  const [filters, setFilters] = useState<CrmFilters | null>(null);
  const [query, setQuery] = useState<ClientQuery>(initialQuery ? { q: initialQuery } : {});
  const [search, setSearch] = useState(initialQuery ?? '');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    crmApi.getFilters().then(setFilters).catch(() => setFilters(null));
  }, []);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    crmApi
      .getClients({ ...query, advisor: advisor || query.advisor }, ctrl.signal)
      .then((c) => setClients(c))
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Failed to load clients');
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [query, advisor]);

  const runSearch = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    setQuery((q) => ({ ...q, q: search.trim() || undefined }));
  }, [search]);

  return (
    <div className="crm-list-view">
      <form className="crm-toolbar" onSubmit={runSearch}>
        <input
          type="text"
          placeholder="Search clients by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select value={query.segment ?? ''} onChange={(e) => setQuery((q) => ({ ...q, segment: e.target.value || undefined }))}>
          <option value="">All segments</option>
          {filters?.segments.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={query.status ?? ''} onChange={(e) => setQuery((q) => ({ ...q, status: e.target.value || undefined }))}>
          <option value="">All statuses</option>
          {filters?.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button type="submit" className="crm-btn">Search</button>
      </form>

      {error && <div className="crm-error">{error}</div>}
      {loading ? (
        <div className="crm-empty">Loading clients…</div>
      ) : clients.length === 0 ? (
        <div className="crm-empty">No clients match your search.</div>
      ) : (
        <div className="crm-table-wrap">
          <table className="crm-table">
            <thead>
              <tr>
                <th>Client</th><th>Status</th><th>Segment</th><th>Channel</th>{!advisor && <th>Advisor</th>}<th className="num">AUM</th>
              </tr>
            </thead>
            <tbody>
              {clients.map((c) => (
                <tr key={c.lead_id} onClick={() => onOpen(c.lead_id)}>
                  <td>
                    <div className="crm-cell-client">
                      <Avatar name={c.name} />
                      <div>
                        <div className="crm-cell-name">{c.name}</div>
                        {c.state && <div className="crm-cell-sub">{c.state}</div>}
                      </div>
                    </div>
                  </td>
                  <td><StatusChip value={c.hh_status} /></td>
                  <td>{c.segment || '—'}</td>
                  <td>{c.channel || '—'}</td>
                  {!advisor && <td>{c.advisor_name || '—'}</td>}
                  <td className="num">{compactUsd(c.aum)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── book picker (choose whose book to open) ──────────────────────────────

function AdvisorsView({ advisors, onOpen }: { advisors: CrmAdvisor[]; onOpen: (a: CrmAdvisor) => void }) {
  const [search, setSearch] = useState('');

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const base = needle
      ? advisors.filter((a) =>
          a.name.toLowerCase().includes(needle) ||
          a.email.toLowerCase().includes(needle) ||
          a.region.toLowerCase().includes(needle))
      : advisors;
    return base.slice(0, 60); // grid stays scannable; search narrows the rest
  }, [advisors, search]);

  return (
    <div className="crm-list-view">
      <div className="crm-toolbar">
        <input
          type="text"
          placeholder="Search advisors by name, email, or region…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          autoFocus
        />
        <span className="crm-hero-sub">{advisors.length.toLocaleString()} advisors</span>
      </div>
      {visible.length === 0 ? (
        <div className="crm-empty">No advisors match your search.</div>
      ) : (
        <div className="crm-advisor-grid">
          {visible.map((a) => (
            <button key={a.advisor_id} type="button" className="crm-advisor-card" onClick={() => onOpen(a)}>
              <Avatar name={a.name} size="lg" />
              <div className="crm-advisor-name">{a.name}</div>
              {a.title && <div className="crm-advisor-title">{a.title}</div>}
              {a.region && <div className="crm-advisor-region">{a.region}</div>}
              <div className="crm-advisor-stats">
                <div><span className="crm-advisor-stat">{a.client_count}</span><span className="crm-advisor-statlabel">clients</span></div>
                <div><span className="crm-advisor-stat">{compactUsd(a.total_aum)}</span><span className="crm-advisor-statlabel">AUM</span></div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── book dashboard (the advisor's landing view) ────────────────────────

function BookDashboard({ userId, onOpenClient }: { userId: string; onOpenClient: (leadId: string) => void }) {
  const [advisor, setAdvisor] = useState<CrmAdvisor | null>(null);
  const [clients, setClients] = useState<CrmClient[]>([]);
  const [book, setBook] = useState<CrmBook | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flyoutOpp, setFlyoutOpp] = useState<CrmOpportunity | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setAdvisor(null);
    setBook(null);
    Promise.all([
      crmApi.getAdvisor(userId, ctrl.signal),
      crmApi.getAdvisorBook(userId, ctrl.signal).catch(() => null),
    ])
      .then(([d, b]) => {
        setAdvisor(d.advisor);
        setClients(d.clients);
        setBook(b);
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Failed to load advisor');
      });
    return () => ctrl.abort();
  }, [userId]);

  if (error) return <div className="crm-error">{error}</div>;
  if (!advisor) return <div className="crm-empty">Loading advisor…</div>;

  const trailingNcnm = book ? book.flows.slice(-12).reduce((s, f) => s + f.ncnm, 0) : 0;
  const pipelinePaum = book ? book.pipeline.reduce((s, o) => s + o.paum, 0) : 0;

  const oppFields = (o: CrmOpportunity): FlyoutField[] => [
    { label: 'Amount (PAUM)', value: compactUsd(o.paum) },
    { label: 'Stage', value: <StatusChip value={o.stage} /> },
    { label: 'Days in stage', value: o.days_in_stage },
    { label: 'Score', value: o.score },
    { label: 'Expected close', value: fmtDate(o.expected_close_date) || '—' },
    { label: 'Next activity', value: fmtDate(o.next_activity_date) || '—' },
  ];

  return (
    <div className="crm-record">
      {book && (
        <>
          <div className="crm-ministats">
            <div className="crm-ministat">
              <div className="crm-ministat-value">{compactUsd(advisor.total_aum)}</div>
              <div className="crm-ministat-label">Book AUM · {advisor.client_count} clients</div>
            </div>
            <div className="crm-ministat">
              <div className={`crm-ministat-value ${trailingNcnm >= 0 ? 'pos' : 'neg'}`}>{compactUsd(trailingNcnm)}</div>
              <div className="crm-ministat-label">Net flows · 12 mo</div>
            </div>
            <div className="crm-ministat">
              <div className="crm-ministat-value">{compactUsd(pipelinePaum)}</div>
              <div className="crm-ministat-label">Pipeline PAUM · {book.pipeline.length} opps</div>
            </div>
            <div className="crm-ministat">
              <div className={`crm-ministat-value${book.rmds.count ? ' neg' : ''}`}>
                {book.rmds.count ? compactUsd(book.rmds.total) : '—'}
              </div>
              <div className="crm-ministat-label">RMDs outstanding · {book.rmds.count}</div>
            </div>
            <div className="crm-ministat">
              <div className={`crm-ministat-value${book.needs_attention.length ? ' neg' : ''}`}>{book.needs_attention.length}</div>
              <div className="crm-ministat-label">Need attention (90d)</div>
            </div>
            <div className="crm-ministat">
              <div className="crm-ministat-value">{book.open_tasks}</div>
              <div className="crm-ministat-label">Open tasks</div>
            </div>
          </div>

          <FlowsChart flows={book.flows} title="Book AUM & net flows (Tamarac rollforward)" />

          <div className="crm-book-grid">
            <AllocationPanel allocation={book.allocation} title="Book asset allocation" />
            <div className="crm-book-panel">
              <div className="crm-section-label">Needs attention — no contact in 90 days</div>
              {book.needs_attention.length === 0 ? (
                <div className="crm-empty">Every client has recent contact. 🎉</div>
              ) : (
                <div className="crm-attention-list">
                  {book.needs_attention.map((n) => (
                    <button key={n.lead_id} type="button" className="crm-attention-item" onClick={() => onOpenClient(n.lead_id)}>
                      <Avatar name={n.name} />
                      <div className="crm-attention-body">
                        <div className="crm-cell-name">{n.name}</div>
                        <div className="crm-cell-sub">
                          {n.last_activity ? `Last contact ${n.last_activity}` : 'No contact recorded'}
                        </div>
                      </div>
                      <div className="crm-attention-aum">{compactUsd(n.aum)}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="crm-book-panel">
              <div className="crm-section-label">Segment mix</div>
              {book.segments.length === 0 ? (
                <div className="crm-empty">No segment data.</div>
              ) : (
                <div className="crm-segment-list">
                  {book.segments.map((s) => {
                    const maxAum = Math.max(...book.segments.map((x) => x.aum), 1);
                    return (
                      <div key={s.segment} className="crm-segment-row">
                        <div className="crm-segment-head">
                          <span className="crm-cell-name">{s.segment}</span>
                          <span className="crm-cell-sub">{s.clients} clients · {compactUsd(s.aum)}</span>
                        </div>
                        <div className="crm-segment-bar">
                          <div className="crm-segment-fill" style={{ width: `${Math.max(4, (s.aum / maxAum) * 100)}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div className="crm-book-panel">
              <div className="crm-section-label">Open pipeline</div>
              {book.pipeline.length === 0 ? (
                <div className="crm-empty">No open opportunities. <a className="crm-applink" href="/pipeline-review">Pipeline Review</a></div>
              ) : (
                <div className="crm-attention-list">
                  {book.pipeline.map((o) => (
                    <button key={`${o.lead_id}-${o.stage}`} type="button" className="crm-attention-item" onClick={() => setFlyoutOpp(o)}>
                      <div className="crm-attention-body">
                        <div className="crm-cell-name">{o.name}</div>
                        <div className="crm-cell-sub">{o.stage} · {o.days_in_stage} days · score {o.score}</div>
                      </div>
                      <div className="crm-attention-aum">{compactUsd(o.paum)}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="crm-book-panel">
              <div className="crm-section-label">Outstanding RMDs</div>
              {book.rmds.items.length === 0 ? (
                <div className="crm-empty">All RMDs satisfied.</div>
              ) : (
                <div className="crm-attention-list">
                  {book.rmds.items.map((r) => (
                    <button key={`${r.lead_id}-${r.account_name}`} type="button" className="crm-attention-item" onClick={() => r.lead_id && onOpenClient(r.lead_id)}>
                      <div className="crm-attention-body">
                        <div className="crm-cell-name">{r.client_name}</div>
                        <div className="crm-cell-sub">{r.account_name}</div>
                      </div>
                      <div className="crm-attention-aum neg">{compactUsd(r.amount)}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      <div className="crm-section-label">Clients</div>
      <div className="crm-table-wrap">
        <table className="crm-table">
          <thead>
            <tr><th>Client</th><th>Status</th><th>Segment</th><th className="num">AUM</th></tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.lead_id} onClick={() => onOpenClient(c.lead_id)}>
                <td>
                  <div className="crm-cell-client">
                    <Avatar name={c.name} />
                    <div className="crm-cell-name">{c.name}</div>
                  </div>
                </td>
                <td><StatusChip value={c.hh_status} /></td>
                <td>{c.segment || '—'}</td>
                <td className="num">{compactUsd(c.aum)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <CrmFlyout
        open={!!flyoutOpp}
        kicker="Opportunity"
        title={flyoutOpp?.name || ''}
        fields={flyoutOpp ? oppFields(flyoutOpp) : []}
        linkHref={flyoutOpp?.sf_url || undefined}
        onClose={() => setFlyoutOpp(null)}
      />
    </div>
  );
}

// ── pipeline view ─────────────────────────────────────────────────────────────

function PipelineView({ onOpenClient, advisorName }: { onOpenClient: (leadId: string) => void; advisorName?: string }) {
  const [opps, setOpps] = useState<CrmOpportunity[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [flyoutOpp, setFlyoutOpp] = useState<CrmOpportunity | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    crmApi
      .getOpportunities(ctrl.signal)
      .then((all) => setOpps(advisorName ? all.filter((o) => o.advisor_name === advisorName) : all))
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Failed to load pipeline');
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [advisorName]);

  const fields = (o: CrmOpportunity): FlyoutField[] => [
    { label: 'Amount (PAUM)', value: compactUsd(o.paum) },
    { label: 'Stage', value: <StatusChip value={o.stage} /> },
    { label: 'Days in stage', value: o.days_in_stage },
    { label: 'Score', value: o.score },
    { label: 'Channel', value: o.channel || '—' },
    { label: 'Assigned to', value: o.advisor_name || '—' },
    { label: 'Region', value: o.region || '—' },
    { label: 'Expected close', value: fmtDate(o.expected_close_date) || '—' },
  ];

  if (error) return <div className="crm-error">{error}</div>;
  if (loading) return <div className="crm-empty">Loading pipeline…</div>;

  return (
    <div className="crm-list-view">
      <div className="crm-table-wrap">
        <table className="crm-table">
          <thead>
            <tr><th>Opportunity</th><th>Stage</th><th className="num">PAUM</th><th className="num">Score</th><th>Advisor</th><th /></tr>
          </thead>
          <tbody>
            {opps.map((o) => (
              <tr key={`${o.lead_id}-${o.stage}`}>
                <td>
                  <button type="button" className="crm-linktext" onClick={() => onOpenClient(o.lead_id)}>{o.name}</button>
                </td>
                <td><StatusChip value={o.stage} /></td>
                <td className="num">{compactUsd(o.paum)}</td>
                <td className="num">{o.score}</td>
                <td>{o.advisor_name || '—'}</td>
                <td><button type="button" className="crm-btn crm-btn-ghost" onClick={() => setFlyoutOpp(o)}>Details</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <CrmFlyout
        open={!!flyoutOpp}
        kicker="Opportunity"
        title={flyoutOpp?.name || ''}
        fields={flyoutOpp ? fields(flyoutOpp) : []}
        linkHref={flyoutOpp?.sf_url || undefined}
        onClose={() => setFlyoutOpp(null)}
      />
    </div>
  );
}

// ── tasks view ────────────────────────────────────────────────────────────────

function TasksView({ onOpenClient, owner }: { onOpenClient: (leadId: string) => void; owner?: string }) {
  const [tasks, setTasks] = useState<CrmTask[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ctrl = new AbortController();
    crmApi
      .getTasks(owner, ctrl.signal)
      .then(setTasks)
      .catch((e) => {
        if (!ctrl.signal.aborted) setError(e instanceof Error ? e.message : 'Failed to load tasks');
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [owner]);

  if (error) return <div className="crm-error">{error}</div>;
  if (loading) return <div className="crm-empty">Loading tasks…</div>;
  if (tasks.length === 0) return <div className="crm-empty">No open tasks.</div>;

  return (
    <div className="crm-list-view">
      <div className="crm-table-wrap">
        <table className="crm-table">
          <thead>
            <tr><th>Task</th><th>Client</th><th>Owner</th><th>Status</th><th>Created</th></tr>
          </thead>
          <tbody>
            {tasks.map((t) => (
              <tr key={t.id}>
                <td>{t.subject || '—'}</td>
                <td>
                  {t.lead_id ? (
                    <button type="button" className="crm-linktext" onClick={() => onOpenClient(t.lead_id)}>{t.client_name || t.lead_id}</button>
                  ) : (t.client_name || '—')}
                </td>
                <td>{t.owner_name || '—'}</td>
                <td><StatusChip value={t.status || 'Open'} /></td>
                <td>{fmtDate(t.created)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── container ─────────────────────────────────────────────────────────────────

type View =
  | { section: 'dashboard' }
  | { section: 'clients' }
  | { section: 'client'; leadId: string }
  | { section: 'pipeline' }
  | { section: 'tasks' };

type Section = 'dashboard' | 'clients' | 'pipeline' | 'tasks';

const SECTION_LABELS: Record<Section, string> = {
  dashboard: 'Dashboard',
  clients: 'Clients',
  pipeline: 'Pipeline',
  tasks: 'Tasks',
};

const ADVISOR_KEY = 'allworth-crm-advisor';

// Deep-link support: /crm?client=<leadId> opens a Client 360 directly;
// /crm?q=<name> opens Clients pre-filtered (used by the Avantos cockpit).
function initialViewFromUrl(): { view: View; clientQuery?: string } {
  try {
    const params = new URLSearchParams(window.location.search);
    const client = params.get('client');
    if (client) return { view: { section: 'client', leadId: client } };
    const q = params.get('q');
    if (q) return { view: { section: 'clients' }, clientQuery: q };
  } catch { /* ignore */ }
  return { view: { section: 'dashboard' } };
}

const Crm = () => {
  const [advisors, setAdvisors] = useState<CrmAdvisor[] | null>(null);
  const [ctx, setCtx] = useState<CrmAdvisor | null>(null);
  const [picking, setPicking] = useState(false);
  const [initial] = useState(initialViewFromUrl);
  const [view, setView] = useState<View>(initial.view);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Resolve the advisor context: saved selection → signed-in email match → picker.
  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([
      crmApi.getAdvisors(ctrl.signal),
      resolveUserEmail().catch(() => null),
    ])
      .then(([all, email]) => {
        setAdvisors(all);
        let saved: string | null = null;
        try { saved = localStorage.getItem(ADVISOR_KEY); } catch { /* ignore */ }
        const found =
          (saved && all.find((a) => a.advisor_id === saved)) ||
          (email && all.find((a) => a.email.toLowerCase() === email.toLowerCase())) ||
          null;
        setCtx(found || null);
        if (!found) setPicking(true);
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) setLoadError(e instanceof Error ? e.message : 'Failed to load advisors');
      });
    return () => ctrl.abort();
  }, []);

  const selectAdvisor = (a: CrmAdvisor) => {
    setCtx(a);
    setPicking(false);
    setView({ section: 'dashboard' });
    try { localStorage.setItem(ADVISOR_KEY, a.advisor_id); } catch { /* ignore */ }
  };

  const switchToAdvisorById = (id: string) => {
    const a = advisors?.find((x) => x.advisor_id === id);
    if (a) selectAdvisor(a);
  };

  const openClient = (leadId: string) => setView({ section: 'client', leadId });
  const activeSection: Section = view.section === 'client' ? 'clients' : view.section;

  return (
    <div className="crm-page has-sidenav">
      <SideNav />
      <div className="crm-shell">
        <header className="crm-hero">
          {ctx && !picking ? (
            <div className="crm-hero-advisor">
              <Avatar name={ctx.name} size="lg" />
              <div>
                <div className="crm-kicker">Advisor workspace</div>
                <h1 className="crm-title">{ctx.name}</h1>
                <div className="crm-hero-sub">
                  {[ctx.title, ctx.region, `${ctx.client_count.toLocaleString()} clients`, compactUsd(ctx.total_aum)]
                    .filter(Boolean).join(' · ')}
                </div>
              </div>
            </div>
          ) : (
            <div>
              <div className="crm-kicker">Advisor workspace</div>
              <h1 className="crm-title">CRM</h1>
              <div className="crm-hero-sub">Choose a book of business to open.</div>
            </div>
          )}
          <div className="crm-hero-actions">
            {ctx && !picking && (
              <button type="button" className="crm-btn crm-btn-ghost" onClick={() => setPicking(true)}>
                Switch book
              </button>
            )}
            <ShareTool toolId="crm" toolName="CRM" />
          </div>
        </header>

        {loadError && <div className="crm-error">{loadError}</div>}

        {picking || !ctx ? (
          !loadError && (advisors
            ? <AdvisorsView advisors={advisors} onOpen={selectAdvisor} />
            : <div className="crm-empty">Loading advisors…</div>)
        ) : (
          <>
            <nav className="crm-sectionnav">
              {(Object.keys(SECTION_LABELS) as Section[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`crm-sectiontab${activeSection === s ? ' active' : ''}`}
                  onClick={() => setView({ section: s })}
                >
                  {SECTION_LABELS[s]}
                </button>
              ))}
            </nav>

            {view.section === 'client' && (
              <button type="button" className="crm-back" onClick={() => setView({ section: 'clients' })}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                Back to Clients
              </button>
            )}

            <main className="crm-main">
              {view.section === 'dashboard' && <BookDashboard userId={ctx.advisor_id} onOpenClient={openClient} />}
              {view.section === 'clients' && <ClientsView onOpen={openClient} advisor={ctx.advisor_id} initialQuery={initial.clientQuery} />}
              {view.section === 'client' && <ClientRecord leadId={view.leadId} onOpenAdvisor={switchToAdvisorById} />}
              {view.section === 'pipeline' && <PipelineView onOpenClient={openClient} advisorName={ctx.name} />}
              {view.section === 'tasks' && <TasksView onOpenClient={openClient} owner={ctx.advisor_id} />}
            </main>
          </>
        )}
      </div>
    </div>
  );
};

export default Crm;
