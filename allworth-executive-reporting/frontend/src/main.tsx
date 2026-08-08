import { StrictMode, Suspense, lazy, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import './theme.css';
import './index.css';
import Reporting from './Reporting';
import EmbedApp from './EmbedApp';
import RefreshLog from './RefreshLog';
import Tamarac2 from './Tamarac2';
import Sfp2 from './Sfp2';
import Repcodes from './Repcodes';
import Nfbc from './nfbc/Nfbc';
import Admin from './Admin';
import AppUsage from './AppUsage';
import Automations from './Automations';
import FeeCalculator from './FeeCalculator';
import PipelineReview from './PipelineReview';
import ExecutiveReport from './ExecutiveReport';
import Crm from './Crm';
import FileExplorer from './FileExplorer';
import Brief from './brief/Brief';
import Home from './Home';
import SideNav from './components/SideNav';
import PageTracker from './components/PageTracker';
import type { KpiDataset, PredictionsPayload } from './types/kpi';
import { getChartContext } from '@thoughtspot/ts-chart-sdk';
import type { ThoughtSpotCell, ThoughtSpotRenderContext } from './types/thoughtspot';
import { fetchAllMetrics } from './services/api';
import { adminApi } from './services/admin';
import {
  ensureAuthenticated,
  installAuthFetch,
} from './services/auth';
import { demoMetrics, demoNetFlows, demoPredictions } from './data/demoMetrics';

// MUI-based tools are code-split so the (large) MUI runtime is only fetched
// when one of these routes is opened.
const BondAnalyzer = lazy(() => import('./BondAnalyzer'));
const EmailBatchApp = lazy(() => import('./EmailBatchApp'));
const PlanningApp = lazy(() => import('./PlanningApp'));
const Avantos = lazy(() => import('./Avantos'));
const Rebalancer = lazy(() => import('./Rebalancer'));

const lazyPage = (node: ReactNode) => (
  <Suspense fallback={<div className="lazy-page-loading" />}>{node}</Suspense>
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
// (fetched once from /api/admin/me) is enforced. Fails OPEN on lookup error so
// a backend hiccup can't lock everyone out.
// ---------------------------------------------------------------------------
interface MeAccess {
  effective: Set<string>;
  all: boolean;
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
        // Fail open: if access can't be resolved, don't lock the user out.
        meCache = { effective: new Set(), all: true };
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
  if (me.all || me.effective.has(toolId)) return <>{children}</>;
  return <NoAccess />;
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
      p === '/crm' ||
      p === '/file-explorer' ||
      p === '/brief' ||
      p === '/bond-analyzer' ||
      p === '/advisor-mailer' ||
      p === '/planning' ||
      p === '/avantos' ||
      p === '/rebalancer' ||
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
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/home" element={<Home />} />
            <Route path="/refresh_log" element={<ToolGuard toolId="pipeline_logging"><RefreshLog /></ToolGuard>} />
            <Route path="/refresh-log" element={<ToolGuard toolId="pipeline_logging"><RefreshLog /></ToolGuard>} />
            <Route path="/tamarac" element={<ToolGuard toolId="pipeline_logging"><Tamarac2 /></ToolGuard>} />
            <Route path="/sfp2" element={<ToolGuard toolId="sfp2"><Sfp2 /></ToolGuard>} />
            <Route path="/repcodes" element={<ToolGuard toolId="repcodes"><Repcodes /></ToolGuard>} />
            <Route path="/nfbc" element={<ToolGuard toolId="nfbc"><Nfbc /></ToolGuard>} />
            <Route path="/fee-calculator" element={<ToolGuard toolId="fee_calculator"><FeeCalculator /></ToolGuard>} />
            <Route path="/pipeline-review" element={<ToolGuard toolId="pipeline_review"><PipelineReview /></ToolGuard>} />
            <Route path="/executive-report" element={<ToolGuard toolId="executive_report"><ExecutiveReport /></ToolGuard>} />
            <Route path="/crm" element={<ToolGuard toolId="crm"><Crm /></ToolGuard>} />
            <Route path="/file-explorer" element={<ToolGuard toolId="file_explorer"><FileExplorer /></ToolGuard>} />
            <Route path="/brief" element={<ToolGuard toolId="brief"><Brief /></ToolGuard>} />
            <Route path="/bond-analyzer" element={<ToolGuard toolId="bond_analyzer">{lazyPage(<BondAnalyzer />)}</ToolGuard>} />
            <Route path="/advisor-mailer" element={<ToolGuard toolId="advisor_mailer">{lazyPage(<EmailBatchApp />)}</ToolGuard>} />
            <Route path="/planning" element={<ToolGuard toolId="financial_planning">{lazyPage(<PlanningApp />)}</ToolGuard>} />
            <Route path="/avantos" element={<ToolGuard toolId="avantos">{lazyPage(<Avantos />)}</ToolGuard>} />
            <Route path="/rebalancer" element={<ToolGuard toolId="rebalancer">{lazyPage(<Rebalancer />)}</ToolGuard>} />
            <Route path="/admin" element={<ToolGuard toolId="admin"><Admin /></ToolGuard>} />
            <Route path="/app-usage" element={<ToolGuard toolId="admin"><AppUsage /></ToolGuard>} />
            <Route path="/automations" element={<ToolGuard toolId="admin"><Automations /></ToolGuard>} />
            <Route path="*" element={<Home />} />
          </Routes>
          <PageTracker />
          <ImpersonationBar />
        </BrowserRouter>
      </StrictMode>
    );
  })();
}

