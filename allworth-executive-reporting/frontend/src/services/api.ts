// src/services/api.ts
// NOTE: same-origin requests to /api/ are automatically decorated with a
// Bearer token by the global fetch() wrapper installed in main.tsx via
// installAuthFetch().  Do not duplicate that header here.
import type { KpiDataset, KpiEntry, PredictionsPayload } from '../types/kpi';

export interface KpiMetricRaw {
  metric_name: string;
  channel?: string;
  channel_middle?: string;
  period?: string;
  actual_value: number;
  goal_value?: number;
  py_actual_value?: number;
  py_prorated?: number;
  goal_prorated?: number;
  target_value?: number;
  budget_value?: number;
  currency?: string;
  unit?: string;
}

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

/** Combined response from /api/all-metrics */
interface AllMetricsResponse {
  success: boolean;
  kpiMetrics: ApiResponse<KpiMetricRaw[]>;
  netFlows: ApiResponse<KpiMetricRaw[]>;
  detailedMetrics: ApiResponse<KpiMetricRaw[]>;
  predictions?: PredictionsPayload;
}

/** Pre-transformed bundle returned by fetchAllMetrics */
export interface AllMetricsBundle {
  kpiMetrics: KpiDataset;
  netFlows: KpiDataset;
  detailedMetrics: KpiDataset;
  predictions?: PredictionsPayload;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

/**
 * Transforms raw API metrics into the KpiDataset format used by the app
 */
const transformApiMetrics = (rawMetrics: KpiMetricRaw[]): KpiDataset => {
  return rawMetrics.map((raw, index) => {
    const metric = raw.metric_name;
    const channel = raw.channel || 'Default Channel';
    const period = raw.period || new Date().toISOString().slice(0, 7); // YYYY-MM format
    
    const slugify = (value: string) => 
      value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    
    const id = `${slugify(metric)}-${slugify(channel)}-${slugify(period)}-${index}`;
    
    const entry: KpiEntry = {
      id,
      metric,
      channel,
      period,
      actual: raw.actual_value,
      goal: raw.goal_value ?? raw.target_value ?? raw.budget_value ?? 0,
    };
    
    // Add channel_middle if present
    if (raw.channel_middle) entry.channelMiddle = raw.channel_middle;
    
    // Add PY and prorated values
    if (raw.py_actual_value !== undefined) entry.pyActual = raw.py_actual_value;
    if (raw.py_prorated !== undefined) entry.pyProrated = raw.py_prorated;
    if (raw.goal_prorated !== undefined) entry.goalProrated = raw.goal_prorated;
    if (raw.target_value !== undefined) entry.target = raw.target_value;
    if (raw.budget_value !== undefined) entry.budget = raw.budget_value;
    if (raw.currency) entry.currency = raw.currency;
    if (raw.unit) entry.unit = raw.unit;
    
    return entry;
  });
};

/**
 * Fetches KPI metrics from the backend API and transforms them
 */
export const fetchKpiMetrics = async (): Promise<KpiDataset> => {
  try {
    console.log('   Fetching from:', `${API_BASE_URL}/kpi-metrics`);
    
    // Set a 30-second timeout for the request (Azure AD auth can take time)
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    
    const response = await fetch(`${API_BASE_URL}/kpi-metrics`, {
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    console.log('   Response status:', response.status, response.statusText);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('   Response error:', errorText.substring(0, 500));
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const result: ApiResponse<KpiMetricRaw[]> = await response.json();
    console.log('   Parsed result:', result.success ? 'success' : 'failed', 'data count:', result.data?.length);
    
    if (!result.success || !result.data) {
      throw new Error(result.error || 'Failed to fetch metrics');
    }
    
    return transformApiMetrics(result.data);
  } catch (error) {
    console.error('   ❌ Error fetching KPI metrics:', error);
    throw error;
  }
};

/**
 * Checks if the API backend is healthy and available
 */
export const checkApiHealth = async (): Promise<boolean> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000); // 3 second timeout
    
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      return false;
    }
    
    const result = await response.json();
    return result.status === 'healthy';
  } catch (error) {
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        console.error('API health check timed out after 3 seconds');
      } else {
        console.error('API health check failed:', error.message);
      }
    }
    return false;
  }
};

/**
 * Fetches Net Flows metrics from the backend API
 */
