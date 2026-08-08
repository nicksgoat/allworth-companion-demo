// src/services/crm.ts
// Typed fetch helpers for the CRM tool (Client 360 + Advisor book views).
// Backed by the read-only /api/crm blueprint. In local-preview DEMO_MODE
// (npm run dev:demo) there is no backend, so a bundled synthetic dataset is
// served so the whole tool can be explored offline.

// Same-origin default: Vite dev proxies /api → :5000, nginx does so in prod.
// An absolute localhost:5000 URL would be cross-origin from the dev server and
// fail CORS with credentials: 'include'.
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

// ── types ─────────────────────────────────────────────────────────────────

export interface CrmClient {
  lead_id: string;
  name: string;
  state: string;
  hh_status: string;
  segment: string;
  channel: string;
  stage: string;
  job_title: string;
  aum: number;
  paum: number;
  advisor_id: string;
  advisor_name: string;
  avhhid: string;
  sf_url: string;
}

export interface CrmClientDetail extends CrmClient {
  email: string;
  phone: string;
  address: string;
  zip: string;
  aum_billed: number;
  hhid: string;
  secondary_advisor_id: string;
}

export interface CrmActivity {
  id: string;
  activity_type: string;
  subject: string;
  status: string;
  call_disposition: string;
  completed_by: string;
  created: string;
  owner_name: string;
}

export interface CrmOpportunity {
  lead_id: string;
  name: string;
  paum: number;
  stage: string;
  days_in_stage: number;
  score: number;
  channel: string;
  advisor_name: string;
  region: string;
  expected_close_date: string;
  last_activity_date: string;
  next_activity_date: string;
  sf_url: string;
}

export interface CrmTask {
  id: string;
  subject: string;
  status: string;
  activity_type: string;
  lead_id: string;
  created: string;
  owner_name: string;
  client_name: string;
  sf_url: string;
}

export interface CrmAdvisor {
  advisor_id: string;
  name: string;
  region: string;
  title: string;
  email: string;
  client_count: number;
  total_aum: number;
}

export interface CrmSummary {
  total_clients: number;
  total_advisors: number;
  open_opportunities: number;
  open_pipeline_paum: number;
}

export interface CrmFilters {
  segments: string[];
  channels: string[];
  statuses: string[];
}

export interface CrmAdvisorDetail {
  advisor: CrmAdvisor;
  clients: CrmClient[];
}

export interface CrmAccount {
  account_id: string;
  account_name: string;
  account_type: string;
  master_category: string;
  custodian: string;
  taxable: string;
  total_value: number;
  current_cash: number;
  rmd_total: number;
  rmd_satisfied: string;
}

export interface CrmFlowPoint {
  period: string; // YYYY-MM-DD month end
  total_value: number;
  ncnm: number;
  acquisition: number;
  attrition: number;
  distribution: number;
  income: number;
  mgmt_fee: number;
}

export interface CrmSegmentSlice {
  segment: string;
  clients: number;
  aum: number;
}

export interface CrmAttentionItem {
  lead_id: string;
  name: string;
  aum: number;
  last_activity: string | null;
  sf_url: string;
}

export interface CrmRmdItem {
  lead_id: string;
  client_name: string;
  account_name: string;
  amount: number;
}

export interface CrmAllocationSlice {
  label: string;
  value: number;
  pct: number;
}

export interface CrmPerformancePoint {
  period: string;
  mtd_pct: number;
}

export interface CrmHolding {
  symbol: string;
  custodian: string;
  market_value: number;
  cost_basis: number;
  unrealized: number;
}

export interface CrmPortfolio {
  as_of: string | null;
  allocation: CrmAllocationSlice[];
  beta: number;
  duration: number;
  yield_pct: number;
  performance: CrmPerformancePoint[];
  ytd_pct: number | null;
  holdings: CrmHolding[];
}

export interface CrmBook {
  flows: CrmFlowPoint[];
  allocation: CrmAllocationSlice[];
  segments: CrmSegmentSlice[];
  needs_attention: CrmAttentionItem[];
  pipeline: CrmOpportunity[];
  rmds: { count: number; total: number; items: CrmRmdItem[] };
  open_tasks: number;
}

