// src/components/SideNav.tsx
// Shared left navigation rail mirroring the /home hub sidebar. Dropped into the
// standalone tool pages (Tamarac, Full Log, Rep Codes, Admin, SFP2) so they
// share the hub's global navigation. Active detection reads the current path so
// it works on any page regardless of router context. Links are filtered to the
// tools the current user (or impersonated user) can access.

import { useEffect, useMemo, useRef, useState } from 'react';
import { canAccessTool, useEffectiveAccess } from '../services/access';
import allworthLogo from '../assets/allworth-logo.svg';
import './SideNav.css';

interface NavLink {
  href: string;
  label: string;
  icon: React.ReactNode;
  matches?: string[];
  // Tool id gating this link. When omitted the link is always shown (e.g. the
  // Home hub). Links whose tool id is not in the user's effective access are
  // hidden from the rail.
  toolId?: string;
}

interface NavGroup {
  heading: string;
  links: NavLink[];
}

const icon = (path: React.ReactNode) => (
  <svg
    className="side-nav-icon"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {path}
  </svg>
);

const GROUPS: NavGroup[] = [
  {
    heading: 'Workspace',
    links: [
      { href: '/', label: 'Home', matches: ['/', '/home', '/home/'], icon: icon(<><path d="M3 12 12 3l9 9" /><path d="M5 10v10h14V10" /></>) },
    ],
  },
  {
    heading: 'Daily work',
    links: [
      { href: '/reporting/kpi', label: 'Performance', matches: ['/reporting/kpi'], toolId: 'performance', icon: icon(<><path d="M3 3v18h18" /><path d="M7 15l3-4 3 3 4-6" /></>) },
      { href: '/crm', label: 'CRM', matches: ['/crm'], toolId: 'crm', icon: icon(<><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.9" /><path d="M16 3.1a4 4 0 0 1 0 7.8" /></>) },
      { href: '/pipeline-review', label: 'Pipeline Review', matches: ['/pipeline-review'], toolId: 'pipeline_review', icon: icon(<><path d="M3 3v18h18" /><path d="m7 14 4-4 3 3 5-6" /></>) },
      { href: '/executive-report', label: 'Executive Report', matches: ['/executive-report'], toolId: 'executive_report', icon: icon(<><path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" /><rect x="12" y="7" width="3" height="10" /><rect x="17" y="4" width="3" height="13" /></>) },
      { href: '/brief', label: 'Executive Brief', matches: ['/brief'], toolId: 'brief', icon: icon(<><path d="M3 6h18v12H3z" /><path d="m3 7 9 6 9-6" /></>) },
      { href: '/fee-calculator', label: 'Fee Calculator', matches: ['/fee-calculator'], toolId: 'fee_calculator', icon: icon(<><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M8 6h8" /><path d="M8 10h8" /><path d="M8 14h4" /><path d="M8 18h6" /></>) },
      { href: '/planning', label: 'Financial Planning', matches: ['/planning'], toolId: 'financial_planning', icon: icon(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" /><path d="M12 3v3" /><path d="M12 18v3" /><path d="M3 12h3" /><path d="M18 12h3" /></>) },
      { href: '/avantos', label: 'Avantos', matches: ['/avantos'], toolId: 'avantos', icon: icon(<><path d="M3 17l6-6 4 4 8-8" /><path d="M14 7h7v7" /></>) },
    ],
  },
  {
    heading: 'Portfolio tools',
    links: [
      { href: '/rebalancer', label: 'Mock Rebalancer', matches: ['/rebalancer'], toolId: 'rebalancer', icon: icon(<><path d="M12 3v18" /><path d="M5 8l7-5 7 5" /><path d="M3 14a3 3 0 0 0 6 0l-3-6z" /><path d="M15 14a3 3 0 0 0 6 0l-3-6z" /></>) },
      { href: '/bond-analyzer', label: 'Bond Analyzer', matches: ['/bond-analyzer'], toolId: 'bond_analyzer', icon: icon(<><path d="M3 3v18h18" /><path d="M7 13h2v4H7z" /><path d="M11 9h2v8h-2z" /><path d="M15 5h2v12h-2z" /></>) },
      { href: '/advisor-mailer', label: 'Advisor Mailer', matches: ['/advisor-mailer'], toolId: 'advisor_mailer', icon: icon(<><path d="M3 6h18v12H3z" /><path d="m3 7 9 6 9-6" /><path d="M8 18h8" /></>) },
    ],
  },
  {
    heading: 'Data & operations',
    links: [
      { href: '/jarvis', label: 'Jarvis Encyclopedia', matches: ['/jarvis'], toolId: 'jarvis', icon: icon(<><path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z" /><path d="M9 8h6" /><path d="M9 12h6" /><path d="M9 16h4" /></>) },
      { href: '/nfbc', label: 'NFBC Adjustments', matches: ['/nfbc'], toolId: 'nfbc', icon: icon(<><path d="M4 4h16v16H4z" /><path d="M4 9h16" /><path d="M4 14h16" /><path d="M9 4v16" /></>) },
      { href: '/file-explorer', label: 'File Explorer', matches: ['/file-explorer'], toolId: 'file_explorer', icon: icon(<><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 11v5" /><path d="m9.5 13.5 2.5-2.5 2.5 2.5" /></>) },
      { href: '/catalog/', label: 'Data Catalog', matches: ['/catalog', '/catalog/'], toolId: 'data_catalog', icon: icon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>) },
      { href: '/sfp2', label: 'Salesforce Schema', matches: ['/sfp2'], toolId: 'sfp2', icon: icon(<><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h10" /><circle cx="18" cy="18" r="2" /></>) },
      { href: '/repcodes', label: 'Rep Codes', matches: ['/repcodes'], toolId: 'repcodes', icon: icon(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18" /><path d="M8 4v16" /></>) },
      { href: '/tamarac', label: 'Tamarac Runs', matches: ['/tamarac'], toolId: 'pipeline_logging', icon: icon(<><path d="M4 7h10" /><path d="M4 12h16" /><path d="M4 17h7" /><circle cx="18" cy="7" r="2" /><circle cx="14" cy="17" r="2" /></>) },
      { href: '/refresh_log', label: 'Refresh Log', matches: ['/refresh_log', '/refresh-log'], toolId: 'pipeline_logging', icon: icon(<><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 3v6h-6" /></>) },
    ],
  },
  {
    heading: 'Administration',
    links: [
      { href: '/admin', label: 'Access Management', matches: ['/admin'], toolId: 'admin', icon: icon(<><path d="M12 2 4 5v6c0 5 3.4 8.5 8 11 4.6-2.5 8-6 8-11V5z" /><circle cx="12" cy="10" r="2.4" /><path d="M8.5 16a3.7 3.7 0 0 1 7 0" /></>) },
      { href: '/app-usage', label: 'App Usage', matches: ['/app-usage'], toolId: 'admin', icon: icon(<><path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" rx="1" /><rect x="12" y="7" width="3" height="10" rx="1" /><rect x="17" y="13" width="3" height="4" rx="1" /></>) },
      { href: '/automations', label: 'Automations', matches: ['/automations'], toolId: 'admin', icon: icon(<><path d="M12 2v4" /><path d="m16.2 7.8 2.9-2.9" /><path d="M18 12h4" /><circle cx="12" cy="12" r="4" /><path d="M4.9 4.9 7.8 7.8" /><path d="M2 12h4" /></>) },
    ],
  },
];
const chevronRight = (
  <svg className="side-nav-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
);
const searchIcon = icon(<><circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" /></>);
const panelIcon = icon(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M9 4v16" /></>);
const menuIcon = icon(<><path d="M4 7h16" /><path d="M4 12h16" /><path d="M4 17h16" /></>);
const closeIcon = icon(<><path d="m6 6 12 12" /><path d="m18 6-12 12" /></>);

function accountName(email: string | null | undefined): string {
  if (!email) return 'Signed-in user';
  const local = email.split('@')[0] ?? '';
  if (local.toLowerCase() === 'demo') return 'Demo user';
  const words = local.split(/[._-]+/).filter(Boolean).slice(0, 2);
  if (!words.length) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function accountInitials(email: string | null | undefined): string {
  const name = accountName(email);
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join('')
    .toUpperCase();
}

// ── access resolution ──────────────────────────────────────────────────────
// Effective access (with "view as" impersonation applied) is resolved by the
// shared services/access module so the rail, the Home hub, and the route guard
// all agree on what the current (or impersonated) user can reach.


const SideNav = () => {
  const access = useEffectiveAccess();
  const searchInput = useRef<HTMLInputElement>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState('');

  useEffect(() => {
    setCollapsed(window.localStorage.getItem('allworth-nav-collapsed') === 'true');
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty('--aw-nav-width', collapsed ? '72px' : '252px');
    return () => {
      document.documentElement.style.removeProperty('--aw-nav-width');
    };
  }, [collapsed]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearchOpen((open) => !open);
      }
      if (event.key === 'Escape') {
        setSearchOpen(false);
        setMobileOpen(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  useEffect(() => {
    if (!searchOpen) {
      setQuery('');
      return;
    }
    window.requestAnimationFrame(() => searchInput.current?.focus());
  }, [searchOpen]);

  const current = (() => {
    try {
      return window.location.pathname.replace(/\/+$/, '') || '/';
    } catch {
      return '/';
    }
  })();

  const isActive = (link: NavLink) => {
    const matches = link.matches ?? [link.href];
    return matches.some((m) => (m.replace(/\/+$/, '') || '/') === current);
  };

  // A link is visible when it has no tool gate (Home), or the user has full
  // access, or the tool id is in the effective set. While access is still
  // loading (null) only ungated links are shown to avoid a flash of tools the
  // user can't reach.
  const canSee = (link: NavLink) => canAccessTool(access, link.toolId);

  const renderLink = (link: NavLink) => (
    <a
      key={link.href}
      href={link.href}
      className={isActive(link) ? 'side-nav-item active' : 'side-nav-item'}
      aria-current={isActive(link) ? 'page' : undefined}
      title={collapsed ? link.label : undefined}
      onClick={() => setMobileOpen(false)}
    >
      {link.icon}
      <span>{link.label}</span>
    </a>
  );

  const visibleGroups = GROUPS.map((group) => ({
    ...group,
    links: group.links.filter(canSee),
  })).filter((group) => group.links.length > 0);

  const accountEmail = access?.email ?? null;
  const accessLabel = access?.all
    ? 'All tools'
    : `${access?.tools.size ?? 0} ${access?.tools.size === 1 ? 'tool' : 'tools'}`;

  const searchResults = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const entries = GROUPS.flatMap((group) => group.links.map((link) => ({ ...link, group: group.heading }))).filter(canSee);
    if (!needle) return entries;
    return entries.filter((entry) => `${entry.label} ${entry.group}`.toLowerCase().includes(needle));
  }, [access, query]);

  const toggleCollapsed = () => {
    setCollapsed((value) => {
      window.localStorage.setItem('allworth-nav-collapsed', String(!value));
      return !value;
    });
  };

  return (
    <>
      <button
        type="button"
        className="side-nav-mobile-trigger"
        aria-label="Open navigation"
        aria-expanded={mobileOpen}
        onClick={() => setMobileOpen(true)}
      >
        {menuIcon}
      </button>
      {mobileOpen && <button type="button" className="side-nav-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}
      <aside className={`side-nav${collapsed ? ' is-collapsed' : ''}${mobileOpen ? ' is-mobile-open' : ''}`} aria-label="Primary">
      <div className="side-nav-brand-row">
        <a className="side-nav-brand" href="/" aria-label="Allworth workspace">
          <img
            src={allworthLogo}
            alt="Allworth"
            onError={(event) => {
              event.currentTarget.hidden = true;
              event.currentTarget.nextElementSibling?.classList.add('visible');
            }}
          />
          <span className="side-nav-brand-fallback">Allworth</span>
        </a>
        <button type="button" className="side-nav-mobile-close" aria-label="Close navigation" onClick={() => setMobileOpen(false)}>{closeIcon}</button>
      </div>
      <button type="button" className="side-nav-search" onClick={() => { setMobileOpen(false); setSearchOpen(true); }} title={collapsed ? 'Find a tool' : undefined}>
        {searchIcon}
        <span>Find a tool</span>
        <kbd>⌘ K</kbd>
      </button>
      <nav className="side-nav-scroll">
        {visibleGroups.map((group) => (
          <div className="side-nav-group" key={group.heading}>
            <h6>{group.heading}</h6>
            {group.links.map(renderLink)}
          </div>
        ))}
      </nav>
      <div
        className="side-nav-account"
        aria-label={accountEmail ? `Signed in as ${accountEmail}` : 'Signed-in account'}
        title={collapsed ? `${accountName(accountEmail)} · ${accountEmail ?? accessLabel}` : undefined}
      >
        <span className="side-nav-account-avatar" aria-hidden="true">
          {accountInitials(accountEmail)}
        </span>
        <span className="side-nav-account-copy">
          <strong>{accountName(accountEmail)}</strong>
          <span>{accountEmail ?? 'Account details unavailable'}</span>
          <small>{access?.impersonating ? 'Viewing as · ' : ''}{accessLabel}</small>
        </span>
      </div>
      <button type="button" className="side-nav-collapse" onClick={toggleCollapsed} aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}>
        {panelIcon}
        <span>{collapsed ? 'Expand' : 'Collapse'}</span>
      </button>
      </aside>

      {searchOpen && (
        <div className="side-nav-command" role="dialog" aria-modal="true" aria-label="Find a tool" onMouseDown={(event) => event.target === event.currentTarget && setSearchOpen(false)}>
          <div className="side-nav-command-panel">
            <div className="side-nav-command-input">
              {searchIcon}
              <input
                ref={searchInput}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search tools and reports"
                aria-label="Search tools and reports"
              />
              <button type="button" onClick={() => setSearchOpen(false)}>Esc</button>
            </div>
            <div className="side-nav-command-results">
              {searchResults.length ? searchResults.map((entry) => (
                <a key={`${entry.group}-${entry.href}`} href={entry.href} onClick={() => { setSearchOpen(false); setMobileOpen(false); }}>
                  {entry.icon}
                  <span>{entry.label}<small>{entry.group}</small></span>
                  {chevronRight}
                </a>
              )) : <p>No matching tools.</p>}
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default SideNav;
