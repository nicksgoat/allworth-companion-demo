import { StrictMode, Suspense, lazy, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './theme.css';
import './index.css';
import Home from './Home';
import SideNav from './components/SideNav';
import PageTracker from './components/PageTracker';
import type { KpiDataset } from './types/kpi';
import type { ThoughtSpotCell, ThoughtSpotRenderContext } from './types/thoughtspot';
import { fetchAllMetrics } from './services/api';
import { adminApi } from './services/admin';
import {
  ensureAuthenticated,
  installAuthFetch,
} from './services/auth';
import { demoMetrics } from './data/demoMetrics';
import { WorkspaceProvider } from './components/WorkspaceContext';

// Tool pages load only after their route is opened. This keeps page-specific
// charting, editor, and data-grid dependencies out of the initial workspace.
const RefreshLog = lazy(() => import('./RefreshLog'));
const Reporting = lazy(() => import('./Reporting'));
const EmbedApp = lazy(() => import('./EmbedApp'));
const Tamarac2 = lazy(() => import('./Tamarac2'));
const Sfp2 = lazy(() => import('./Sfp2'));
const Repcodes = lazy(() => import('./Repcodes'));
const Nfbc = lazy(() => import('./nfbc/Nfbc'));
const Admin = lazy(() => import('./Admin'));
const AppUsage = lazy(() => import('./AppUsage'));
const Automations = lazy(() => import('./Automations'));
const FeeCalculator = lazy(() => import('./FeeCalculator'));
const PipelineReview = lazy(() => import('./PipelineReview'));
const ExecutiveReport = lazy(() => import('./ExecutiveReport'));
const Crm = lazy(() => import('./Crm'));
const FileExplorer = lazy(() => import('./FileExplorer'));
const Brief = lazy(() => import('./brief/Brief'));
const BondAnalyzer = lazy(() => import('./BondAnalyzer'));
const EmailBatchApp = lazy(() => import('./EmailBatchApp'));
const PlanningApp = lazy(() => import('./PlanningApp'));
const Avantos = lazy(() => import('./Avantos'));
const Rebalancer = lazy(() => import('./Rebalancer'));

const lazyPage = (node: ReactNode) => (
  <Suspense fallback={<div className="lazy-page-loading" aria-label="Loading tool" />}>{node}</Suspense>
);

// Local preview mode: when VITE_DEMO_MODE=true the app renders bundled demo
// data with NO authentication and NO backend/Synapse connection.  Used for the
// `npm run dev:demo` workflow so visual changes can be previewed offline.
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root not found');
}

const root = createRoot(container);

// ---------------------------------------------------------------------------
// "View as user" floating revert control. Rendered on every SPA route so an
// admin who impersonated a user from /admin can return to their own view from
// anywhere. Reads the session overlay written by the Admin page.
// ---------------------------------------------------------------------------
const IMPERSONATION_KEY = 'allworth-impersonation';
const IMPERSONATION_EVENT = 'allworth-impersonation-change';

function readImpersonation(): { email: string; tools: string[] } | null {
  try {
    const raw = sessionStorage.getItem(IMPERSONATION_KEY);
    return raw ? (JSON.parse(raw) as { email: string; tools: string[] }) : null;
  } catch {
    return null;
  }
}

