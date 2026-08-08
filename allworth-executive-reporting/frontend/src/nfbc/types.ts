// Row + response models for the NFBC console. Mirrors the backend queue JSON
// (backend/nfbc/routes.py + agent.py).

export type NfbcRowStatus =
  | 'proposed'
  | 'needs_review'
  | 'written_pending_jira'
  | 'confirmed'
  | 'error';

export interface Finding {
  type: 'info' | 'warn' | 'success' | 'error';
  title: string;
  detail: string;
}

export interface FlowPeriod {
  reportingperiod: string;
  inflows: number | null;
  outflows: number | null;
  net_flows: number | null;
  total_aum: number | null;
}

export interface ExistingAdjustment {
  reportingperiod: string;
  flow_adjustment: number | null;
  multiplier: number | null;
  adjustment_type: string | null;
}

export interface ConfirmStep {
  done?: boolean;
  error?: string;
  already_present?: boolean;
  rows_affected?: number;
  [k: string]: unknown;
}

export interface ConfirmResult {
  steps: Record<string, ConfirmStep>;
}

export interface NfbcRow {
  row_id: string;
  ticket_key: string;
  ticket_summary: string;
  ticket_status?: string;
  avhhid: number | null;
  household: string | null;
  advisor: string | null;
  period: string | null;
  amount: number | null;
  multiplier?: number;
  adjustment_type: string;
  rationale: string;
  draft_reply: string;
  confidence?: number | null;
  findings?: Finding[];
  computed_vs_claude?: { claude_amount: number | null; code_amount: number | null };
  needs_human_flags?: string[];
  status: NfbcRowStatus;
  flows?: FlowPeriod[];
  existing_adjustments?: ExistingAdjustment[];
  confirm_result?: ConfirmResult;
  confirmed_by?: string;
  confirmed_at?: string;
}

export interface JiraDiag {
  configured: boolean;
  source: 'env' | 'keyvault' | 'missing' | 'kv_error' | null;
  url?: string;
  key_vault?: string;
  kv_error?: string | null;
}

export interface BuildProgress {
  done: number;
  total: number;
  current?: string | null;
}

export interface QueueResponse {
  ok: boolean;
  cached?: boolean;
  building?: boolean;
  progress?: BuildProgress | null;
  built_at?: number;
  rows: NfbcRow[];
  error?: string;
  diag?: JiraDiag;
  jql_ticket_count?: number;
}

export interface EditPatch {
  amount?: number;
  period?: string;
  adjustment_type?: string;
  multiplier?: number;
  draft_reply?: string;
  avhhid?: number | null;
}

export interface ConfirmResponse {
  ok: boolean;
  row_id?: string;
  partial_failure?: boolean;
  steps?: Record<string, ConfirmStep>;
  error?: string;
}

export interface AuditResponse {
  ok: boolean;
  db_adjustments: Array<Record<string, string | number | null>>;
  confirmed?: NfbcRow[];
  actions: Array<Record<string, unknown>>;
}

export interface HouseholdInvestigation {
  ok: boolean;
  dim: Record<string, string | number | null> | null;
  flows: FlowPeriod[];
  adjustments: ExistingAdjustment[];
  fact: Record<string, string | number | null> | null;
  error?: string;
}
