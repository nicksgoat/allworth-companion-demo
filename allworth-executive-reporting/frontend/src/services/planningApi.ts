export type Household = { id: string; name: string; people: number; accounts: number; source: string };
export type Scenario = { id: string; household_id: string; name: string; overrides: unknown[]; is_recommended: boolean };
export type YearRow = {
  year: number; client_age: number; phase: string; inflows: string; outflows: string;
  taxes: string; investment_growth: string; withdrawals: string; savings: string;
  shortfall: string; net_worth: string;
};
export type Projection = {
  household_id: string; start_year: number; rows: YearRow[]; ending_net_worth: string;
  lifetime_taxes: string; first_shortfall_year: number | null; warnings: string[];
};
export type MonteCarloInputs = {
  ready: boolean; missing_required_inputs: string[]; warnings: string[];
  holdings_as_of: string | null;
  cma_version: string; cma_as_of: string; cma_source: string;
  portfolio_expected_return: number | null; portfolio_volatility: number | null;
  asset_classes: Array<{ name: string; weight: string; market_value: string; expected_return: string; std_dev: string }>;
  provenance: Record<string, string>;
};
export type MonteCarloResult = {
  probability_of_success: number; n_trials: number; seed: number;
  success_by_age: Record<string, number>;
  ending_value_percentiles: Record<string, string>;
  net_worth_bands: Array<{ year: number; p5: string; p25: string; p50: string; p75: string; p95: string }>;
  first_failure_year_histogram: Record<string, number>;
  input_snapshot: MonteCarloInputs;
};
export type Job = { id: string; status: 'queued' | 'running' | 'succeeded' | 'failed'; progress: number; result?: MonteCarloResult; error?: string };
export type StressResult = { kind: string; projection: Projection; delta_ending_net_worth: string };
export type SolveResult = { lever: string; value: string; target: string; iterations: number; achieved: boolean };
export type CompareScenario = {
  scenario_id: string; name: string; ending_net_worth: string; lifetime_taxes: string;
  first_shortfall_year: number | null; series: Array<{ year: number; net_worth: string }>;
};
export type LifecyclePlan = {
  inputs: Record<string, unknown>;
  economic_balance_sheet: { financial_wealth: number; human_capital: number; liabilities: number; economic_net_worth: number };
  bequest: { amount: number; type: string; is_optimal: boolean };
  human_capital_path: Array<{ year: number; age: number; gross_income: number; dc_savings: number; present_value_income: number }>;
  consumption_path: Array<{ year: number; age: number; nondiscretionary: number; discretionary: number; annuity_floor: number; total_consumption: number }>;
  glide_path: Array<{ year: number; age: number; unconstrained_equity: number; constrained_equity: number; domestic_stock: number; global_stock: number; bonds_cash: number }>;
  survival_curve: Array<{ year: number; age: number; survival_probability: number }>;
  warnings: string[];
};
export type VaultFile = {
  id: string; name: string; mime: string; size: number; folder: string;
  shared_with_client: boolean; uploaded_by: string; uploaded_at: string; sha256: string;
};
export type PortalRecord = {
  id: string; household_id: string; kind: string; payload: Record<string, unknown>;
  created_at: string; updated_at: string; created_by: string;
};
export type FeedEvent = PortalRecord & { household_name: string };
export type RothCandidate = {
  label: string; annual_conversion: string; window_years: number; total_converted: string;
  lifetime_taxes: string; lifetime_tax_delta: string; ending_net_worth: string;
  ending_net_worth_delta: string; ending_after_tax_wealth: string; ending_after_tax_delta: string;
  breakeven_year: number | null; first_shortfall_year: number | null;
};
export type RothAnalysis = {
  source_account_name: string | null; window_start_year: number; window_years: number;
  heir_tax_rate: string; baseline_lifetime_taxes: string; baseline_ending_net_worth: string;
  baseline_ending_after_tax_wealth: string; candidates: RothCandidate[];
  recommended: RothCandidate | null; warnings: string[];
};
export type SyncActualsResult = {
  household_id: string; applied: boolean; warnings: string[];
  diff: {
    matched: Array<{ name: string; kind: string; plan_value: string; actual_value: string; delta: string; delta_pct: string | null }>;
    added: Array<{ name: string; kind: string; actual_value: string }>;
    removed: Array<{ name: string; kind: string; plan_value: string }>;
    plan_total: string; actual_total: string; total_delta: string;
  };
  drift: { status: string; year?: number; projected_portfolio?: string; actual_portfolio?: string; ratio?: string; tolerance?: string; reason?: string };
  alert: Record<string, unknown> | null;
};
export type Publication = {
  publication_id: string; household_id: string; scenario_id: string; scenario_name: string;
  household_name: string; facts_version_id: string; status: string; published_at: string;
  published_by: string; input_hash: string; result_hash: string;
  summary: Record<string, unknown>; advisor_note: string | null;
  superseded_by: string | null; withdrawn_at: string | null;
};
export type CapitalMarketAssumptions = {
  version: string; as_of: string; source: string;
  expected_return_source: string; default_volatility_source: string;
  asset_classes: Record<string, { bucket: string; expected_return: string; std_dev: string; expected_return_source: string; volatility_source: string }>;
  correlations: Record<string, string>;
  aliases: Record<string, string>;
  warnings: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail;
    const message = typeof detail === 'string'
      ? detail
      : [detail?.message, detail?.hint].filter(Boolean).join(' ');
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

export const planningApi = {
  households: () => request<{ households: Household[] }>('/api/v1/households'),
  summary: (id: string) => request<Record<string, unknown>>(`/api/v1/households/${id}/summary`),
  facts: (id: string) => request<Record<string, unknown>>(`/api/v1/households/${id}/facts`),
  patchFacts: (id: string, ops: unknown[]) => request<Record<string, unknown>>(`/api/v1/households/${id}/facts`, {
    method: 'PATCH', body: JSON.stringify({ ops }),
  }),
  commitFacts: (id: string) => request<{ facts_version_id: string; committed_at: string }>(`/api/v1/households/${id}/facts/commit`, {
    method: 'POST',
  }),
  scenarios: (id: string) => request<{ scenarios: Scenario[] }>(`/api/v1/households/${id}/scenarios`),
  project: (id: string) => request<Projection>(`/api/v1/scenarios/${id}/project`, { method: 'POST' }),
  overrides: (id: string, overrides: unknown[]) => request<Scenario>(`/api/v1/scenarios/${id}/overrides`, {
    method: 'PATCH', body: JSON.stringify({ overrides }),
  }),
  create: (facts: unknown) => request<{ household_id: string; scenario_ids: string[] }>('/api/v1/households', {
    method: 'POST', body: JSON.stringify(facts),
  }),
  importWarehouse: (sourceId: string) => request<{ household_id: string; scenario_ids: string[] }>(`/api/v1/warehouse/households/${encodeURIComponent(sourceId)}/import`, { method: 'POST' }),
  deleteHousehold: (id: string, reason: string) => request<{ job_id: string; status: string }>(`/api/v1/households/${id}/delete`, {
    method: 'POST', body: JSON.stringify({ confirmation: 'DELETE', reason }),
  }),
  contract: () => request<Record<string, unknown>>('/api/v1/warehouse/contract'),
  estate: (id: string) => request<Record<string, unknown>>(`/api/v1/scenarios/${id}/estate-flow`, { method: 'POST' }),
  goals: (id: string) => request<{ goals: Array<Record<string, string>> }>(`/api/v1/scenarios/${id}/goals`),
  reportDefinitions: () => request<{ definitions: Array<{ id: number; name: string }> }>('/api/v1/report-definitions'),
  monteCarloInputs: (id: string) => request<MonteCarloInputs>(`/api/v1/scenarios/${id}/monte-carlo/inputs`),
  runMonteCarlo: (id: string, trials = 1000, seed = 42) => request<{ job_id: string }>(`/api/v1/scenarios/${id}/monte-carlo`, {
    method: 'POST', body: JSON.stringify({ trials, seed, refresh_synapse_inputs: true }),
  }),
  job: (id: string) => request<Job>(`/api/v1/jobs/${id}`),
  stress: (id: string, kind: 'crash' | 'low_return' | 'inflation' | 'longevity') =>
    request<StressResult>(`/api/v1/scenarios/${id}/stress/${kind}`, { method: 'POST' }),
  solve: (id: string, target: string) => request<SolveResult>(`/api/v1/scenarios/${id}/solve`, {
    method: 'POST', body: JSON.stringify({ lever: 'monthly_savings', target }),
  }),
  compare: (householdId: string, scenarioIds: string[]) =>
    request<{ household_id: string; scenarios: CompareScenario[] }>(`/api/v1/households/${householdId}/compare`, {
      method: 'POST', body: JSON.stringify({ scenario_ids: scenarioIds }),
    }),
  rothConversion: (id: string, windowYears?: number) =>
    request<RothAnalysis>(`/api/v1/scenarios/${id}/roth-conversion`, {
      method: 'POST', body: JSON.stringify(windowYears ? { window_years: windowYears } : {}),
    }),
  syncActuals: (householdId: string, apply: boolean) =>
    request<SyncActualsResult>(`/api/v1/households/${householdId}/sync-actuals`, {
      method: 'POST', body: JSON.stringify({ apply }),
    }),
  publish: (scenarioId: string, advisorNote?: string) =>
    request<Publication>(`/api/v1/scenarios/${scenarioId}/publish`, {
      method: 'POST', body: JSON.stringify(advisorNote ? { advisor_note: advisorNote } : {}),
    }),
  publications: (householdId: string) =>
    request<{ publications: Publication[] }>(`/api/v1/households/${householdId}/publications`),
  withdrawPublication: (publicationId: string, reason?: string) =>
    request<Publication>(`/api/v1/publications/${publicationId}/withdraw`, {
      method: 'POST', body: JSON.stringify(reason ? { reason } : {}),
    }),
  estateTaxProjection: (id: string) =>
    request<{ years: Array<{ year: number; gross_estate: string; federal_estate_tax: string }> }>(`/api/v1/scenarios/${id}/estate-tax-projection`),
  lifecyclePlan: (id: string) => request<LifecyclePlan>(`/api/v1/scenarios/${id}/lifecycle-plan`, { method: 'POST' }),
  lifecycleSensitivity: (id: string, param: string, values: Array<number | string>) =>
    request<{ base: Record<string, unknown>; results: Array<{ param: string; value: number | string; result: LifecyclePlan }> }>(
      `/api/v1/scenarios/${id}/lifecycle-plan/sensitivity`,
      { method: 'POST', body: JSON.stringify({ param, values }) },
    ),
  socialSecurityOptimizer: (clientPia: string, spousePia: string) =>
    request<{ client_claim_age: number; spouse_claim_age: number; expected_lifetime_benefit: string }>('/api/v1/tools/social-security-optimizer', {
      method: 'POST', body: JSON.stringify({ client_pia: clientPia, spouse_pia: spousePia }),
    }),
  inheritedIra: (balance: string) => request<Record<string, string[]>>('/api/v1/tools/inherited-ira', {
    method: 'POST', body: JSON.stringify({ balance }),
  }),
  nua: (costBasis: string, marketValue: string, ordinaryRate: string, ltcgRate: string) =>
    request<Record<string, string>>('/api/v1/tools/nua', {
      method: 'POST', body: JSON.stringify({ cost_basis: costBasis, market_value: marketValue, ordinary_rate: ordinaryRate, ltcg_rate: ltcgRate }),
    }),
  vaultFiles: (householdId: string) => request<{ files: VaultFile[] }>(`/api/v1/households/${householdId}/vault/files`),
  vaultUpload: async (householdId: string, file: File, folder: string, sharedWithClient: boolean): Promise<VaultFile> => {
    const form = new FormData();
    form.append('file', file);
    form.append('folder', folder);
    form.append('shared_with_client', sharedWithClient ? 'true' : 'false');
    const response = await fetch(`/api/v1/households/${householdId}/vault/files`, { method: 'POST', body: form });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : `${response.status} ${response.statusText}`);
    }
    return response.json() as Promise<VaultFile>;
  },
  vaultShare: (householdId: string, fileId: string, shared: boolean) =>
    request<VaultFile>(`/api/v1/households/${householdId}/vault/files/${fileId}`, {
      method: 'PATCH', body: JSON.stringify({ shared_with_client: shared }),
    }),
  vaultDelete: async (householdId: string, fileId: string): Promise<void> => {
    const response = await fetch(`/api/v1/households/${householdId}/vault/files/${fileId}`, { method: 'DELETE' });
    if (!response.ok && response.status !== 204) throw new Error(`${response.status} ${response.statusText}`);
  },
  vaultDownloadUrl: (householdId: string, fileId: string) => `/api/v1/households/${householdId}/vault/files/${fileId}`,
  advisorFeed: () => request<{ events: FeedEvent[] }>('/api/v1/advisor/feed'),
  portalRecords: (householdId: string, kind: 'tasks' | 'alerts' | 'budgets') =>
    request<Record<string, PortalRecord[]>>(`/api/v1/households/${householdId}/${kind}`),
  createPortalRecord: (householdId: string, kind: 'tasks' | 'alerts', payload: Record<string, unknown>) =>
    request<PortalRecord>(`/api/v1/households/${householdId}/${kind}`, {
      method: 'POST', body: JSON.stringify({ payload }),
    }),
  updatePortalRecord: (householdId: string, kind: 'tasks' | 'alerts', recordId: string, payload: Record<string, unknown>) =>
    request<PortalRecord>(`/api/v1/households/${householdId}/${kind}/${recordId}`, {
      method: 'PATCH', body: JSON.stringify({ payload }),
    }),
  capitalMarketAssumptions: () =>
    request<CapitalMarketAssumptions>('/api/v1/capital-market-assumptions?refresh_synapse=0'),
  reportHistory: (householdId: string) =>
    request<{ runs: PortalRecord[] }>(`/api/v1/households/${householdId}/report-history`),
};