export const fetchNetFlowsMetrics = async (): Promise<KpiDataset> => {
  try {
    console.log('   Fetching from:', `${API_BASE_URL}/net-flows`);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    
    const response = await fetch(`${API_BASE_URL}/net-flows`, {
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    console.log('   Net Flows response status:', response.status, response.statusText);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('   Net Flows response error:', errorText.substring(0, 500));
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const result: ApiResponse<KpiMetricRaw[]> = await response.json();
    console.log('   Net Flows parsed result:', result.success ? 'success' : 'failed', 'data count:', result.data?.length);
    
    if (!result.success || !result.data) {
      throw new Error(result.error || 'Failed to fetch net flows metrics');
    }
    
    return transformApiMetrics(result.data);
  } catch (error) {
    console.error('   ❌ Error fetching Net Flows metrics:', error);
    throw error;
  }
};

/**
 * Fetches detailed KPI metrics with channel_middle granularity
 */
export const fetchDetailedKpiMetrics = async (): Promise<KpiDataset> => {
  try {
    console.log('   Fetching from:', `${API_BASE_URL}/kpi-metrics-detailed`);
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    
    const response = await fetch(`${API_BASE_URL}/kpi-metrics-detailed`, {
      signal: controller.signal
    });
    
    clearTimeout(timeoutId);
    console.log('   Detailed metrics response status:', response.status, response.statusText);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error('   Detailed metrics response error:', errorText.substring(0, 500));
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const result: ApiResponse<KpiMetricRaw[]> = await response.json();
    console.log('   Detailed metrics parsed result:', result.success ? 'success' : 'failed', 'data count:', result.data?.length);
    
    if (!result.success || !result.data) {
      throw new Error(result.error || 'Failed to fetch detailed metrics');
    }
    
    return transformApiMetrics(result.data);
  } catch (error) {
    console.error('   ❌ Error fetching detailed KPI metrics:', error);
    throw error;
  }
};

/**
 * Fetches ALL metrics (kpi, net-flows, detailed) in a single HTTP request.
 * The backend runs the three Synapse queries concurrently, so total latency
 * ≈ slowest single query instead of sum-of-three.
 *
 * Falls back to individual sequential fetches if the combined endpoint is
 * unavailable (e.g. older backend version).
 */
export const fetchAllMetrics = async (): Promise<AllMetricsBundle> => {
  try {
    console.log('   Fetching from:', `${API_BASE_URL}/all-metrics`);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 45000);

    const response = await fetch(`${API_BASE_URL}/all-metrics`, {
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    console.log('   all-metrics response status:', response.status, response.statusText);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result: AllMetricsResponse = await response.json();

    return {
      kpiMetrics: result.kpiMetrics?.data ? transformApiMetrics(result.kpiMetrics.data) : [],
      netFlows: result.netFlows?.data ? transformApiMetrics(result.netFlows.data) : [],
      detailedMetrics: result.detailedMetrics?.data ? transformApiMetrics(result.detailedMetrics.data) : [],
      predictions: result.predictions,
    };
  } catch (error) {
    console.warn('   ⚠️ Combined endpoint failed, falling back to sequential fetches:', error);
    return fetchAllMetricsSequential();
  }
};

/**
 * Fallback: fetch the three datasets individually (sequential to avoid
 * connection-busy errors on Synapse).
 */
async function fetchAllMetricsSequential(): Promise<AllMetricsBundle> {
  const kpiMetrics = await fetchKpiMetrics();

  let netFlows: KpiDataset = [];
  try {
    netFlows = await fetchNetFlowsMetrics();
  } catch {
    console.warn('   ⚠️ Net Flows fetch failed');
  }

  let detailedMetrics: KpiDataset = [];
  try {
    detailedMetrics = await fetchDetailedKpiMetrics();
  } catch {
    console.warn('   ⚠️ Detailed metrics fetch failed');
  }

  return { kpiMetrics, netFlows, detailedMetrics };
}


// ---------------------------------------------------------------------------
// Page-view analytics – fire-and-forget tracker
// ---------------------------------------------------------------------------
export function trackPageView(opts: {
  isEmbedded: boolean;
  loadTimeMs?: number;
  userEmail?: string | null;
}): void {
  try {
    const payload = {
      page: window.location.pathname || '/',
      referrer: document.referrer || null,
      screenWidth: window.screen?.width,
      screenHeight: window.screen?.height,
      windowWidth: window.innerWidth,
      windowHeight: window.innerHeight,
      loadTimeMs: opts.loadTimeMs != null ? Math.round(opts.loadTimeMs) : null,
      isEmbedded: opts.isEmbedded,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      language: navigator.language,
      userEmail: opts.userEmail ?? null,
    };

    // Fire-and-forget – intentionally no await
    fetch(`${API_BASE_URL}/track`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).catch(() => {
      // Silently swallow – analytics should never break the app
    });
  } catch {
    // Safety net
  }
}