const renderApp = (metrics: KpiDataset, netFlowsMetrics?: KpiDataset, detailedMetrics?: KpiDataset, isLoading = false, predictions?: PredictionsPayload) => {
  const nf = netFlowsMetrics || [];
  const dm = detailedMetrics || [];
  root.render(
    <StrictMode>
      <BrowserRouter>
        <Routes>
          <Route path="/embed" element={<EmbedApp metrics={metrics} netFlowsMetrics={nf} detailedMetrics={dm} />} />
          <Route path="/" element={<Home />} />
          <Route path="/home" element={<Home />} />
          <Route path="/refresh_log" element={<ToolGuard toolId="pipeline_logging"><RefreshLog /></ToolGuard>} />
          <Route path="/refresh-log" element={<ToolGuard toolId="pipeline_logging"><RefreshLog /></ToolGuard>} />
          <Route path="/tamarac" element={<ToolGuard toolId="pipeline_logging"><Tamarac2 /></ToolGuard>} />
          <Route path="/sfp2" element={<ToolGuard toolId="sfp2"><Sfp2 /></ToolGuard>} />
          <Route path="/repcodes" element={<ToolGuard toolId="repcodes"><Repcodes /></ToolGuard>} />
          <Route path="/nfbc" element={<ToolGuard toolId="nfbc"><Nfbc /></ToolGuard>} />
          <Route path="/fee-calculator" element={<ToolGuard toolId="fee_calculator"><FeeCalculator /></ToolGuard>} />
          <Route path="/pipeline-review" element={<ToolGuard toolId="pipeline_review"><PipelineReview /></ToolGuard>} />
          <Route path="/executive-report" element={<ToolGuard toolId="executive_report"><ExecutiveReport /></ToolGuard>} />
          <Route path="/crm" element={<ToolGuard toolId="crm"><Crm /></ToolGuard>} />
          <Route path="/file-explorer" element={<ToolGuard toolId="file_explorer"><FileExplorer /></ToolGuard>} />
          <Route path="/brief" element={<ToolGuard toolId="brief"><Brief /></ToolGuard>} />
          <Route path="/bond-analyzer" element={<ToolGuard toolId="bond_analyzer">{lazyPage(<BondAnalyzer />)}</ToolGuard>} />
          <Route path="/advisor-mailer" element={<ToolGuard toolId="advisor_mailer">{lazyPage(<EmailBatchApp />)}</ToolGuard>} />
          <Route path="/planning" element={<ToolGuard toolId="financial_planning">{lazyPage(<PlanningApp />)}</ToolGuard>} />
          <Route path="/avantos" element={<ToolGuard toolId="avantos">{lazyPage(<Avantos />)}</ToolGuard>} />
          <Route path="/admin" element={<ToolGuard toolId="admin"><Admin /></ToolGuard>} />
          <Route path="/app-usage" element={<ToolGuard toolId="admin"><AppUsage /></ToolGuard>} />
          <Route path="/automations" element={<ToolGuard toolId="admin"><Automations /></ToolGuard>} />
          <Route path="/reporting/kpi" element={<ToolGuard toolId="performance"><Reporting metrics={metrics} netFlowsMetrics={nf} detailedMetrics={dm} isLoading={isLoading} predictions={predictions} /></ToolGuard>} />
          <Route path="*" element={<ToolGuard toolId="performance"><Reporting metrics={metrics} netFlowsMetrics={nf} detailedMetrics={dm} isLoading={isLoading} predictions={predictions} /></ToolGuard>} />
        </Routes>
        <PageTracker />
        <ImpersonationBar />
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
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;background:#0f172a;color:#f8fafc;font-family:Inter,system-ui,sans-serif;padding:2rem;text-align:center;">
        <div style="font-size:3rem;margin-bottom:1rem;">⚠️</div>
        <h1 style="font-size:1.5rem;margin:0 0 1rem;color:#f87171;">Connection Error</h1>
        <p style="color:#94a3b8;max-width:400px;margin:0 0 1.5rem;">${message}</p>
        <button onclick="location.reload()" style="padding:0.75rem 1.5rem;background:linear-gradient(135deg,#6366f1,#0ea5e9);color:white;border:none;border-radius:8px;cursor:pointer;font-size:1rem;">Retry</button>
      </div>
    `;
  }
};

const renderLoading = (statusMessage: string = 'Connecting to database...') => {
  const container = document.getElementById('root');
  if (container) {
    container.innerHTML = `
      <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;background:linear-gradient(135deg,#0f172a 0%,#1e293b 100%);color:#f8fafc;font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;padding:2rem;text-align:center;">
        <div style="position:relative;width:60px;height:60px;margin-bottom:2rem;">
          <div style="position:absolute;width:60px;height:60px;border:3px solid rgba(99,102,241,0.2);border-radius:50%;"></div>
          <div style="position:absolute;width:60px;height:60px;border:3px solid transparent;border-top-color:#6366f1;border-radius:50%;animation:spin 1s linear infinite;"></div>
        </div>
        <h1 style="font-size:1.5rem;font-weight:600;margin:0 0 0.75rem;background:linear-gradient(135deg,#6366f1,#0ea5e9);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;">Allworth Executive Reporting</h1>
        <p id="loading-status" style="color:#94a3b8;font-size:0.95rem;margin:0;">${statusMessage}</p>
      </div>
      <style>
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      </style>
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
    renderApp(demoMetrics, demoNetFlows, [], false, demoPredictions);
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
      renderApp(bundle.kpiMetrics, bundle.netFlows, bundle.detailedMetrics, false, bundle.predictions);
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
