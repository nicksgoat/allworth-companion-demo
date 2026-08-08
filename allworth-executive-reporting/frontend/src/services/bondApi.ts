/**
 * Bond Analyzer API Service
 * Communicates with the FastAPI backend for portfolio management and analytics
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';
const CLIENT_QUERY_CACHE_TTL_MS = 5 * 60 * 1000;

type QueryCacheEntry = {
  expiresAt: number;
  promise: Promise<unknown>;
};

const queryCache = new Map<string, QueryCacheEntry>();

function cachedRequest<T>(
  key: string,
  loader: () => Promise<T>,
  ttlMs = CLIENT_QUERY_CACHE_TTL_MS,
): Promise<T> {
  const cached = queryCache.get(key);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.promise as Promise<T>;
  }
  const promise = loader().catch(error => {
    queryCache.delete(key);
    throw error;
  });
  queryCache.set(key, { expiresAt: Date.now() + ttlMs, promise });
  return promise;
}

const accountCacheKey = (prefix: string, accountNumbers: string[]) =>
  `${prefix}:${[...new Set(accountNumbers.map(value => value.trim()).filter(Boolean))]
    .sort()
    .join(',')}`;

// ============================================================================
// Types
// ============================================================================

export interface Bond {
  symbol: string;
  cusip: string;
  description: string;
  account_number?: string;
  account_name?: string;
  coupon: number;
  price: number;
  quantity: number;
  market_value: number;
  weight?: number | null;
  annual_income?: number;
  yield_to_worst: number;
  effective_duration: number;
  ratings: CreditRating[];
  maturity_date: string;
  call_date?: string;
  callable: boolean;
  issuer: string;
  sector: string;
  state: string;
}

export interface CreditRating {
  agency: string;
  current: string;
  previous?: string;
  effective_date: string;
}

export interface KPIs {
  market_value: number;
  annual_income: number;
  avg_coupon: number;
  avg_yield: number;
  avg_duration: number;
  avg_rating: string;
  callable_pct: number;
  health_score: number;
}

export interface PortfolioSummary {
  id: string;
  name: string;
  source_filename: string;
  holdings: number;
  accounts: string[];
  created_at: string;
}

export interface UploadResponse {
  portfolio: PortfolioSummary;
  message: string;
}

export interface Dashboard {
  portfolio_id: string;
  bonds: Bond[];
  kpis: KPIs;
  maturity_ladder: Record<string, number>;
  call_ladder: Record<string, number>;
  credit_distribution: Record<string, number>;
  sector_allocation: Record<string, number>;
  state_allocation: Record<string, number>;
  issuer_concentration: Record<string, number>;
  cash_flow_projection: Array<{ month: string; principal: number; income: number }>;
  monthly_income: Record<string, number>;
  coupon_distribution: Record<string, number>;
  yield_distribution: Record<string, number>;
  upcoming_calls: Bond[];
  upcoming_maturities: Bond[];
  rating_changes: Array<{ bond: string; from: string; to: string; date: string }>;
  ladder_quality_score: number;
  portfolio_health_score: number;
}

export interface AISummary {
  strengths: string[];
  risks: string[];
  concentration_warnings: string[];
  reinvestment_needs: string[];
  recommendations: string[];
}

// ============================================================================
// Health Check
// ============================================================================

export const checkApiHealth = async (): Promise<boolean> => {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    const response = await fetch(`${API_BASE_URL}/health`, {
      signal: controller.signal,
    });

    clearTimeout(timeoutId);
    return response.ok;
  } catch {
    return false;
  }
};

// ============================================================================
// Portfolio Management
// ============================================================================

export const fetchPortfolios = async (): Promise<PortfolioSummary[]> => {
  const response = await fetch(`${API_BASE_URL}/portfolios`);
  if (!response.ok) throw new Error(`Failed to fetch portfolios: ${response.status}`);
  return response.json();
};

export const getPortfolio = async (portfolioId: string): Promise<PortfolioSummary> => {
  const response = await fetch(`${API_BASE_URL}/portfolios/${portfolioId}`);
  if (!response.ok) throw new Error(`Failed to fetch portfolio: ${response.status}`);
  return response.json();
};

export const uploadPortfolio = async (file: File): Promise<UploadResponse> => {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${API_BASE_URL}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(error || `Upload failed: ${response.status}`);
  }

  return response.json();
};

// ============================================================================
// Dashboard & Analytics
// ============================================================================

export const getDashboard = async (portfolioId: string, accounts?: string[]): Promise<Dashboard> => {
  let url = `${API_BASE_URL}/dashboard/${portfolioId}`;
  if (accounts?.length) {
    url += `?accounts=${accounts.join(',')}`;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch dashboard: ${response.status}`);
  return response.json();
};

export const getAISummary = async (portfolioId: string, accounts?: string[]): Promise<AISummary> => {
  let url = `${API_BASE_URL}/summary/${portfolioId}`;
  if (accounts?.length) {
    url += `?accounts=${accounts.join(',')}`;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch AI summary: ${response.status}`);
  return response.json();
};

export const getMaturityLadder = async (portfolioId: string, accounts?: string[]) => {
  let url = `${API_BASE_URL}/maturity/${portfolioId}`;
  if (accounts?.length) {
    url += `?accounts=${accounts.join(',')}`;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch maturity ladder: ${response.status}`);
  return response.json();
};

export const getCallLadder = async (portfolioId: string, accounts?: string[]) => {
  let url = `${API_BASE_URL}/calls/${portfolioId}`;
  if (accounts?.length) {
    url += `?accounts=${accounts.join(',')}`;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch call ladder: ${response.status}`);
  return response.json();
};

export const getCashFlowProjection = async (portfolioId: string, accounts?: string[]) => {
  let url = `${API_BASE_URL}/cashflow/${portfolioId}`;
  if (accounts?.length) {
    url += `?accounts=${accounts.join(',')}`;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch cash flow: ${response.status}`);
  return response.json();
};

export const getIncomeProjection = async (portfolioId: string, accounts?: string[]) => {
  let url = `${API_BASE_URL}/income/${portfolioId}`;
  if (accounts?.length) {
    url += `?accounts=${accounts.join(',')}`;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch income: ${response.status}`);
  return response.json();
};

export const getCreditDistribution = async (portfolioId: string, accounts?: string[]) => {
  let url = `${API_BASE_URL}/credit/${portfolioId}`;
  if (accounts?.length) {
    url += `?accounts=${accounts.join(',')}`;
  }

  const response = await fetch(url);
  if (!response.ok) throw new Error(`Failed to fetch credit distribution: ${response.status}`);
  return response.json();
};

// ============================================================================
// Account Analyzer (DataWarehouse)
// ============================================================================

export interface AccountAnalysisResult {
  account_number: string;
  account_name: string | null;
  account_numbers: string[];
  account_names: string[];
  holdings_count: number;
  enriched_count: number;
  dashboard: Dashboard;
  summary: AISummary;
  field_requirements: Record<string, { required: string[]; recommended: string[] }>;
}

export const analyzeAccount = async (accountNumber: string): Promise<AccountAnalysisResult> => {
  const normalized = accountNumber.trim();
  return cachedRequest(accountCacheKey('analysis', [normalized]), async () => {
    const response = await fetch(`${API_BASE_URL}/analyze/account/${encodeURIComponent(normalized)}`);
    if (response.status === 404) throw new Error(`Account "${normalized}" not found.`);
    if (response.status === 503) throw new Error('Database connection is not configured on the server.');
    if (response.status === 502) throw new Error('Database query failed. Check server logs.');
    if (!response.ok) throw new Error(`Account analysis failed: ${response.status}`);
    return response.json();
  });
};

export const analyzeAccounts = async (accountNumbers: string[]): Promise<AccountAnalysisResult> => {
  const normalized = [...new Set(accountNumbers.map(value => value.trim()).filter(Boolean))].sort();
  return cachedRequest(accountCacheKey('analysis', normalized), async () => {
    const params = new URLSearchParams();
    normalized.forEach(accountNumber => params.append('account_numbers', accountNumber));
    const response = await fetch(`${API_BASE_URL}/analyze/accounts?${params}`);
    if (response.status === 404) throw new Error(`No holdings found for ${normalized.join(', ')}.`);
    if (response.status === 503) throw new Error('Database connection is not configured on the server.');
    if (response.status === 502) throw new Error('Database query failed. Check server logs.');
    if (!response.ok) throw new Error(`Account analysis failed: ${response.status}`);
    return response.json();
  });
};

// ============================================================================
// Bond Ladder (DataWarehouse)
// ============================================================================

export interface BondLadderHolding {
  account_number: string;
  account_name: string;
  strategy: string;
  symbol: string;
  cusip: string;
  description: string;
  issuer: string;
  sector: string;
  state: string;
  quantity: number;
  price: number;
  market_value: number;
  coupon: number;
  yield_to_worst: number;
  effective_duration: number;
  maturity_date: string | null;
  call_date: string | null;
  callable: boolean;
  fitch_rating: string | null;
  fitch_rating_previous: string | null;
  fitch_rating_effective_date: string | null;
  fitch_rating_previous_effective_date: string | null;
  is_downgraded: boolean;
  annual_income: number;
}

export interface BondLadderAccountSummary {
  account_number: string;
  account_name: string;
  strategy: string;
  bond_count: number;
  total_market_value: number;
}

export interface BondLadderResult {
  total_accounts: number;
  total_bonds: number;
  total_market_value: number;
  strategies: string[];
  accounts: BondLadderAccountSummary[];
  bonds: BondLadderHolding[];
  cache_age_seconds: number | null;
  fetched_at: string | null;  // ISO-8601 UTC
}

// ── Module-level client cache ─────────────────────────────────────────────────
// Avoids a full DB round-trip every time the user switches back to the
// Bond Ladder tab.  Expires after 5 minutes; the server has its own 30-min TTL.
const CLIENT_CACHE_TTL_MS = 5 * 60 * 1000;
let _bondLadderCache: { data: BondLadderResult; fetchedAt: number } | null = null;

export const invalidateBondLadderCache = () => { _bondLadderCache = null; };

export const fetchBondLadder = async (
  strategy?: string,
  sortBy: 'maturity' | 'call_date' = 'maturity',
  forceRefresh = false,
): Promise<BondLadderResult> => {
  // Serve from client cache if still fresh and no filter is active
  if (
    !forceRefresh &&
    !strategy &&
    sortBy === 'maturity' &&
    _bondLadderCache &&
    Date.now() - _bondLadderCache.fetchedAt < CLIENT_CACHE_TTL_MS
  ) {
    return _bondLadderCache.data;
  }

  const params = new URLSearchParams({ sort_by: sortBy });
  if (strategy) params.set('strategy', strategy);
  const response = await fetch(`${API_BASE_URL}/bond-ladder?${params}`);
  if (response.status === 503) throw new Error('Database connection is not configured on the server.');
  if (response.status === 502) throw new Error('Database query failed. Check server logs.');
  if (!response.ok) throw new Error(`Bond Ladder fetch failed: ${response.status}`);
  const data: BondLadderResult = await response.json();

  // Only cache the unfiltered baseline
  if (!strategy && sortBy === 'maturity') {
    _bondLadderCache = { data, fetchedAt: Date.now() };
  }
  return data;
};

export const refreshBondLadder = async (): Promise<{ total_accounts: number; total_bonds: number; fetched_at: string | null }> => {
  invalidateBondLadderCache();
  const response = await fetch(`${API_BASE_URL}/bond-ladder/refresh`, { method: 'POST' });
  if (!response.ok) throw new Error(`Refresh failed: ${response.status}`);
  return response.json();
};

// ── Called (redeemed) bonds report ────────────────────────────────────────────

export interface TransactionRow {
  transaction_id: string | null;
  account_number: string;
  account_name: string;
  trade_date: string | null;
  transaction_type: string | null;
  symbol: string | null;
  cusip: string | null;
  description: string | null;
  quantity: number | null;
  price: number | null;
  amount: number | null;
  notes: string | null;
  source: string;
}

export interface CalledReport {
  days: number;
  start_date: string;
  end_date: string;
  as_of_date: string;
  count: number;
  cash_flagged_count: number;
  reinvested_count: number;
  unresolved_count: number;
  cache_ttl_seconds: number;
  rows: CalledBondRow[];
}

export interface CalledBondRow extends TransactionRow {
  account_value: number;
  cash_value: number;
  cash_percent: number;
  cash_flagged: boolean;
  matching_buy: TransactionRow | null;
  match_basis: 'quantity' | 'amount' | null;
  highlight: 'cash' | 'yellow' | null;
}

export interface CalledReportQuery {
  startDate?: string;
  endDate?: string;
  days?: number;
  forceRefresh?: boolean;
}

export const fetchBondLadderCalled = async ({
  startDate,
  endDate,
  days = 30,
  forceRefresh = false,
}: CalledReportQuery = {}): Promise<CalledReport> => {
  const params = new URLSearchParams({ days: String(days) });
  if (startDate) params.set('start_date', startDate);
  if (endDate) params.set('end_date', endDate);
  if (forceRefresh) params.set('force_refresh', 'true');
  const response = await fetch(`${API_BASE_URL}/bond-ladder/called?${params}`);
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json() as { detail?: string };
      detail = body.detail ?? '';
    } catch {
      // Use the status fallback below when the response is not JSON.
    }
    if (response.status === 503) {
      throw new Error(detail || 'The called-bond warehouse source is unavailable.');
    }
    if (response.status === 502) {
      throw new Error(detail || 'The called-bond warehouse query failed.');
    }
    if (response.status === 400) {
      throw new Error(detail || 'The selected date range is invalid.');
    }
  }
  if (!response.ok) throw new Error(`Called report fetch failed: ${response.status}`);
  return response.json();
};

// ── Transactions (Tamarac-style activity) ─────────────────────────────────────

export interface TransactionsResult {
  account_numbers: string[];
  count: number;
  rows: TransactionRow[];
}

export const fetchTransactions = async (accountNumbers: string[]): Promise<TransactionsResult> => {
  const normalized = [...new Set(accountNumbers.map(value => value.trim()).filter(Boolean))].sort();
  return cachedRequest(accountCacheKey('transactions', normalized), async () => {
    const [first, ...rest] = normalized;
    if (rest.length === 0) {
      const response = await fetch(`${API_BASE_URL}/transactions/account/${encodeURIComponent(first)}`);
      if (response.status === 502) throw new Error('Database query failed. Check server logs.');
      if (!response.ok) throw new Error(`Transactions fetch failed: ${response.status}`);
      return response.json();
    }
    const params = new URLSearchParams();
    normalized.forEach(n => params.append('account_numbers', n));
    const response = await fetch(`${API_BASE_URL}/transactions/accounts?${params}`);
    if (response.status === 502) throw new Error('Database query failed. Check server logs.');
    if (!response.ok) throw new Error(`Transactions fetch failed: ${response.status}`);
    return response.json();
  });
};

// ============================================================================
// Appraisal / Holdings (DataWarehouse)
// ============================================================================

export interface AppraisalHolding {
  account_number: string;
  account_name: string;
  asset_class: string;
  subsector: string;
  security_type: string;
  cusip: string;
  symbol: string;
  description: string;
  redemption_date: string | null;
  quantity: number | null;
  price: number | null;
  market_value: number | null;
  weight: number | null;
  call_date: string | null;
  unrealized_gain_loss: number | null;
  percent_gain_loss: number | null;
  annual_income: number | null;
  annual_income_rate: number | null;
  accrued_income: number | null;
  open_date: string | null;
}

export interface AppraisalResult {
  account_number: string;
  account_name: string | null;
  account_numbers: string[];
  account_names: string[];
  as_of_date: string | null;
  holdings_count: number;
  rows: AppraisalHolding[];
}

export const fetchAppraisalHoldings = async (accountNumbers: string[]): Promise<AppraisalResult> => {
  const normalized = [...new Set(accountNumbers.map(value => value.trim()).filter(Boolean))].sort();
  return cachedRequest(accountCacheKey('appraisal', normalized), async () => {
    const [first, ...rest] = normalized;
    if (rest.length === 0) {
      const response = await fetch(`${API_BASE_URL}/appraisal/account/${encodeURIComponent(first)}`);
      if (response.status === 404) throw new Error(`Account "${first}" not found.`);
      if (response.status === 503) throw new Error('Database connection is not configured on the server.');
      if (response.status === 502) throw new Error('Database query failed. Check server logs.');
      if (!response.ok) throw new Error(`Appraisal fetch failed: ${response.status}`);
      return response.json();
    }
    const params = new URLSearchParams();
    normalized.forEach(n => params.append('account_numbers', n));
    const response = await fetch(`${API_BASE_URL}/appraisal/accounts?${params}`);
    if (response.status === 404) throw new Error('No holdings found for the given accounts.');
    if (response.status === 503) throw new Error('Database connection is not configured on the server.');
    if (response.status === 502) throw new Error('Database query failed. Check server logs.');
    if (!response.ok) throw new Error(`Appraisal fetch failed: ${response.status}`);
    return response.json();
  });
};

// ============================================================================
// Sample Portfolio Generator
// ============================================================================

export interface SampleStrategy {
  key: string;
  label: string;
  asset: string;
  tax_exempt: boolean;
  min_year: number;
  max_year: number;
  target_count: number;
}

export interface CreditGrade {
  grade: string;
  pct: number;
}

export interface IncomeScheduleRow {
  year: number;
  annual: number;
  cumulative: number;
}

export interface SamplePortfolioMetrics {
  portfolio_value: number;
  cash_invested: number;
  total_face_value: number;
  number_of_securities: number;
  annual_taxable_income: number;
  annual_tax_exempt_income: number;
  yield_to_worst: number | null;
  yield_to_maturity: number | null;
  tax_equivalent_ytw: number | null;
  tax_equivalent_ytm: number | null;
  average_credit_quality: string | null;
  investor_federal_tax_rate: number;
  credit_quality_distribution: CreditGrade[];
  income_schedule: IncomeScheduleRow[];
}

export interface SamplePortfolioBond {
  symbol: string | null;
  cusip: string | null;
  description: string;
  coupon: number | null;
  price: number | null;
  quantity: number | null;
  market_value: number | null;
  annual_income: number | null;
  yield_to_worst: number | null;
  maturity_date: string | null;
  rating: string | null;
  rating_agency: string | null;
  previous_rating: string | null;
  rating_effective_date: string | null;
  corporate_quality_score: number | null;
  corporate_quality_components: Record<string, number> | null;
  sector: string | null;
  broad_sector: string | null;
  segment: string | null;
  state: string | null;
  callable: boolean;
}

export interface SamplePortfolioResult {
  strategy: { key: string; label: string; asset: string; description: string };
  target_value: number;
  as_of: string;
  metrics: SamplePortfolioMetrics;
  warnings: string[];
  bonds: SamplePortfolioBond[];
}

export interface GenerateSampleRequest {
  strategy: string;
  target_value?: number;
  tax_rate?: number;
  exclude_unrated?: boolean;
  lot_size?: number;
  state?: string;
}

export interface ProposalSampleRequest extends GenerateSampleRequest {
  client_name?: string;
  prepared_by?: string;
  proposal_title?: string;
  proposal_id?: string;
}

export const fetchSampleStrategies = async (): Promise<SampleStrategy[]> => {
  const response = await fetch(`${API_BASE_URL}/sample-portfolio/strategies`);
  if (!response.ok) throw new Error(`Failed to load strategies: ${response.status}`);
  const data = await response.json();
  return data.strategies;
};

/** Extract the most useful error message from a failed sample-portfolio response. */
const _sampleError = async (response: Response): Promise<string> => {
  // FastAPI error bodies: { "detail": "..." }
  try {
    const body = await response.json();
    if (body?.detail && typeof body.detail === 'string') return body.detail;
  } catch { /* not JSON */ }
  // Fallback hints by status code.
  if (response.status === 422) return 'No eligible bonds were found for this strategy in the warehouse.';
  if (response.status === 503) return 'Service unavailable — check that the database connection and PDF engine are configured.';
  if (response.status === 502) return 'Database query failed. Check server logs.';
  return `Request failed: ${response.status}`;
};

export const generateSamplePortfolio = async (
  req: GenerateSampleRequest,
): Promise<SamplePortfolioResult> => {
  const response = await fetch(`${API_BASE_URL}/sample-portfolio/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!response.ok) throw new Error(await _sampleError(response));
  return response.json();
};

export const downloadSamplePortfolioPdf = async (req: GenerateSampleRequest): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/sample-portfolio/pdf`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!response.ok) throw new Error(await _sampleError(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${req.strategy}-sample-portfolio.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

export const downloadSamplePortfolioProposal = async (req: ProposalSampleRequest): Promise<void> => {
  const response = await fetch(`${API_BASE_URL}/sample-portfolio/proposal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!response.ok) throw new Error(await _sampleError(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  const slug = (req.proposal_title || req.client_name || req.strategy)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '') || req.strategy;
  link.download = `${slug}-proposal.pdf`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};