export interface CrmPlanLink {
  household_id: string;
  name: string;
  source: string;
}

export interface ClientQuery {
  q?: string;
  advisor?: string;
  segment?: string;
  status?: string;
  limit?: number;
}

interface Envelope<T> {
  success: boolean;
  data?: T;
  error?: string;
}

// ── real API ────────────────────────────────────────────────────────────────

async function unwrap<T>(res: Response): Promise<T> {
  let body: Envelope<T> | null = null;
  try {
    body = (await res.json()) as Envelope<T>;
  } catch {
    /* ignore */
  }
  if (!res.ok || !body || !body.success || body.data === undefined) {
    const detail = body?.error ? `: ${body.error}` : '';
    throw new Error(`HTTP ${res.status} ${res.statusText}${detail}`);
  }
  return body.data;
}

const get = <T>(path: string, signal?: AbortSignal) =>
  fetch(`${API_BASE_URL}/crm${path}`, { signal, credentials: 'include' }).then(
    (r) => unwrap<T>(r),
  );

function clientQueryString(q: ClientQuery): string {
  const p = new URLSearchParams();
  if (q.q) p.set('q', q.q);
  if (q.advisor) p.set('advisor', q.advisor);
  if (q.segment) p.set('segment', q.segment);
  if (q.status) p.set('status', q.status);
  if (q.limit) p.set('limit', String(q.limit));
  const s = p.toString();
  return s ? `?${s}` : '';
}

const realApi = {
  getSummary: (signal?: AbortSignal) => get<CrmSummary>('/summary', signal),
  getFilters: (signal?: AbortSignal) => get<CrmFilters>('/filters', signal),
  getClients: (q: ClientQuery = {}, signal?: AbortSignal) =>
    get<CrmClient[]>(`/clients${clientQueryString(q)}`, signal),
  getClient: (leadId: string, signal?: AbortSignal) =>
    get<CrmClientDetail>(`/clients/${encodeURIComponent(leadId)}`, signal),
  getClientActivities: (leadId: string, signal?: AbortSignal) =>
    get<CrmActivity[]>(`/clients/${encodeURIComponent(leadId)}/activities`, signal),
  getClientOpportunities: (leadId: string, signal?: AbortSignal) =>
    get<CrmOpportunity[]>(`/clients/${encodeURIComponent(leadId)}/opportunities`, signal),
  getClientAccounts: (leadId: string, signal?: AbortSignal) =>
    get<CrmAccount[]>(`/clients/${encodeURIComponent(leadId)}/accounts`, signal),
  getClientFlows: (leadId: string, signal?: AbortSignal) =>
    get<CrmFlowPoint[]>(`/clients/${encodeURIComponent(leadId)}/flows`, signal),
  getClientPortfolio: (leadId: string, signal?: AbortSignal) =>
    get<CrmPortfolio | null>(`/clients/${encodeURIComponent(leadId)}/portfolio`, signal),
  getOpportunities: (signal?: AbortSignal) => get<CrmOpportunity[]>('/opportunities', signal),
  getTasks: (owner?: string, signal?: AbortSignal) =>
    get<CrmTask[]>(`/tasks${owner ? `?owner=${encodeURIComponent(owner)}` : ''}`, signal),
  getAdvisors: (signal?: AbortSignal) => get<CrmAdvisor[]>('/advisors', signal),
  getAdvisor: (userId: string, signal?: AbortSignal) =>
    get<CrmAdvisorDetail>(`/advisors/${encodeURIComponent(userId)}`, signal),
  getAdvisorBook: (userId: string, signal?: AbortSignal) =>
    get<CrmBook>(`/advisors/${encodeURIComponent(userId)}/book`, signal),
  // Cross-app: find this client's plan in the Financial Planning tool by name.
  findPlan: async (clientName: string, signal?: AbortSignal): Promise<CrmPlanLink | null> => {
    try {
      // Planning lives under the same API host at /v1 (registered at /api/v1).
      const base = API_BASE_URL.replace(/\/$/, '');
      const res = await fetch(`${base}/v1/households`, { signal, credentials: 'include' });
      if (!res.ok) return null;
      const body = (await res.json()) as { households?: { id: string; name: string; source: string }[] };
      const target = clientName.trim().toLowerCase();
      const hit = (body.households ?? []).find((h) => h.name.trim().toLowerCase() === target)
        ?? (body.households ?? []).find((h) => {
          const n = h.name.trim().toLowerCase();
          return n.includes(target) || target.includes(n);
        });
      return hit ? { household_id: hit.id, name: hit.name, source: hit.source } : null;
    } catch {
      return null;
    }
  },
};

