import { useEffect, useMemo, useRef, useState } from 'react';
import { canAccessTool, useEffectiveAccess } from '../services/access';
import { tools, type ToolNavigationItem } from '../config/toolManifest';
import { householdHref } from '../services/workspace';
import allworthLogo from '../assets/allworth-logo.svg';
import { useWorkspace } from './WorkspaceContext';
import { ToolIcon } from './ToolIcon';
import './SideNav.css';

interface NavLink extends ToolNavigationItem {
  toolId?: string;
  icon: string;
}

interface NavGroup { heading: string; links: NavLink[] }

const GROUP_ORDER = ['Daily work', 'Portfolio tools', 'Data and operations', 'Administration'];
const ADVISOR_ORDER = ['crm', 'financial_planning', 'pipeline_review', 'fee_calculator', 'avantos'];
const HOME_LINK: NavLink = { href: '/', label: 'Home', matches: ['/', '/home', '/home/'], group: 'Workspace', icon: 'home' };

const iconPaths: Record<string, React.ReactNode> = {
  home: <><path d="M3 12 12 3l9 9" /><path d="M5 10v10h14V10" /></>,
  search: <><circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" /></>,
  panel: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="m6 6 12 12m0-12L6 18" />,
  chevron: <path d="m9 6 6 6-6 6" />,
};

function StaticIcon({ name, className = 'side-nav-icon' }: { name: string; className?: string }) {
  return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name]}</svg>;
}

function manifestLinks(): NavLink[] {
  return tools.flatMap((tool) => tool.navigation.map((item) => ({ ...item, toolId: tool.id, icon: tool.icon })));
}

function baseGroups(): NavGroup[] {
  const links = manifestLinks();
  return [{ heading: 'Workspace', links: [HOME_LINK] }, ...GROUP_ORDER.map((heading) => ({ heading, links: links.filter((link) => link.group === heading) }))];
}

function advisorGroups(groups: NavGroup[]): NavGroup[] {
  const links = groups.flatMap((group) => group.links);
  const primary = ADVISOR_ORDER.map((toolId) => links.find((link) => link.toolId === toolId)).filter((link): link is NavLink => Boolean(link));
  const primaryHrefs = new Set(primary.map((link) => link.href));
  return [
    { heading: 'Advisor workspace', links: [{ ...HOME_LINK, label: 'My book' }, ...primary.map((link) => ({ ...link, label: link.advisor_label ?? link.label }))] },
    ...groups.slice(1).map((group) => ({ ...group, links: group.links.filter((link) => !primaryHrefs.has(link.href)) })),
  ];
}

function accountName(email: string | null | undefined): string {
  if (!email) return 'Signed-in user';
  const local = email.split('@')[0] ?? '';
  if (local.toLowerCase() === 'demo') return 'Demo user';
  const words = local.split(/[._-]+/).filter(Boolean).slice(0, 2);
  return words.length ? words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ') : email;
}

function accountInitials(email: string | null | undefined): string {
  return accountName(email).split(/\s+/).filter(Boolean).slice(0, 2).map((word) => word.charAt(0)).join('').toUpperCase();
}

