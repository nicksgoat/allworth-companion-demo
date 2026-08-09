import { useEffect, useMemo, useState } from 'react';
import SideNav from './SideNav';
import { RelationshipSpine } from './RelationshipSpine';
import { useWorkspace } from './WorkspaceContext';
import { WorkspaceToolWidgets } from './WorkspaceToolWidgets';
import { householdHref, workspaceApi, type AdvisorHomeData, type AdvisorHomeHousehold } from '../services/workspace';
import type { AssignmentType } from '../services/admin';
import { assignmentPresets } from '../config/toolManifest';
import './AssignmentHome.css';

const HOME_COPY: Record<Exclude<AssignmentType, 'advisor' | 'general'>, { eyebrow: string; title: string; description: string }> = {
  executive: { eyebrow: 'Executive workspace', title: 'Decisions that need your attention', description: 'Company performance, material changes, and leadership actions in one view.' },
  operations: { eyebrow: 'Operations workspace', title: 'Keep work moving cleanly', description: 'Resolve exceptions, monitor refreshes, and move governed work queues forward.' },
  platform_admin: { eyebrow: 'Platform workspace', title: 'Access, health, and control', description: 'Manage the workspace and catch operational issues before users encounter them.' },
};

function compactMoney(value: string | number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 1 }).format(Number(value));
}

function HouseholdRow({ row }: { row: AdvisorHomeHousehold }) {
  const work = row.open_alerts + row.open_tasks;
  return <a className="advisor-household-row" href={householdHref('/', row.context)}>
    <span className={`advisor-health-mark ${row.health_band}`} aria-label={row.health_band.replace('_', ' ')} />
    <span className="advisor-household-name"><strong>{row.name}</strong><small>{row.context.plan_status === 'published' ? 'Plan published' : 'Plan in progress'}{row.drift_flagged ? ' · Actuals changed' : ''}</small></span>
    <span><small>Relationship</small><strong>{compactMoney(row.context.aum || row.total_assets)}</strong></span>
    <span><small>Open work</small><strong>{work || 'Clear'}</strong></span>
    <span><small>Plan health</small><strong>{row.health_score}</strong></span>
    <b>→</b>
  </a>;
}

function AdvisorHome() {
  const { me, household } = useWorkspace();
  const [data, setData] = useState<AdvisorHomeData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!me?.advisor?.advisor_id) return;
    let live = true;
    void workspaceApi.advisorHome(me.advisor.advisor_id).then((result) => { if (live) setData(result); })
      .catch((reason) => { if (live) setError(reason instanceof Error ? reason.message : 'Advisor workbench is unavailable'); });
    return () => { live = false; };
  }, [me?.advisor?.advisor_id]);

  if (me?.advisor_status === 'unresolved') return <div className="assignment-home has-sidenav"><SideNav /><main className="assignment-home-main"><section className="advisor-unresolved"><span>Advisor workspace</span><h1>Link your advisor record</h1><p>Your assignment is active, but your advisor identity could not be matched. Ask an administrator to add an Advisor ID override to your account.</p></section></main></div>;
  const rows = data?.households ?? [];
  const selected = household ? rows.find((row) => row.context.planning_household_id === household.planning_household_id || row.context.crm_lead_id === household.crm_lead_id) : null;
  const attention = rows.filter((row) => row.open_alerts || row.open_tasks || row.drift_flagged).slice(0, 5);
  return <div className="assignment-home advisor-home has-sidenav"><SideNav /><main className="assignment-home-main">
    <RelationshipSpine />
    <header className="advisor-home-header"><div><span>{me?.assignment.name || 'Advisor workspace'}</span><h1>{selected ? selected.name : `Good morning${me?.advisor?.name ? `, ${me.advisor.name.split(' ')[0]}` : ''}.`}</h1><p>{selected ? 'The relationship context below will stay with you across every advisor tool.' : 'Start with the relationships that need judgment, then move into the connected work.'}</p></div>
      <a href="/crm">Find a household</a></header>
    {error && <div className="advisor-home-error">{error}</div>}
    <section className="advisor-ledger" aria-label="Advisor book summary">
      <div><small>Households</small><strong>{data?.summary.households ?? '—'}</strong></div>
      <div><small>Relationship assets</small><strong>{data ? compactMoney(data.summary.total_assets) : '—'}</strong></div>
      <div><small>Needs attention</small><strong>{data?.summary.needs_attention ?? '—'}</strong></div>
      <div><small>At risk</small><strong>{data?.summary.at_risk ?? '—'}</strong></div>
      <div><small>Plans to publish</small><strong>{data?.summary.unpublished ?? '—'}</strong></div>
    </section>
    <div className="advisor-work-grid"><section className="advisor-book"><header><div><span>Prioritized book</span><h2>Households to work</h2></div><a href="/avantos">Open full book</a></header>
      <div className="advisor-book-columns"><span>Household</span><span>Relationship</span><span>Open work</span><span>Plan health</span></div>
      {!data ? <p className="advisor-loading">Loading your book…</p> : rows.slice(0, 12).map((row) => <HouseholdRow key={row.household_id} row={row} />)}
    </section><aside className="advisor-attention"><span>Next actions</span><h2>Needs attention</h2>
      {attention.length ? attention.map((row) => <a key={row.household_id} href={householdHref('/planning', row.context)}><strong>{row.name}</strong><small>{row.drift_flagged ? 'Review changed actuals' : row.open_alerts ? `${row.open_alerts} plan alerts` : `${row.open_tasks} open tasks`}</small></a>) : <p>No urgent planning work.</p>}
    </aside></div>
  </main></div>;
}

export function AssignmentHome() {
  const { me, loading } = useWorkspace();
  const type = me?.assignment.type ?? 'general';
  const tools = useMemo(() => {
    if (!me) return [];
    const configured = me.home_tool_ids.length ? me.home_tool_ids : assignmentPresets[type];
    return configured.filter((tool) => me.all_access || me.effective_tools.includes(tool));
  }, [me, type]);
  if (loading) return <div className="assignment-home-loading">Loading workspace…</div>;
  if (type === 'advisor') return <AdvisorHome />;
  if (type === 'general') return null;
  const copy = HOME_COPY[type];
  return <div className={`assignment-home assignment-home-${type} has-sidenav`}><SideNav /><main className="assignment-home-main">
    <header className="role-home-header"><span>{copy.eyebrow}</span><h1>{copy.title}</h1><p>{copy.description}</p></header>
    <WorkspaceToolWidgets toolIds={tools} accountLabel={`${me?.assignment.name} · ${tools.length} connected tools`} />
  </main></div>;
}