// ── demo API (offline, deterministic) ─────────────────────────────────────────

const DEMO_ADVISORS: CrmAdvisor[] = [
  { advisor_id: 'u1', name: 'Bill Jones', region: 'West', title: 'Senior Advisor', email: 'bill.jones@allworth.com', client_count: 3, total_aum: 42_800_000 },
  { advisor_id: 'u2', name: 'Maria Chen', region: 'Central', title: 'Wealth Advisor', email: 'maria.chen@allworth.com', client_count: 2, total_aum: 31_500_000 },
  { advisor_id: 'u3', name: 'David Okafor', region: 'East', title: 'Advisor', email: 'david.okafor@allworth.com', client_count: 1, total_aum: 9_200_000 },
];

const DEMO_CLIENTS: CrmClientDetail[] = [
  {
    lead_id: 'L1001', name: 'Kevin & Kim Anderson', state: 'CA', hh_status: 'Active',
    segment: 'A-List Client', channel: 'Referral', stage: 'Client', job_title: 'Senior VP at Acme Tech',
    aum: 18_400_000, paum: 1_000_000, advisor_id: 'u1', advisor_name: 'Bill Jones', avhhid: 'AV1001',
    sf_url: '', email: 'kevin.anderson@acme.com', phone: '617-555-7274', address: '128 Marina Blvd',
    zip: '94107', aum_billed: 17_900_000, hhid: 'HH-8842', secondary_advisor_id: 'u2',
  },
  {
    lead_id: 'L1002', name: 'Sandra Whitfield', state: 'CA', hh_status: 'Active',
    segment: 'Premier', channel: 'Seminar', stage: 'Client', job_title: 'Retired Partner',
    aum: 14_200_000, paum: 0, advisor_id: 'u1', advisor_name: 'Bill Jones', avhhid: 'AV1002',
    sf_url: '', email: 'sandra.whitfield@example.com', phone: '415-555-3391', address: '9 Vista Court',
    zip: '94110', aum_billed: 14_000_000, hhid: 'HH-8843', secondary_advisor_id: '',
  },
  {
    lead_id: 'L1003', name: 'The Patel Family Trust', state: 'WA', hh_status: 'Active',
    segment: 'A-List Client', channel: 'Referral', stage: 'Client', job_title: 'Business Owner',
    aum: 10_200_000, paum: 250_000, advisor_id: 'u1', advisor_name: 'Bill Jones', avhhid: 'AV1003',
    sf_url: '', email: 'raj.patel@example.com', phone: '206-555-1180', address: '540 Lakeview Dr',
    zip: '98052', aum_billed: 9_800_000, hhid: 'HH-8844', secondary_advisor_id: '',
  },
  {
    lead_id: 'L1004', name: 'Thomas & Grace Lee', state: 'IL', hh_status: 'Active',
    segment: 'Premier', channel: 'Digital', stage: 'Client', job_title: 'Physician',
    aum: 21_500_000, paum: 0, advisor_id: 'u2', advisor_name: 'Maria Chen', avhhid: 'AV1004',
    sf_url: '', email: 'grace.lee@example.com', phone: '312-555-4420', address: '77 Prairie Ave',
    zip: '60605', aum_billed: 21_000_000, hhid: 'HH-8845', secondary_advisor_id: '',
  },
  {
    lead_id: 'L1005', name: 'Nguyen Household', state: 'TX', hh_status: 'Prospect',
    segment: 'Emerging', channel: 'Referral', stage: 'Proposal', job_title: 'Engineer',
    aum: 0, paum: 2_400_000, advisor_id: 'u2', advisor_name: 'Maria Chen', avhhid: '',
    sf_url: '', email: 'lan.nguyen@example.com', phone: '512-555-9902', address: '210 Congress Ave',
    zip: '78701', aum_billed: 0, hhid: 'HH-8846', secondary_advisor_id: '',
  },
  {
    lead_id: 'L1006', name: 'Robert Delgado', state: 'NY', hh_status: 'Active',
    segment: 'Premier', channel: 'Event', stage: 'Client', job_title: 'Attorney',
    aum: 9_200_000, paum: 0, advisor_id: 'u3', advisor_name: 'David Okafor', avhhid: 'AV1006',
    sf_url: '', email: 'robert.delgado@example.com', phone: '212-555-6640', address: '18 Hudson St',
    zip: '10013', aum_billed: 9_000_000, hhid: 'HH-8847', secondary_advisor_id: '',
  },
];