export default function SideNav() {
  const access = useEffectiveAccess();
  const workspace = useWorkspace();
  const searchInput = useRef<HTMLInputElement>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => { setCollapsed(window.localStorage.getItem('allworth-nav-collapsed') === 'true'); }, []);
  useEffect(() => {
    document.documentElement.style.setProperty('--aw-nav-width', collapsed ? '72px' : '260px');
    return () => { document.documentElement.style.removeProperty('--aw-nav-width'); };
  }, [collapsed]);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); setSearchOpen((open) => !open); }
      if (event.key === 'Escape') { setSearchOpen(false); setMobileOpen(false); }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);
  useEffect(() => {
    if (!searchOpen) { setQuery(''); return; }
    window.requestAnimationFrame(() => searchInput.current?.focus());
  }, [searchOpen]);

  const current = window.location.pathname.replace(/\/+$/, '') || '/';
  const canSee = (link: NavLink) => canAccessTool(access, link.toolId);
  const groups = workspace.me?.assignment.type === 'advisor' ? advisorGroups(baseGroups()) : baseGroups();
  const visibleGroups = groups.map((group) => ({ ...group, links: group.links.filter(canSee) })).filter((group) => group.links.length);
  const entries = groups.flatMap((group) => group.links.map((link) => ({ ...link, group: group.heading }))).filter(canSee);
  const needle = query.trim().toLowerCase();
  const searchResults = useMemo(() => needle ? entries.filter((entry) => `${entry.label} ${entry.group}`.toLowerCase().includes(needle)) : entries, [entries, needle]);
  const accountEmail = access?.email ?? null;
  const accessLabel = access?.all ? 'All tools' : `${access?.tools.size ?? 0} ${access?.tools.size === 1 ? 'tool' : 'tools'}`;
  const isActive = (link: NavLink) => link.matches.some((match) => (match.replace(/\/+$/, '') || '/') === current);
  const toggleCollapsed = () => setCollapsed((value) => { window.localStorage.setItem('allworth-nav-collapsed', String(!value)); return !value; });

  const renderLink = (link: NavLink) => <a key={`${link.toolId ?? 'workspace'}-${link.href}`} href={link.href} className={isActive(link) ? 'side-nav-item active' : 'side-nav-item'} aria-current={isActive(link) ? 'page' : undefined} title={collapsed ? link.label : undefined} onClick={() => setMobileOpen(false)}>
    {link.icon === 'home' ? <StaticIcon name="home" /> : <ToolIcon name={link.icon} className="side-nav-icon" />}
    <span>{link.label}</span>
  </a>;

  return <>
    <button type="button" className="side-nav-mobile-trigger" aria-label="Open navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)}><StaticIcon name="menu" /></button>
    {mobileOpen && <button type="button" className="side-nav-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
    <aside className={`side-nav${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' is-mobile-open' : ''}`} aria-label="Primary">
      <div className="side-nav-brand-row">
        <a className="side-nav-brand" href="/" aria-label="Allworth workspace"><img className="side-nav-brand-wordmark" src={allworthLogo} alt="Allworth" onError={(event) => { event.currentTarget.hidden = true; event.currentTarget.parentElement?.querySelector('.side-nav-brand-fallback')?.classList.add('visible'); }} /><span className="side-nav-brand-fallback">Allworth</span></a>
        <button type="button" className="side-nav-collapse" onClick={toggleCollapsed} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'} title={collapsed ? 'Expand navigation' : 'Collapse navigation'}><StaticIcon name="panel" /></button>
        <button type="button" className="side-nav-mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><StaticIcon name="close" /></button>
      </div>
      <button type="button" className="side-nav-search" onClick={() => { setMobileOpen(false); setSearchOpen(true); }} title={collapsed ? 'Search tools' : undefined}><StaticIcon name="search" /><span>Search tools</span><kbd>⌘ K</kbd></button>
      <nav className="side-nav-scroll">{visibleGroups.map((group) => <div className="side-nav-group" key={group.heading}><h6>{group.heading}</h6>{group.links.map(renderLink)}</div>)}</nav>
      {workspace.household && <a className="side-nav-household" href={householdHref('/', workspace.household)} title={collapsed ? workspace.household.name : undefined}><span>Active household</span><strong>{workspace.household.name}</strong><small>{workspace.household.plan_status === 'published' ? 'Plan published' : workspace.household.plan_status === 'draft' ? 'Plan in progress' : 'Plan not started'}</small></a>}
      <div className="side-nav-account" aria-label={accountEmail ? `Signed in as ${accountEmail}` : 'Signed-in account'} title={collapsed ? `${accountName(accountEmail)} · ${accountEmail ?? accessLabel}` : undefined}>
        <span className="side-nav-account-avatar" aria-hidden="true">{accountInitials(accountEmail)}</span>
        <span className="side-nav-account-copy"><strong>{accountName(accountEmail)}</strong><span>{accountEmail ?? 'Account details unavailable'}</span><small>{access?.impersonating ? 'Viewing as · ' : ''}{accessLabel}</small></span>
      </div>
    </aside>
    {searchOpen && <div className="side-nav-command" role="dialog" aria-modal="true" aria-label="Find a tool" onMouseDown={(event) => event.target === event.currentTarget && setSearchOpen(false)}>
      <div className="side-nav-command-panel">
        <div className="side-nav-command-input"><StaticIcon name="search" /><input ref={searchInput} value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search tools and reports" aria-label="Search tools and reports" /><button type="button" onClick={() => setSearchOpen(false)}>Esc</button></div>
        <div className="side-nav-command-results">{searchResults.length ? searchResults.map((entry) => <a key={`${entry.group}-${entry.href}`} href={entry.href} onClick={() => { setSearchOpen(false); setMobileOpen(false); }}>{entry.icon === 'home' ? <StaticIcon name="home" /> : <ToolIcon name={entry.icon} className="side-nav-icon" />}<span>{entry.label}<small>{entry.group}</small></span><StaticIcon name="chevron" className="side-nav-chevron" /></a>) : <p>No matching tools.</p>}</div>
      </div>
    </div>}
  </>;
}
