// src/components/SideNav.tsx
// Shared left navigation rail mirroring the /home hub sidebar. Dropped into the
// standalone tool pages (Tamarac, Full Log, Rep Codes, Admin, SFP2) so they
// share the hub's global navigation. Active detection reads the current path so
// it works on any page regardless of router context. Links are filtered to the
// tools the current user (or impersonated user) can access.

import { useState } from 'react';
import { canAccessTool, useEffectiveAccess } from '../services/access';
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
    heading: 'Live tools',
    links: [
      { href: '/nfbc', label: 'NFBC Adjustments', matches: ['/nfbc'], toolId: 'nfbc', icon: icon(<><path d="M4 4h16v16H4z" /><path d="M4 9h16" /><path d="M4 14h16" /><path d="M9 4v16" /></>) },
      { href: '/fee-calculator', label: 'Fee Calculator', matches: ['/fee-calculator'], toolId: 'fee_calculator', icon: icon(<><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M8 6h8" /><path d="M8 10h8" /><path d="M8 14h4" /><path d="M8 18h6" /></>) },
      { href: '/pipeline-review', label: 'Pipeline Review', matches: ['/pipeline-review'], toolId: 'pipeline_review', icon: icon(<><path d="M3 3v18h18" /><path d="m7 14 4-4 3 3 5-6" /></>) },
      { href: '/executive-report', label: 'Executive Report', matches: ['/executive-report'], toolId: 'executive_report', icon: icon(<><path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" /><rect x="12" y="7" width="3" height="10" /><rect x="17" y="4" width="3" height="13" /></>) },
      { href: '/crm', label: 'CRM', matches: ['/crm'], toolId: 'crm', icon: icon(<><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.9" /><path d="M16 3.1a4 4 0 0 1 0 7.8" /></>) },
      { href: '/file-explorer', label: 'File Explorer', matches: ['/file-explorer'], toolId: 'file_explorer', icon: icon(<><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 11v5" /><path d="m9.5 13.5 2.5-2.5 2.5 2.5" /></>) },
      { href: '/catalog/', label: 'Data Catalog', matches: ['/catalog', '/catalog/'], toolId: 'data_catalog', icon: icon(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>) },
      { href: '/brief', label: 'Executive Brief', matches: ['/brief'], toolId: 'brief', icon: icon(<><path d="M3 6h18v12H3z" /><path d="m3 7 9 6 9-6" /></>) },
      { href: '/planning', label: 'Financial Planning', matches: ['/planning'], toolId: 'financial_planning', icon: icon(<><circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.5" /><path d="M12 3v3" /><path d="M12 18v3" /><path d="M3 12h3" /><path d="M18 12h3" /></>) },
      { href: '/avantos', label: 'Avantos', matches: ['/avantos'], toolId: 'avantos', icon: icon(<><path d="M3 17l6-6 4 4 8-8" /><path d="M14 7h7v7" /></>) },
  { href: '/rebalancer', label: 'Mock Rebalancer', matches: ['/rebalancer'], toolId: 'rebalancer', icon: icon(<><path d="M12 3v18" /><path d="M5 8l7-5 7 5" /><path d="M3 14a3 3 0 0 0 6 0l-3-6z" /><path d="M15 14a3 3 0 0 0 6 0l-3-6z" /></>) },
      { href: '/sfp2', label: 'Salesforce Column Updater', matches: ['/sfp2'], toolId: 'sfp2', icon: icon(<><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h10" /><circle cx="18" cy="18" r="2" /></>) },
      { href: '/repcodes', label: 'Rep Codes', matches: ['/repcodes'], toolId: 'repcodes', icon: icon(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18" /><path d="M8 4v16" /></>) },
      { href: '/bond-analyzer', label: 'Bond Analyzer', matches: ['/bond-analyzer'], toolId: 'bond_analyzer', icon: icon(<><path d="M3 3v18h18" /><path d="M7 13h2v4H7z" /><path d="M11 9h2v8h-2z" /><path d="M15 5h2v12h-2z" /></>) },
      { href: '/advisor-mailer', label: 'Advisor Mailer', matches: ['/advisor-mailer'], toolId: 'advisor_mailer', icon: icon(<><path d="M3 6h18v12H3z" /><path d="m3 7 9 6 9-6" /><path d="M8 18h8" /></>) },
    ],
  },
  {
    heading: 'Admin',
    links: [
      { href: '/admin', label: 'Admin', matches: ['/admin'], toolId: 'admin', icon: icon(<><path d="M12 2 4 5v6c0 5 3.4 8.5 8 11 4.6-2.5 8-6 8-11V5z" /><circle cx="12" cy="10" r="2.4" /><path d="M8.5 16a3.7 3.7 0 0 1 7 0" /></>) },
      { href: '/app-usage', label: 'App Usage', matches: ['/app-usage'], toolId: 'admin', icon: icon(<><path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" rx="1" /><rect x="12" y="7" width="3" height="10" rx="1" /><rect x="17" y="13" width="3" height="4" rx="1" /></>) },
      { href: '/automations', label: 'Automations', matches: ['/automations'], toolId: 'admin', icon: icon(<><path d="M12 2v4" /><path d="m16.2 7.8 2.9-2.9" /><path d="M18 12h4" /><circle cx="12" cy="12" r="4" /><path d="M4.9 4.9 7.8 7.8" /><path d="M2 12h4" /></>) },
      { href: '/tamarac', label: 'Tamarac', matches: ['/tamarac'], toolId: 'pipeline_logging', icon: icon(<><path d="M4 7h10" /><path d="M4 12h16" /><path d="M4 17h7" /><circle cx="18" cy="7" r="2" /><circle cx="14" cy="17" r="2" /></>) },
      { href: '/refresh_log', label: 'Full Log', matches: ['/refresh_log', '/refresh-log'], toolId: 'pipeline_logging', icon: icon(<><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 3v6h-6" /></>) },
    ],
  },
];

// Reports live under the /reporting/* hierarchy and are surfaced via the
// "Reporting" drill-in section rather than the top-level tool list. Add new
// reports here as the section grows.
const REPORTS: NavLink[] = [
  { href: '/reporting/kpi', label: 'Growth KPIs', matches: ['/reporting/kpi'], toolId: 'performance', icon: icon(<><rect x="3" y="4" width="18" height="14" rx="2" /><path d="M8 20h8" /><path d="M7 12l3-3 3 3 4-5" /></>) },
];

const reportingIcon = icon(<><path d="M3 3v18h18" /><path d="M7 15l3-4 3 3 4-6" /></>);
const chevronRight = (
  <svg className="side-nav-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
);
const chevronLeft = (
  <svg className="side-nav-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
);

// ── access resolution ──────────────────────────────────────────────────────
// Effective access (with "view as" impersonation applied) is resolved by the
// shared services/access module so the rail, the Home hub, and the route guard
// all agree on what the current (or impersonated) user can reach.


const SideNav = () => {
  const access = useEffectiveAccess();

  const current = (() => {
    try {
      return window.location.pathname.replace(/\/+$/, '') || '/';
    } catch {
      return '/';
    }
  })();

  // Two-level nav: the top-level ("hub") view lists the workspace sections and a
  // "Reporting" drill-in; selecting it swaps the pane to the reports list with a
  // "Back to hub" button. Defaults to the reporting view when already on a
  // /reporting/* page so the active report is in context.
  const [view, setView] = useState<'hub' | 'reporting'>(
    current.startsWith('/reporting') ? 'reporting' : 'hub'
  );

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
    >
      {link.icon}
      <span>{link.label}</span>
    </a>
  );

  const visibleReports = REPORTS.filter(canSee);
  const hasReporting = visibleReports.length > 0;
  const reportingActive = current.startsWith('/reporting');

  const visibleGroups = GROUPS.map((group) => ({
    ...group,
    links: group.links.filter(canSee),
  })).filter((group) => group.links.length > 0);

  const workspaceGroup = visibleGroups.find((g) => g.heading === 'Workspace');
  const otherGroups = visibleGroups.filter((g) => g.heading !== 'Workspace');

  return (
    <aside className="side-nav" aria-label="Primary">
      <a className="side-nav-brand" href="/">
        <img src="/home/logo.png" alt="Allworth" onError={(e) => (e.currentTarget.style.display = 'none')} />
        <span className="side-nav-brand-chip">Hub</span>
      </a>
      <nav className="side-nav-scroll">
        {view === 'reporting' ? (
          <>
            <button
              type="button"
              className="side-nav-back"
              onClick={() => setView('hub')}
            >
              {chevronLeft}
              <span>Back to hub</span>
            </button>
            <div className="side-nav-group">
              <h6>Reporting</h6>
              {visibleReports.map(renderLink)}
            </div>
          </>
        ) : (
          <>
            {workspaceGroup && (
              <div className="side-nav-group" key={workspaceGroup.heading}>
                <h6>{workspaceGroup.heading}</h6>
                {workspaceGroup.links.map(renderLink)}
              </div>
            )}
            {hasReporting && (
              <div className="side-nav-group">
                <h6>Reporting</h6>
                <button
                  type="button"
                  className={
                    'side-nav-item side-nav-drill' + (reportingActive ? ' active' : '')
                  }
                  aria-expanded={false}
                  onClick={() => setView('reporting')}
                >
                  {reportingIcon}
                  <span>Reporting</span>
                  {chevronRight}
                </button>
              </div>
            )}
            {otherGroups.map((group) => (
              <div className="side-nav-group" key={group.heading}>
                <h6>{group.heading}</h6>
                {group.links.map(renderLink)}
              </div>
            ))}
          </>
        )}
      </nav>
    </aside>
  );
};

export default SideNav;