const DEMO_ACTIVITIES: Record<string, CrmActivity[]> = {
  L1001: [
    { id: 'a1', activity_type: 'call', subject: 'Call Kevin Anderson', status: 'Completed', call_disposition: 'Reached', completed_by: 'Bill Jones', created: '2026-07-28 14:05:00', owner_name: 'Bill Jones' },
    { id: 'a2', activity_type: 'event', subject: 'Annual review meeting', status: 'Completed', call_disposition: '', completed_by: 'Bill Jones', created: '2026-07-22 17:00:00', owner_name: 'Bill Jones' },
    { id: 'a3', activity_type: 'meeting', subject: '401k rollover setup', status: 'Open', call_disposition: '', completed_by: '', created: '2026-07-15 10:30:00', owner_name: 'Bill Jones' },
    { id: 'a4', activity_type: 'task', subject: 'Send updated IPS', status: 'Open', call_disposition: '', completed_by: '', created: '2026-07-13 09:00:00', owner_name: 'Bill Jones' },
  ],
  L1004: [
    { id: 'a5', activity_type: 'meeting', subject: 'Estate planning intro', status: 'Completed', call_disposition: '', completed_by: 'Maria Chen', created: '2026-07-26 15:30:00', owner_name: 'Maria Chen' },
    { id: 'a6', activity_type: 'call', subject: 'Quarterly check-in', status: 'Completed', call_disposition: 'Left voicemail', completed_by: 'Maria Chen', created: '2026-07-10 11:15:00', owner_name: 'Maria Chen' },
  ],
  L1005: [
    { id: 'a7', activity_type: 'appointment', subject: 'Proposal presentation', status: 'Open', call_disposition: '', completed_by: '', created: '2026-07-30 13:00:00', owner_name: 'Maria Chen' },
  ],
};

const DEMO_OPPORTUNITIES: CrmOpportunity[] = [
  { lead_id: 'L1005', name: 'Nguyen Household', paum: 2_400_000, stage: 'Proposal', days_in_stage: 12, score: 88, channel: 'Referral', advisor_name: 'Maria Chen', region: 'Central', expected_close_date: '2026-08-29', last_activity_date: '2026-07-30', next_activity_date: '2026-08-05', sf_url: '' },
  { lead_id: 'L1001', name: 'Kevin & Kim Anderson', paum: 1_000_000, stage: 'Verbal Commitment', days_in_stage: 5, score: 82, channel: 'Referral', advisor_name: 'Bill Jones', region: 'West', expected_close_date: '2026-08-15', last_activity_date: '2026-07-28', next_activity_date: '2026-08-02', sf_url: '' },
  { lead_id: 'L1003', name: 'The Patel Family Trust', paum: 250_000, stage: 'Engaged', days_in_stage: 20, score: 61, channel: 'Referral', advisor_name: 'Bill Jones', region: 'West', expected_close_date: '2026-09-30', last_activity_date: '2026-07-18', next_activity_date: '2026-08-08', sf_url: '' },
];

