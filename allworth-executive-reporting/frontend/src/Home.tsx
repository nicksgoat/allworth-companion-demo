// src/Home.tsx
// Team hub / landing page. Previously a server-rendered Flask template
// (backend/home/templates/index.html); ported to React so it shares the exact
// same global navigation rail (<SideNav />) as every other tool page and so
// the "view as" impersonation overlay hides the same cards/nav a real user
// would never see. Card launchers are gated by effective tool access.

import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import SideNav from './components/SideNav';
import { canAccessTool, useEffectiveAccess } from './services/access';
import './Home.css';

type CardColor = 'navy' | 'orange' | 'sky' | 'slate' | 'teal';
type CardTag = 'live' | 'new' | 'soon';

interface HubCard {
  id: string;
  // Access key (matches tools.yaml id). When omitted the card is an
  // always-visible "coming soon" placeholder that is never gated.
  toolId?: string;
  kicker: string;
  title: string;
  tag: CardTag;
  color: CardColor;
  desc: ReactNode;
  href?: string;
  host: string;
  icon: ReactNode;
}

interface HubSection {
  heading: string;
  blurb: string;
  cards: HubCard[];
}

const svg = (path: ReactNode) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    {path}
  </svg>
);

// Card catalog mirrors the tool registry. Keep in sync with SideNav groups and
// backend/home/tools.yaml when adding a new tool (see the checklist in
// .github/copilot-instructions.md).
const SECTIONS: HubSection[] = [
  {
    heading: 'Live tools',
    blurb: 'Shipped and in production for the team to use today.',
    cards: [
      {
        id: 'performance',
        toolId: 'performance',
        kicker: 'Dashboard',
        title: 'Performance by Channel',
        tag: 'live',
        color: 'navy',
        href: '/reporting/kpi',
        host: '/reporting/kpi',
        desc: 'KPI matrix for NCNM, Clients, Appointments and Leads across every acquisition channel — with plan, prior-year and prorated current-month values.',
        icon: svg(<><path d="M3 3v18h18" /><path d="M7 15l4-4 4 4 5-6" /></>),
      },
      {
        id: 'nfbc',
        toolId: 'nfbc',
        kicker: 'Agentic ops',
        title: 'NFBC Adjustments',
        tag: 'new',
        color: 'orange',
        href: '/nfbc',
        host: '/nfbc',
        desc: 'Review and confirm proposed NFBC flow adjustments across open Jira tickets — edit inline, then one click writes Synapse, runs rollforward, and posts the reply back to Jira.',
        icon: svg(<><path d="M4 4h16v16H4z" /><path d="M4 9h16" /><path d="M4 14h16" /><path d="M9 4v16" /></>),
      },
      {
        id: 'fee_calculator',
        toolId: 'fee_calculator',
        kicker: 'Pricing',
        title: 'Fee Calculator',
        tag: 'live',
        color: 'teal',
        href: '/fee-calculator',
        host: '/fee-calculator',
        desc: 'Tiered fee computation for new client pricing — search households, pull AUM from rollforward, compare schedules, and upload billing history.',
        icon: svg(<><rect x="4" y="2" width="16" height="20" rx="2" /><path d="M8 6h8" /><path d="M8 10h8" /><path d="M8 14h4" /><path d="M8 18h6" /></>),
      },
      {
        id: 'pipeline_review',
        toolId: 'pipeline_review',
        kicker: 'Prospect focus list',
        title: 'Pipeline Review',
        tag: 'live',
        color: 'teal',
        href: '/pipeline-review',
        host: '/pipeline-review',
        desc: 'Weekly high-value prospect focus list with scoring, week-over-week trends, at-risk flags, check-off, and XLSX export.',
        icon: svg(<><path d="M3 3v18h18" /><path d="m7 14 4-4 3 3 5-6" /></>),
      },
      {
        id: 'executive_report',
        toolId: 'executive_report',
        kicker: 'Executive',
        title: 'Executive Report',
        tag: 'new',
        color: 'navy',
        href: '/executive-report',
        host: '/executive-report',
        desc: 'CEO-level company flows and NCNM forecast — appointment PAUM YoY, channel funnel, the 3-component end-of-month NCNM projection, and a GPT-4.1 executive summary.',
        icon: svg(<><path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" /><rect x="12" y="7" width="3" height="10" /><rect x="17" y="4" width="3" height="13" /></>),
      },
      {
        id: 'file_explorer',
        toolId: 'file_explorer',
        kicker: 'Data lake',
        title: 'File Explorer',
        tag: 'new',
        color: 'sky',
        href: '/file-explorer',
        host: '/file-explorer',
        desc: 'Download data-lake tables as CSV or tab-delimited text, with inline sharing — grant specific people or groups access to a folder or a single table.',
        icon: svg(<><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="M12 11v5" /><path d="m9.5 13.5 2.5-2.5 2.5 2.5" /></>),
      },
      {
        id: 'data_catalog',
        toolId: 'data_catalog',
        kicker: 'Data dictionary',
        title: 'Data Catalog',
        tag: 'new',
        color: 'navy',
        href: '/catalog/',
        host: '/catalog/',
        desc: 'Searchable dictionary of the tho warehouse — browse columns/fields and the tables they live in, explore joins and an ER graph, and inspect every table\'s schema.',
        icon: svg(<><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>),
      },
      {
        id: 'brief',
        toolId: 'brief',
        kicker: 'Executive inbox',
        title: 'Executive Brief',
        tag: 'new',
        color: 'navy',
        href: '/brief',
        host: '/brief',
        desc: 'CEO inbox operating system — decision-first email triage with AI summaries, a "what you might miss" panel, and quick-action reply drafting.',
        icon: svg(<><path d="M3 6h18v12H3z" /><path d="m3 7 9 6 9-6" /></>),
      },
      {
        id: 'sfp2',
        toolId: 'sfp2',
        kicker: 'Developer tool',
        title: 'Salesforce Column Updater',
        tag: 'live',
        color: 'sky',
        href: '/sfp2',
        host: '/sfp2',
        desc: 'Diff bronze Delta tables against the live Salesforce describe() and apply column schema updates — keeps the Salesforce ingestion schema in sync.',
        icon: svg(<><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h10" /><circle cx="18" cy="18" r="2" /></>),
      },
      {
        id: 'repcodes',
        toolId: 'repcodes',
        kicker: 'Reference data',
        title: 'Rep Codes',
        tag: 'live',
        color: 'teal',
        href: '/repcodes',
        host: '/repcodes',
        desc: 'Editable lookup table for advisor rep codes backed by Synapse — add, edit, and track recent changes to the rep-code mapping.',
        icon: svg(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18" /><path d="M8 4v16" /></>),
      },
    ],
  },
  {
    heading: 'Analytics & reports',
    blurb: 'Visual analytics, static exports, and partner-facing deliverables.',
    cards: [
      {
        id: 'heatmaps',
        kicker: 'Visual analytics',
        title: 'Heatmaps',
        tag: 'soon',
        color: 'sky',
        host: '—',
        desc: 'Density views for advisor activity, client engagement and portfolio drift — ties into ThoughtSpot liveboards.',
        icon: svg(<><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></>),
      },
      {
        id: 'html_reports',
        kicker: 'Ad-hoc',
        title: 'HTML Reports',
        tag: 'soon',
        color: 'slate',
        host: '—',
        desc: 'Drop-in viewer for static HTML exports — reconciliations, recon diffs, and one-off deliverables the team ships to partners.',
        icon: svg(<><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" /><path d="M14 3v6h6" /><path d="M8 13h8" /><path d="M8 17h6" /></>),
      },
      {
        id: 'reconciliations',
        kicker: 'Data quality',
        title: 'Reconciliations',
        tag: 'soon',
        color: 'teal',
        host: '—',
        desc: 'Cross-system flow and balance recon — Synapse vs. custodian, rollforward bridges, and drill-down to the row-level diffs.',
        icon: svg(<><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 3v6h-6" /></>),
      },
    ],
  },
  {
    heading: 'Utilities',
    blurb: 'Small internal apps and lookup tools spun up by the team.',
    cards: [
      {
        id: 'field_mapping',
        kicker: 'Developer tool',
        title: 'Field Mapping Explorer',
        tag: 'soon',
        color: 'orange',
        host: '—',
        desc: 'Navigate stored-procedure field lineage across rollforward, fact tables, and Tamarac.',
        icon: svg(<><path d="M3 6h18" /><path d="M3 12h18" /><path d="M3 18h18" /><circle cx="7" cy="6" r="1.2" fill="currentColor" /><circle cx="13" cy="12" r="1.2" fill="currentColor" /><circle cx="17" cy="18" r="1.2" fill="currentColor" /></>),
      },
      {
        id: 'custodian',
        kicker: 'Operations',
        title: 'Custodian Dashboard',
        tag: 'soon',
        color: 'slate',
        host: '—',
        desc: 'Monitor custodian feed health, trade volumes, and reconciliation breaks across Fidelity, Schwab, and internal.',
        icon: svg(<><path d="M3 9h18v10H3z" /><path d="M7 9V6a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v3" /></>),
      },
    ],
  },
  {
    heading: 'Admin',
    blurb: 'Access control and pipeline operations for the admin team.',
    cards: [
      {
        id: 'admin',
        toolId: 'admin',
        kicker: 'Access control',
        title: 'Admin',
        tag: 'new',
        color: 'slate',
        href: '/admin',
        host: '/admin',
        desc: 'Grant tool access by email, build groups, and let group access cascade to every member — one place to manage who can open which tool.',
        icon: svg(<><path d="M12 2 4 5v6c0 5 3.4 8.5 8 11 4.6-2.5 8-6 8-11V5z" /><circle cx="12" cy="10" r="2.4" /><path d="M8.5 16a3.7 3.7 0 0 1 7 0" /></>),
      },
      {
        id: 'app_usage',
        toolId: 'admin',
        kicker: 'Adoption',
        title: 'App Usage',
        tag: 'live',
        color: 'navy',
        href: '/app-usage',
        host: '/app-usage',
        desc: 'See which workspace tools people are using.',
        icon: svg(<><path d="M3 3v18h18" /><rect x="7" y="11" width="3" height="6" /><rect x="12" y="7" width="3" height="10" /><rect x="17" y="13" width="3" height="4" /></>),
      },
      {
        id: 'automations',
        toolId: 'admin',
        kicker: 'Operations',
        title: 'Automations',
        tag: 'live',
        color: 'sky',
        href: '/automations',
        host: '/automations',
        desc: 'Review and manage recurring workspace jobs.',
        icon: svg(<><path d="M12 2v4" /><path d="m16.2 7.8 2.9-2.9" /><path d="M18 12h4" /><circle cx="12" cy="12" r="4" /><path d="M4.9 4.9 7.8 7.8" /><path d="M2 12h4" /></>),
      },
      {
        id: 'pipeline_logging',
        toolId: 'pipeline_logging',
        kicker: 'Pipeline observability',
        title: 'Tamarac',
        tag: 'live',
        color: 'sky',
        href: '/tamarac',
        host: '/tamarac',
        desc: 'Inspect Tamarac ingestion and transformation runs.',
        icon: svg(<><path d="M4 7h10" /><path d="M4 12h16" /><path d="M4 17h7" /><circle cx="18" cy="7" r="2" /><circle cx="14" cy="17" r="2" /></>),
      },
      {
        id: 'refresh_log',
        toolId: 'pipeline_logging',
        kicker: 'Pipeline history',
        title: 'Full Log',
        tag: 'live',
        color: 'slate',
        href: '/refresh_log',
        host: '/refresh_log',
        desc: 'Review complete refresh and transformation history.',
        icon: svg(<><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 3v6h-6" /></>),
      },
    ],
  },
];

const arrow = (
  <svg className="hub-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></svg>
);

const cardSummary: Record<string, string> = {
  performance: 'Review growth against plan across every acquisition channel.',
  nfbc: 'Review, edit, and confirm proposed flow adjustments.',
  fee_calculator: 'Compare fee schedules and calculate client pricing.',
  pipeline_review: 'Focus the team on the prospects that need attention now.',
  executive_report: 'See company flows, forecasts, and the executive summary.',
  crm: 'Find clients, activity, opportunities, and advisor relationships.',
  file_explorer: 'Find, download, and share approved data-lake tables.',
  data_catalog: 'Understand warehouse fields, tables, and relationships.',
  brief: 'Triage the executive inbox and prepare decision-ready replies.',
  financial_planning: 'Build and compare retirement, tax, and estate scenarios.',
  avantos: 'Review acquisition-channel performance and growth trends.',
  rebalancer: 'Model portfolio rebalancing decisions before execution.',
  sfp2: 'Keep Salesforce ingestion columns aligned with the live schema.',
  repcodes: 'Maintain advisor rep-code mappings and review changes.',
  bond_analyzer: 'Analyze fixed-income holdings and build proposals.',
  advisor_mailer: 'Review and send advisor communications in batches.',
  admin: 'Manage who can view and share each workspace tool.',
  app_usage: 'See which workspace tools people are using.',
  automations: 'Review and manage recurring workspace jobs.',
  pipeline_logging: 'Inspect Tamarac ingestion and transformation runs.',
  refresh_log: 'Review complete refresh and transformation history.',
};

const ACCOUNT_WIDGET_PRIORITY = [
  'performance',
  'executive_report',
  'pipeline_review',
  'brief',
];

function accountName(email: string | null | undefined): string {
  if (!email) return 'this account';
  const local = email.split('@')[0] ?? '';
  if (local.toLowerCase() === 'demo') return 'Demo user';
  const words = local.split(/[._-]+/).filter(Boolean).slice(0, 2);
  if (!words.length) return email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
}

function AccountToolWidget({ card }: { card: HubCard }) {
  return (
    <a className="hub-tool-widget" href={card.href}>
      <div className="hub-tool-widget-head">
        <span className="hub-tool-widget-rule" aria-hidden="true" />
        <span className="hub-card-icon">{card.icon}</span>
        <span className="hub-tool-widget-kicker">{card.kicker}</span>
      </div>
      <h3>{card.title}</h3>
      <p>{cardSummary[card.id] ?? card.desc}</p>
      <span className="hub-tool-widget-action">
        Open tool
        {arrow}
      </span>
    </a>
  );
}

function Card({ card }: { card: HubCard }) {
  const disabled = !card.href;
  const body = (
    <>
      <div className="hub-card-top">
        <span className="hub-card-icon">{card.icon}</span>
        <div className="hub-card-title-wrap">
          <div className="hub-card-title">{card.title}</div>
          <div className="hub-card-desc">{cardSummary[card.id] ?? card.desc}</div>
        </div>
        {disabled ? <span className="hub-card-status">In planning</span> : arrow}
      </div>
    </>
  );

  if (disabled) {
    return (
      <div className="hub-card disabled" aria-disabled="true">
        {body}
      </div>
    );
  }
  return (
    <a className="hub-card" href={card.href}>
      {body}
    </a>
  );
}

export default function Home() {
  const access = useEffectiveAccess();
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

  // Filter each section's cards to those the (possibly impersonated) user can
  // reach. Placeholder "soon" cards have no toolId and are always shown.
  const visibleSections = useMemo(
    () =>
      SECTIONS.map((section) => ({
        ...section,
        cards: section.cards.filter((c) => canAccessTool(access, c.toolId)),
      })).filter((section) => section.cards.length > 0),
    [access]
  );

  const availableSections = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return visibleSections.map((section) => ({
      ...section,
      cards: section.cards.filter((card) => {
        if (!card.href) return false;
        if (!needle) return true;
        return `${card.title} ${card.kicker} ${card.desc}`.toLowerCase().includes(needle);
      }),
    })).filter((section) => section.cards.length > 0);
  }, [query, visibleSections]);

  const planningCards = useMemo(
    () => visibleSections.flatMap((section) => section.cards).filter((card) => !card.href),
    [visibleSections]
  );
  const availableCount = visibleSections.flatMap((section) => section.cards).filter((card) => card.href).length;
  const resultCount = availableSections.reduce((total, section) => total + section.cards.length, 0);
  const accountWidgets = useMemo(() => {
    const available = visibleSections.flatMap((section) => section.cards).filter((card) => card.href);
    const preferred = ACCOUNT_WIDGET_PRIORITY
      .map((id) => available.find((card) => card.id === id))
      .filter((card): card is HubCard => Boolean(card));
    const remainder = available.filter((card) => !preferred.some((item) => item.id === card.id));
    return [...preferred, ...remainder].slice(0, 4);
  }, [visibleSections]);

  return (
    <div className="home-hub has-sidenav">
      <SideNav />

      <div className="hub-main">
        <div className="hub-inner">
          <header className="hub-intro">
            <p className="hub-eyebrow">Allworth workspace</p>
            <h1>What do you need to do?</h1>
            <div className="hub-search">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
              <input
                ref={searchInput}
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Find a tool or report"
                aria-label="Find a tool or report"
              />
              {!query && <kbd>/</kbd>}
            </div>
            <p className="hub-availability">{query ? `${resultCount} matching ${resultCount === 1 ? 'tool' : 'tools'}` : `${availableCount} tools available to you`}</p>
          </header>

          {!query && accountWidgets.length > 0 && (
            <section className="hub-account-widgets" aria-labelledby="hub-account-tools-title">
              <div className="hub-account-widgets-head">
                <div>
                  <p className="hub-account-label">Account dashboard</p>
                  <h2 id="hub-account-tools-title">Your tools</h2>
                </div>
                <p>
                  {accountName(access?.email)} · {access?.all ? 'all tools enabled' : `${availableCount} enabled`}
                </p>
              </div>
              <div className="hub-account-widget-grid">
                {accountWidgets.map((card) => <AccountToolWidget key={card.id} card={card} />)}
              </div>
            </section>
          )}

          {availableSections.map((section) => (
              <div key={section.heading}>
                <div className="hub-section-head">
                  <div>
                    <h2>{section.heading}</h2>
                  </div>
                </div>
                <div className="hub-card-grid">
                  {section.cards.map((card) => (
                    <Card key={card.id} card={card} />
                  ))}
                </div>
              </div>
          ))}

          {query && resultCount === 0 && (
            <div className="hub-empty">
              <h2>No tools found</h2>
              <p>Try a task, report name, or data source.</p>
              <button type="button" onClick={() => { setQuery(''); searchInput.current?.focus(); }}>Clear search</button>
            </div>
          )}

          {!query && planningCards.length > 0 && (
            <details className="hub-planning">
              <summary>In planning <span>{planningCards.length}</span></summary>
              <div className="hub-card-grid">
                {planningCards.map((card) => <Card key={card.id} card={card} />)}
              </div>
            </details>
          )}
        </div>

        <div className="hub-footer">
          <span><strong>Allworth Financial</strong></span>
          <span>Internal workspace</span>
        </div>
      </div>
    </div>
  );
}