function ImpersonationBar() {
  const [imp, setImp] = useState(readImpersonation());
  useEffect(() => {
    const sync = () => setImp(readImpersonation());
    window.addEventListener(IMPERSONATION_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(IMPERSONATION_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  if (!imp) return null;

  const revert = () => {
    try {
      sessionStorage.removeItem(IMPERSONATION_KEY);
    } catch {
      /* ignore */
    }
    window.dispatchEvent(new CustomEvent(IMPERSONATION_EVENT));
  };

  return (
    <button
      type="button"
      className="impersonation-bar"
      onClick={revert}
      title="Return to your own view"
    >
      <span className="impersonation-dot" />
      <span className="impersonation-text">
        Viewing as <strong>{imp.email}</strong>
      </span>
      <span className="impersonation-revert">Revert view</span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Tool/page access gate. While "viewing as" another user (impersonation), a
// route whose tool id is NOT in that user's effective access renders the
// no-access notice. Otherwise the real signed-in user's effective access
// (fetched once from /api/admin/me) is enforced. Lookup failures fail closed
// with a retry state so an outage cannot become an implicit grant.
// ---------------------------------------------------------------------------
interface MeAccess {
  effective: Set<string>;
  all: boolean;
  unavailable?: boolean;
}
let meCache: MeAccess | null = null;
let mePromise: Promise<void> | null = null;
function loadMe(): Promise<void> {
  if (!mePromise) {
    mePromise = adminApi
      .getMe()
      .then((m) => {
        meCache = { effective: new Set(m.effective_tools), all: m.all_access };
      })
      .catch(() => {
        // Fail closed: an access-service outage must not become an implicit
        // all-tools grant. The user gets a retryable availability state.
        meCache = { effective: new Set(), all: false, unavailable: true };
      });
  }
  return mePromise;
}

function NoAccess() {
  return (
    <div className="no-access has-sidenav">
      <SideNav />
      <div className="no-access-card">
        <div className="no-access-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="10" width="16" height="10" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>
        </div>
        <h1>You do not have access</h1>
        <p>
          Please send an email to{' '}
          <a href="mailto:AnalyticsAndInsights@allworthfinancial.com?subject=Tool%20access%20request">
            AnalyticsAndInsights@allworthfinancial.com
          </a>{' '}
          to request access.
        </p>
      </div>
    </div>
  );
}

function AccessUnavailable() {
  return (
    <div className="no-access has-sidenav">
      <SideNav />
      <div className="no-access-card">
        <h1>Access check unavailable</h1>
        <p>We could not verify your workspace permissions. Refresh to try again.</p>
        <button type="button" onClick={() => window.location.reload()}>Refresh</button>
      </div>
    </div>
  );
}

function ToolGuard({ toolId, children }: { toolId: string; children: ReactNode }) {
  const [imp, setImp] = useState(readImpersonation());
  const [me, setMe] = useState<MeAccess | null>(meCache);
  useEffect(() => {
    const sync = () => setImp(readImpersonation());
    window.addEventListener(IMPERSONATION_EVENT, sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener(IMPERSONATION_EVENT, sync);
      window.removeEventListener('storage', sync);
    };
  }, []);
  useEffect(() => {
    if (meCache) {
      setMe(meCache);
    } else {
      void loadMe().then(() => setMe(meCache));
    }
  }, []);

  // Impersonation ("view as") takes precedence over the real user's access.
  if (imp) {
    return imp.tools.includes(toolId) ? <>{children}</> : <NoAccess />;
  }
  // Real signed-in user. Wait for the access lookup, then enforce.
  if (me === null) return null;
  if (me.unavailable) return <AccessUnavailable />;
  if (me.all || me.effective.has(toolId)) return <>{children}</>;
  return <NoAccess />;
}

interface AppRoutesProps {
  metrics: KpiDataset;
  netFlowsMetrics?: KpiDataset;
  detailedMetrics?: KpiDataset;
  isLoading?: boolean;
  fallback: 'home' | 'reporting';
}

function AppRoutes({ metrics, netFlowsMetrics = [], detailedMetrics = [], isLoading = false, fallback }: AppRoutesProps) {
  const tool = (toolId: string, node: ReactNode) => (
    <ToolGuard toolId={toolId}>{lazyPage(node)}</ToolGuard>
  );
  const reporting = (
    <ToolGuard toolId="performance">
      {lazyPage(<Reporting metrics={metrics} netFlowsMetrics={netFlowsMetrics} detailedMetrics={detailedMetrics} isLoading={isLoading} />)}
    </ToolGuard>
  );

  return (
    <Routes>
      <Route path="/embed" element={lazyPage(<EmbedApp metrics={metrics} netFlowsMetrics={netFlowsMetrics} detailedMetrics={detailedMetrics} />)} />
      <Route path="/" element={<Home />} />
      <Route path="/home" element={<Home />} />
      <Route path="/refresh_log" element={tool('pipeline_logging', <RefreshLog />)} />
      <Route path="/refresh-log" element={tool('pipeline_logging', <RefreshLog />)} />
      <Route path="/tamarac" element={tool('pipeline_logging', <Tamarac2 />)} />
      <Route path="/sfp2" element={tool('sfp2', <Sfp2 />)} />
      <Route path="/repcodes" element={tool('repcodes', <Repcodes />)} />
      <Route path="/nfbc" element={tool('nfbc', <Nfbc />)} />
      <Route path="/fee-calculator" element={tool('fee_calculator', <FeeCalculator />)} />
      <Route path="/pipeline-review" element={tool('pipeline_review', <PipelineReview />)} />
      <Route path="/executive-report" element={tool('executive_report', <ExecutiveReport />)} />
      <Route path="/crm" element={tool('crm', <Crm />)} />
      <Route path="/file-explorer" element={tool('file_explorer', <FileExplorer />)} />
      <Route path="/brief" element={tool('brief', <Brief />)} />
      <Route path="/bond-analyzer" element={tool('bond_analyzer', <BondAnalyzer />)} />
      <Route path="/advisor-mailer" element={tool('advisor_mailer', <EmailBatchApp />)} />
      <Route path="/planning" element={tool('financial_planning', <PlanningApp />)} />
      <Route path="/avantos" element={tool('avantos', <Avantos />)} />
      <Route path="/rebalancer" element={tool('rebalancer', <Rebalancer />)} />
      <Route path="/admin" element={tool('admin', <Admin />)} />
      <Route path="/app-usage" element={tool('admin', <AppUsage />)} />
      <Route path="/automations" element={tool('admin', <Automations />)} />
      <Route path="/reporting/kpi" element={reporting} />
      <Route path="*" element={fallback === 'home' ? <Home /> : reporting} />
    </Routes>
  );
}

// -------------------------------------------------------------------------
// Pipeline-observability pages (/refresh_log, /tamarac) — standalone, backed
// by the ADLS Gen2 Delta table. Rendered BEFORE any Synapse fetch so a Synapse
// outage cannot block them.
// -------------------------------------------------------------------------
const isPipelinePath = (() => {
  // Demo preview always routes through bootstrap (which renders demo data with
  // no auth), so these standalone pages must not short-circuit it.
  if (DEMO_MODE) return false;
  try {
    const p = window.location.pathname.replace(/\/+$/, '');
    return (
      p === '' ||
      p === '/home' ||
      p === '/refresh_log' ||
      p === '/refresh-log' ||
      p === '/tamarac' ||
      p === '/sfp2' ||
      p === '/repcodes' ||
      p === '/nfbc' ||
      p === '/fee-calculator' ||
      p === '/pipeline-review' ||
      p === '/executive-report' ||
      p === '/file-explorer' ||
      p === '/brief' ||
      p === '/admin' ||
      p === '/app-usage' ||
      p === '/automations'
    );
  } catch {
    return false;
  }
})();

if (isPipelinePath) {
  // Gate the pipeline pages behind SSO before rendering – they make API
  // calls (refresh log, sfp2, etc.) that the backend will reject without a
  // valid bearer token.
  void (async () => {
    await ensureAuthenticated();
    installAuthFetch();
    root.render(
      <StrictMode>
        <BrowserRouter>
          <WorkspaceProvider>
            <AppRoutes metrics={[]} fallback="home" />
            <PageTracker />
            <ImpersonationBar />
          </WorkspaceProvider>
        </BrowserRouter>
      </StrictMode>
    );
  })();
}

const renderApp = (metrics: KpiDataset, netFlowsMetrics?: KpiDataset, detailedMetrics?: KpiDataset, isLoading = false) => {
  const nf = netFlowsMetrics || [];
  const dm = detailedMetrics || [];
  root.render(
    <StrictMode>
      <BrowserRouter>
        <WorkspaceProvider>
          <AppRoutes metrics={metrics} netFlowsMetrics={nf} detailedMetrics={dm} isLoading={isLoading} fallback="reporting" />
          <PageTracker />
          <ImpersonationBar />
        </WorkspaceProvider>
      </BrowserRouter>
    </StrictMode>
  );
};

const coerceNumber = (value: ThoughtSpotCell): number | undefined => {
  if (value == null) return undefined;
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined;
  if (typeof value === 'string') {
    const normalized = value.replace(/[%,$\s]/g, '');
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  if (typeof value === 'object') {
    const asAny = value as { value?: unknown };
    if (typeof asAny.value === 'number') return asAny.value;
    if (typeof asAny.value === 'string') return coerceNumber(asAny.value);
  }
  return undefined;
};

const coerceString = (value: ThoughtSpotCell): string | undefined => {
  if (value == null) return undefined;
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return value.toString();
  if (typeof value === 'object') {
    const asAny = value as { formattedValue?: unknown; value?: unknown };
    if (typeof asAny.formattedValue === 'string') return asAny.formattedValue;
    if (typeof asAny.value === 'string') return asAny.value;
  }
  return undefined;
};

const normalizeHeader = (header: string) => header.trim().toLowerCase();

const parseMetricsFromRows = (rows: ThoughtSpotCell[][]): KpiDataset => {
  if (!Array.isArray(rows) || rows.length === 0) return [];

  const potentialHeader = rows[0]?.map(coerceString) ?? [];
  const hasHeader = potentialHeader.every((cell) => typeof cell === 'string' && cell.length > 0);

  const header = hasHeader ? potentialHeader.map((cell) => normalizeHeader(cell ?? '')) : [];
  const dataRows = hasHeader ? rows.slice(1) : rows;

  const headerIndex = (aliases: string[], fallback: number) => {
    if (!header.length) return fallback;
    for (const alias of aliases) {
      const idx = header.findIndex((value) => value.includes(alias));
      if (idx >= 0) return idx;
    }
    return fallback;
  };

  const metricIndex = headerIndex(['metric', 'label', 'name'], 0);
  const channelIndex = headerIndex(['channel', 'segment', 'group'], 1);
  const periodIndex = headerIndex(['monthly date', 'month', 'period'], 2);
  const actualIndex = headerIndex(['total actual', 'actual', 'value', 'current'], 3);
  const goalIndex = headerIndex(['total goal', 'goal'], 4);
  const targetIndex = headerIndex(['target'], 5);
  const budgetIndex = headerIndex(['budget'], 6);
  const currencyIndex = headerIndex(['currency', 'curr'], 7);
  const unitIndex = headerIndex(['unit', 'measurement'], 8);

  const getNumber = (row: ThoughtSpotCell[], index: number) =>
    index >= 0 && index < row.length ? coerceNumber(row[index]) : undefined;
  const getString = (row: ThoughtSpotCell[], index: number) =>
    index >= 0 && index < row.length ? coerceString(row[index]) : undefined;
  const slugify = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

  const entries: KpiDataset = [];

  dataRows.forEach((row, rowIndex) => {
    const metric = getString(row, metricIndex)?.trim();
    const channel = getString(row, channelIndex)?.trim();
    const period = getString(row, periodIndex)?.trim() ?? 'Unspecified Period';
    const actual = getNumber(row, actualIndex);
    const goalRaw = getNumber(row, goalIndex);
    const target = getNumber(row, targetIndex);
    const budget = getNumber(row, budgetIndex);
    const goal = goalRaw ?? target ?? budget;

    if (!metric || !channel || actual == null || goal == null) {
      return;
    }

    const currency = getString(row, currencyIndex)?.trim();
    const unit = getString(row, unitIndex)?.trim();
    const id = `${slugify(metric) || 'metric'}-${slugify(channel) || rowIndex}-${slugify(period) || 'period'}`;

    const entry: KpiDataset[number] = {
      id,
      metric,
      channel,
      period,
      actual,
      goal,
      ...(target != null ? { target } : {}),
      ...(budget != null ? { budget } : {}),
      ...(currency ? { currency } : {}),
      ...(unit ? { unit } : {})
    };

    entries.push(entry);
  });

  return entries;
};

const renderError = (message: string) => {
  const container = document.getElementById('root');
  if (container) {
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#f3f4f4;color:#171717;font-family:Lato,system-ui,sans-serif;padding:2rem;text-align:center;">
        <p style="margin:0 0 10px;color:#a63d35;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;">Workspace unavailable</p>
        <h1 style="font-family:'Playfair Display',Georgia,serif;font-size:2rem;font-weight:600;margin:0 0 .75rem;color:#0c2e4e;">Unable to load the workspace</h1>
        <p style="color:#595959;max-width:420px;margin:0 0 1.5rem;line-height:1.55;">${message}</p>
        <button onclick="location.reload()" style="padding:.7rem 1.1rem;background:#173d67;color:white;border:none;border-radius:10px;cursor:pointer;font:700 .9rem Lato,system-ui,sans-serif;">Try again</button>
      </div>
    `;
  }
};

const renderLoading = (statusMessage: string = 'Connecting to database...') => {
  const container = document.getElementById('root');
  if (container) {
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#f3f4f4;color:#171717;font-family:Lato,system-ui,sans-serif;padding:2rem;text-align:center;">
        <p style="margin:0 0 10px;color:#3e71b7;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;">Allworth Financial</p>
        <h1 style="font-family:'Playfair Display',Georgia,serif;font-size:2rem;font-weight:600;margin:0 0 .75rem;color:#0c2e4e;">Opening your workspace</h1>
        <p id="loading-status" role="status" style="color:#595959;font-size:.95rem;margin:0;">${statusMessage}</p>
      </div>
    `;
  }
};

const updateLoadingStatus = (message: string) => {
  const statusEl = document.getElementById('loading-status');
  if (statusEl) {
    statusEl.textContent = message;
  }
};

const bootstrap = async () => {
  // Show loading screen immediately
  renderLoading('Initializing...');
  
  console.log('🚀 Allworth Executive Reporting Bootstrap Starting...');
  console.log('📍 API Base URL:', import.meta.env.VITE_API_URL || 'http://localhost:5000/api');

  // Local preview mode — render bundled demo data with no auth and no backend.
  if (DEMO_MODE) {
    console.log('🎭 DEMO_MODE enabled — rendering bundled demo metrics (no auth, no backend)');
    renderApp(demoMetrics);
    return;
  }

  // Check if embedded in ThoughtSpot
  const isEmbedded = (() => {
    try {
      return window.self !== window.top;
    } catch (error) {
      console.warn('Unable to determine embedding context', error);
      return true;
    }
  })();

  console.log(`🔍 Embedded mode: ${isEmbedded}`);

  // SSO gate – redirects to login.microsoftonline.com if not signed in.  This
  // never resolves when redirecting; the page navigates away and re-enters
  // bootstrap after the redirect callback.
  updateLoadingStatus('Checking sign-in...');
  await ensureAuthenticated();
  installAuthFetch();

  // Strategy 1: Try fetching from backend API (single combined request)
  try {
    console.log('1️⃣ Strategy 1: Fetching all metrics from backend API...');

    // Render the page shell immediately so the hero/controls are visible while
    // the KPI matrix waits on the data fetch (only that region shows loading).
    renderApp([], [], [], true);

    const bundle = await fetchAllMetrics();
    console.log(`   📊 Received ${bundle.kpiMetrics.length} KPI, ${bundle.netFlows.length} net-flows, ${bundle.detailedMetrics.length} detailed metrics`);

    if (bundle.kpiMetrics.length > 0) {
      console.log('   🎉 SUCCESS! Rendering dashboard');
      renderApp(bundle.kpiMetrics, bundle.netFlows, bundle.detailedMetrics);
      return;
    } else {
      console.warn('   ⚠️ API returned 0 KPI metrics');
      renderError('The database query returned no data. Please check your Synapse connection and query.');
      return;
    }
  } catch (error) {
    console.error('❌ Backend API fetch failed:', error);
    renderError(`Failed to fetch metrics: ${error instanceof Error ? error.message : 'Unknown error'}`);
    // Don't return – fall through to ThoughtSpot strategy
  }

  // Strategy 2: Try ThoughtSpot SDK if embedded
  if (isEmbedded) {
    console.log('2️⃣ Strategy 2: Attempting ThoughtSpot SDK...');
    try {
      console.log('   Initializing ThoughtSpot context...');
      const { getChartContext } = await import('@thoughtspot/ts-chart-sdk');
      await getChartContext({
        getDefaultChartConfig: () => [
          {
            key: 'default',
            dimensions: []
          }
        ],
        getQueriesFromChartConfig: () => [],
        renderChart: async (context: unknown) => {
          const rows = (context as ThoughtSpotRenderContext)?.data ?? [];
          console.log(`   ThoughtSpot returned ${rows.length} rows`);
          const metrics = parseMetricsFromRows(rows);
          if (metrics.length === 0) {
            console.warn('   ⚠️ ThoughtSpot returned no metrics');
            renderError('ThoughtSpot returned no data. Please check your worksheet configuration.');
          } else {
            console.log(`   🎉 SUCCESS! Loaded ${metrics.length} metrics from ThoughtSpot`);
            renderApp(metrics);
          }
        }
      });
      return;
    } catch (error) {
      console.error('❌ ThoughtSpot SDK initialization failed:', error);
    }
  } else {
    console.log('⏭️  Skipping ThoughtSpot (not embedded)');
  }

  // No data source available - show error
  console.error('❌ All data sources failed');
  renderError('Unable to connect to backend API. Please ensure the Flask server is running on port 5000.');
};

// Skip the Synapse bootstrap entirely on the pipeline-observability pages —
// those render themselves immediately above and must not depend on Synapse.
if (!isPipelinePath) {
  void bootstrap();
}