const DEMO_TASKS: CrmTask[] = [
  { id: 'a4', subject: 'Send updated IPS', status: 'Open', activity_type: 'task', lead_id: 'L1001', created: '2026-07-13 09:00:00', owner_name: 'Bill Jones', client_name: 'Kevin & Kim Anderson', sf_url: '' },
  { id: 't2', subject: 'Follow up on beneficiary form', status: 'Open', activity_type: 'task', lead_id: 'L1004', created: '2026-07-27 08:30:00', owner_name: 'Maria Chen', client_name: 'Thomas & Grace Lee', sf_url: '' },
  { id: 't3', subject: 'Prepare proposal deck', status: 'Open', activity_type: 'task', lead_id: 'L1005', created: '2026-07-29 16:45:00', owner_name: 'Maria Chen', client_name: 'Nguyen Household', sf_url: '' },
];

const DEMO_ACCOUNTS: Record<string, CrmAccount[]> = {
  L1001: [
    { account_id: 'ac1', account_name: 'Anderson Joint Trust', account_type: 'Trust', master_category: 'Taxable', custodian: 'Fidelity', taxable: 'Yes', total_value: 9_800_000, current_cash: 240_000, rmd_total: 0, rmd_satisfied: '' },
    { account_id: 'ac2', account_name: 'Kevin Anderson Rollover IRA', account_type: 'IRA', master_category: 'Qualified', custodian: 'Fidelity', taxable: 'No', total_value: 6_400_000, current_cash: 120_000, rmd_total: 185_000, rmd_satisfied: 'No' },
    { account_id: 'ac3', account_name: 'Kim Anderson Roth IRA', account_type: 'Roth IRA', master_category: 'Qualified', custodian: 'Schwab', taxable: 'No', total_value: 2_200_000, current_cash: 40_000, rmd_total: 0, rmd_satisfied: '' },
  ],
  L1004: [
    { account_id: 'ac4', account_name: 'Lee Family Trust', account_type: 'Trust', master_category: 'Taxable', custodian: 'Schwab', taxable: 'Yes', total_value: 15_500_000, current_cash: 410_000, rmd_total: 0, rmd_satisfied: '' },
    { account_id: 'ac5', account_name: 'Thomas Lee 401(k) Rollover', account_type: 'IRA', master_category: 'Qualified', custodian: 'Schwab', taxable: 'No', total_value: 6_000_000, current_cash: 95_000, rmd_total: 92_000, rmd_satisfied: 'Yes' },
  ],
};

// 12 months of book-shaped AUM + flow history, deterministic.
const demoFlows = (base: number, drift: number): CrmFlowPoint[] =>
  Array.from({ length: 12 }, (_, i) => {
    const month = i + 8; // Aug last year → Jul this year
    const year = month > 12 ? 2026 : 2025;
    const m = ((month - 1) % 12) + 1;
    const wave = Math.sin(i * 1.3);
    return {
      period: `${year}-${String(m).padStart(2, '0')}-28`,
      total_value: Math.round(base + drift * i + wave * base * 0.015),
      ncnm: Math.round(drift * 0.6 + wave * 220_000),
      acquisition: i % 5 === 2 ? Math.round(base * 0.01) : 0,
      attrition: i % 7 === 5 ? -Math.round(base * 0.006) : 0,
      distribution: -Math.round(base * 0.0018),
      income: Math.round(base * 0.0011),
      mgmt_fee: -Math.round(base * 0.0008),
    };
  });

const DEMO_CLIENT_FLOWS: Record<string, CrmFlowPoint[]> = {
  L1001: demoFlows(17_600_000, 70_000),
  L1002: demoFlows(13_800_000, 35_000),
  L1003: demoFlows(9_700_000, 45_000),
  L1004: demoFlows(20_400_000, 95_000),
  L1006: demoFlows(8_900_000, 25_000),
};

