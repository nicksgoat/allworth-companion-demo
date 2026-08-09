import { useEffect, useMemo, useRef, useState } from 'react';
import SideNav from './components/SideNav';
import AccountToolWidgets from './components/AccountToolWidgets';
import type { AccountWidgetKey } from './components/AccountToolWidgets';
import { ToolIcon } from './components/ToolIcon';
import { canAccessTool, useEffectiveAccess } from './services/access';
import { useWorkspace } from './components/WorkspaceContext';
import { AssignmentHome } from './components/AssignmentHome';
import { assignableTools, toolManifest, tools, type ToolCategory, type ToolDefinition } from './config/toolManifest';
import './Home.css';

const CATEGORY_ORDER: ToolCategory[] = ['live', 'analytics', 'utilities'];
const CORE_WIDGET_IDS = assignableTools.filter((tool) => tool.widget?.kind === 'core').map((tool) => tool.id as AccountWidgetKey);

const arrow = (
  <svg className="hub-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></svg>
);

function accountName(email: string | null | undefined): string {
  if (!email) return 'this account';
  const local = email.split('@')[0] ?? '';
  if (local.toLowerCase() === 'demo') return 'Demo user';
  const words = local.split(/[._-]+/).filter(Boolean).slice(0, 2);
  if (!words.length) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function Card({ tool }: { tool: ToolDefinition }) {
  const body = <div className="hub-card-top">
    <span className="hub-card-icon"><ToolIcon name={tool.icon} /></span>
    <div className="hub-card-title-wrap">
      <div className="hub-card-title">{tool.name}</div>
      <div className="hub-card-desc">{tool.description}</div>
    </div>
    {tool.url ? arrow : <span className="hub-card-status">In planning</span>}
  </div>;

  return tool.url
    ? <a className="hub-card" href={tool.url}>{body}</a>
    : <div className="hub-card disabled" aria-disabled="true">{body}</div>;
}

export default function Home() {
  const access = useEffectiveAccess();
  const workspace = useWorkspace();
  const searchInput = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.key === '/' && !target?.matches('input, textarea, select, [contenteditable="true"]')) {
        event.preventDefault();
        searchInput.current?.focus();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  const visibleTools = useMemo(
    () => tools.filter((tool) => tool.status === 'soon' || canAccessTool(access, tool.id)),
    [access],
  );
  const available = visibleTools.filter((tool) => tool.url);
  const planning = visibleTools.filter((tool) => !tool.url);
  const needle = query.trim().toLowerCase();
  const matching = available.filter((tool) => !needle || `${tool.name} ${tool.kicker} ${tool.description}`.toLowerCase().includes(needle));
  const sections = CATEGORY_ORDER.map((category) => ({
    category,
    label: toolManifest.sections[category].label,
    tools: matching.filter((tool) => tool.category === category),
  })).filter((section) => section.tools.length);
  const widgetAccess = Object.fromEntries(CORE_WIDGET_IDS.map((id) => [id, canAccessTool(access, id)])) as Record<AccountWidgetKey, boolean>;

  if (!workspace.loading && workspace.me && workspace.me.assignment.type !== 'general') return <AssignmentHome />;

  return <div className="home-hub has-sidenav">
    <SideNav />
    <div className="hub-main">
      <div className="hub-inner">
        <header className="hub-intro">
          <p className="hub-eyebrow">Allworth workspace</p>
          <h1>What do you need to do?</h1>
          <div className="hub-search">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            <input ref={searchInput} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a tool or report" aria-label="Find a tool or report" />
            {!query && <kbd>/</kbd>}
          </div>
          <p className="hub-availability">{query ? `${matching.length} matching ${matching.length === 1 ? 'tool' : 'tools'}` : `${available.length} tools available to you`}</p>
        </header>

        {!query && <AccountToolWidgets enabled={widgetAccess} accountLabel={`${accountName(access?.email)} · ${access?.all ? 'all tools enabled' : `${available.length} enabled`}`} />}

        {sections.map((section) => <div key={section.category}>
          <div className="hub-section-head"><div><h2>{section.label}</h2></div></div>
          <div className="hub-card-grid">{section.tools.map((tool) => <Card key={tool.id} tool={tool} />)}</div>
        </div>)}

        {query && matching.length === 0 && <div className="hub-empty"><h2>No tools found</h2><p>Try a task, report name, or data source.</p><button type="button" onClick={() => { setQuery(''); searchInput.current?.focus(); }}>Clear search</button></div>}

        {!query && planning.length > 0 && <details className="hub-planning"><summary>In planning <span>{planning.length}</span></summary><div className="hub-card-grid">{planning.map((tool) => <Card key={tool.id} tool={tool} />)}</div></details>}
      </div>
      <div className="hub-footer"><span><strong>Allworth Financial</strong></span><span>Internal workspace</span></div>
    </div>
  </div>;
}