const DEMO_BOOKS: Record<string, Omit<CrmBook, 'allocation'>> = {
  u1: {
    flows: demoFlows(41_200_000, 140_000),
    segments: [
      { segment: 'A-List Client', clients: 2, aum: 28_600_000 },
      { segment: 'Premier', clients: 1, aum: 14_200_000 },
    ],
    needs_attention: [
      { lead_id: 'L1002', name: 'Sandra Whitfield', aum: 14_200_000, last_activity: '2026-04-02', sf_url: '' },
      { lead_id: 'L1003', name: 'The Patel Family Trust', aum: 10_200_000, last_activity: '2026-04-18', sf_url: '' },
    ],
    pipeline: [],
    rmds: {
      count: 1,
      total: 185_000,
      items: [{ lead_id: 'L1001', client_name: 'Kevin & Kim Anderson', account_name: 'Kevin Anderson Rollover IRA', amount: 185_000 }],
    },
    open_tasks: 1,
  },
  u2: {
    flows: demoFlows(30_100_000, 180_000),
    segments: [
      { segment: 'Premier', clients: 1, aum: 21_500_000 },
      { segment: 'Emerging', clients: 1, aum: 0 },
    ],
    needs_attention: [],
    pipeline: [],
    rmds: { count: 0, total: 0, items: [] },
    open_tasks: 2,
  },
  u3: {
    flows: demoFlows(8_900_000, 25_000),
    segments: [{ segment: 'Premier', clients: 1, aum: 9_200_000 }],
    needs_attention: [
      { lead_id: 'L1006', name: 'Robert Delgado', aum: 9_200_000, last_activity: null, sf_url: '' },
    ],
    pipeline: [],
    rmds: { count: 0, total: 0, items: [] },
    open_tasks: 0,
  },
};

// Demo plan links: which CRM clients have a household in Financial Planning.
const DEMO_PLANS: Record<string, CrmPlanLink> = {
  'kevin & kim anderson': { household_id: 'demo-plan-1', name: 'Kevin & Kim Anderson', source: 'planning' },
  'thomas & grace lee': { household_id: 'demo-plan-2', name: 'Thomas & Grace Lee', source: 'datawarehouse' },
};

const demoAllocation = (equity: number, intl: number, fixed: number, cash: number, base: number): CrmAllocationSlice[] => {
  const raw = [
    { label: 'US equities', pct: equity },
    { label: 'International equities', pct: intl },
    { label: 'Fixed income', pct: fixed },
    { label: 'Cash', pct: cash },
  ];
  return raw.map((s) => ({ ...s, value: Math.round(base * (s.pct / 100)) }));
};

const demoPerformance = (): CrmPerformancePoint[] =>
  Array.from({ length: 12 }, (_, i) => {
    const month = i + 8;
    const year = month > 12 ? 2026 : 2025;
    const m = ((month - 1) % 12) + 1;
    return {
      period: `${year}-${String(m).padStart(2, '0')}-28`,
      mtd_pct: Number((Math.sin(i * 1.7) * 2.4 + 0.6).toFixed(2)),
    };
  });

const DEMO_PORTFOLIOS: Record<string, CrmPortfolio> = {
  L1001: {
    as_of: '2026-07-28',
    allocation: demoAllocation(58.2, 14.6, 21.4, 5.8, 18_400_000),
    beta: 0.86,
    duration: 5.4,
    yield_pct: 2.1,
    performance: demoPerformance(),
    ytd_pct: 6.42,
    holdings: [
      { symbol: 'VTI', custodian: 'Fidelity', market_value: 3_820_000, cost_basis: 2_610_000, unrealized: 1_210_000 },
      { symbol: 'AVGO', custodian: 'Fidelity', market_value: 2_140_000, cost_basis: 940_000, unrealized: 1_200_000 },
      { symbol: 'VXUS', custodian: 'Fidelity', market_value: 1_930_000, cost_basis: 1_720_000, unrealized: 210_000 },
      { symbol: 'BND', custodian: 'Schwab', market_value: 1_650_000, cost_basis: 1_700_000, unrealized: -50_000 },
      { symbol: 'MUB', custodian: 'Schwab', market_value: 1_280_000, cost_basis: 1_235_000, unrealized: 45_000 },
    ],
  },
  L1004: {
    as_of: '2026-07-28',
    allocation: demoAllocation(49.5, 12.1, 30.9, 7.5, 21_500_000),
    beta: 0.72,
    duration: 6.2,
    yield_pct: 2.6,
    performance: demoPerformance(),
    ytd_pct: 4.87,
    holdings: [
      { symbol: 'SCHB', custodian: 'Schwab', market_value: 4_400_000, cost_basis: 3_300_000, unrealized: 1_100_000 },
      { symbol: 'SCHZ', custodian: 'Schwab', market_value: 3_900_000, cost_basis: 3_950_000, unrealized: -50_000 },
      { symbol: 'SCHF', custodian: 'Schwab', market_value: 2_100_000, cost_basis: 1_800_000, unrealized: 300_000 },
    ],
  },
};

const DEMO_BOOK_ALLOCATION = demoAllocation(55.4, 13.8, 24.2, 6.6, 42_800_000);

const delay = <T>(value: T): Promise<T> =>
  new Promise((resolve) => setTimeout(() => resolve(value), 120));

function filterClients(q: ClientQuery): CrmClient[] {
  const needle = (q.q || '').trim().toLowerCase();
  return DEMO_CLIENTS.filter((c) => {
    if (needle && !c.name.toLowerCase().includes(needle)) return false;
    if (q.advisor && c.advisor_id !== q.advisor) return false;
    if (q.segment && c.segment !== q.segment) return false;
    if (q.status && c.hh_status !== q.status) return false;
    return true;
  }).sort((a, b) => b.aum - a.aum);
}

const demoApi: typeof realApi = {
  getSummary: () =>
    delay({
      total_clients: DEMO_CLIENTS.length,
      total_advisors: DEMO_ADVISORS.length,
      open_opportunities: DEMO_OPPORTUNITIES.length,
      open_pipeline_paum: DEMO_OPPORTUNITIES.reduce((s, o) => s + o.paum, 0),
    }),
  getFilters: () =>
    delay({
      segments: [...new Set(DEMO_CLIENTS.map((c) => c.segment))].sort(),
      channels: [...new Set(DEMO_CLIENTS.map((c) => c.channel))].sort(),
      statuses: [...new Set(DEMO_CLIENTS.map((c) => c.hh_status))].sort(),
    }),
  getClients: (q = {}) => delay(filterClients(q)),
  getClient: (leadId) => {
    const c = DEMO_CLIENTS.find((x) => x.lead_id === leadId);
    if (!c) return Promise.reject(new Error('Client not found'));
    return delay(c);
  },
  getClientActivities: (leadId) => delay(DEMO_ACTIVITIES[leadId] ?? []),
  getClientOpportunities: (leadId) =>
    delay(DEMO_OPPORTUNITIES.filter((o) => o.lead_id === leadId)),
  getClientAccounts: (leadId) => delay(DEMO_ACCOUNTS[leadId] ?? []),
  getClientFlows: (leadId) => delay(DEMO_CLIENT_FLOWS[leadId] ?? []),
  getClientPortfolio: (leadId) => delay(DEMO_PORTFOLIOS[leadId] ?? null),
  getOpportunities: () => delay([...DEMO_OPPORTUNITIES].sort((a, b) => b.score - a.score)),
  getTasks: (owner) => {
    if (!owner) return delay(DEMO_TASKS);
    // Accept either the advisor id or display name as the owner filter.
    const name = DEMO_ADVISORS.find((a) => a.advisor_id === owner)?.name ?? owner;
    return delay(DEMO_TASKS.filter((t) => t.owner_name === name));
  },
  getAdvisors: () => delay([...DEMO_ADVISORS].sort((a, b) => b.total_aum - a.total_aum)),
  getAdvisor: (userId) => {
    const advisor = DEMO_ADVISORS.find((a) => a.advisor_id === userId);
    if (!advisor) return Promise.reject(new Error('Advisor not found'));
    return delay({
      advisor,
      clients: DEMO_CLIENTS.filter((c) => c.advisor_id === userId).sort((a, b) => b.aum - a.aum),
    });
  },
  getAdvisorBook: (userId) => {
    const book = DEMO_BOOKS[userId];
    if (!book) return Promise.reject(new Error('Advisor not found'));
    // Surface the advisor's live pipeline from the shared demo opportunity list.
    const advisor = DEMO_ADVISORS.find((a) => a.advisor_id === userId);
    return delay({
      ...book,
      allocation: DEMO_BOOK_ALLOCATION,
      pipeline: DEMO_OPPORTUNITIES.filter((o) => o.advisor_name === advisor?.name),
    });
  },
  findPlan: (clientName) => delay(DEMO_PLANS[clientName.trim().toLowerCase()] ?? null),
};

export const crmApi = DEMO_MODE ? demoApi : realApi;
