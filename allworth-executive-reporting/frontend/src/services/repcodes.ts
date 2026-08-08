// src/services/repcodes.ts
// Typed fetch helpers for the editable Rep Codes page.

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

export interface RepcodeRow {
  repcode_id: number;
  custodian: string | null;
  actively_used: boolean | null;
  wrap_fee_type: string | null;
  for_employee_accounts: boolean | null;
  fidelity_g_number: string | null;
  g_number_usage: string | null;
  description: string | null;
  notes: string | null;
  schwab_master_account: string | null;
  master_account_type: string | null;
  allworth_advisor: string | null;
  allworth_office: string | null;
  separate_account_manager: string | null;
  sma_strategy: string | null;
  other_third_party: string | null;
  american_funds_rep_number: string | null;
  american_funds_branch_number: string | null;
  bloomwell_529_rep_code: string | null;
  modified_by: string | null;
  modified_at: string | null;
}

export interface RepcodeListResponse {
  success: boolean;
  columns: string[];
  editable_columns: string[];
  bit_columns: string[];
  rows: RepcodeRow[];
  error?: string;
}

interface BaseResponse {
  success: boolean;
  error?: string;
}

const handle = async <T extends BaseResponse>(res: Response): Promise<T> => {
  let body: T | null = null;
  try {
    body = (await res.json()) as T;
  } catch {
    /* ignore */
  }
  if (!res.ok || !body || !body.success) {
    const detail = body?.error ? `: ${body.error}` : '';
    throw new Error(`HTTP ${res.status} ${res.statusText}${detail}`);
  }
  return body;
};

export const fetchRepcodes = async (signal?: AbortSignal) =>
  handle<RepcodeListResponse>(
    await fetch(`${API_BASE_URL}/repcodes/`, { signal, credentials: 'include' })
  );

export type RepcodeWritePayload = Partial<Omit<RepcodeRow, 'repcode_id' | 'modified_by' | 'modified_at'>>;

export const createRepcode = async (payload: RepcodeWritePayload) =>
  handle<{ success: boolean; repcode_id: number; error?: string }>(
    await fetch(`${API_BASE_URL}/repcodes/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    })
  );

export const updateRepcode = async (id: number, payload: RepcodeWritePayload) =>
  handle<{ success: boolean; repcode_id: number; error?: string }>(
    await fetch(`${API_BASE_URL}/repcodes/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(payload),
    })
  );

export const deleteRepcode = async (id: number) =>
  handle<{ success: boolean; repcode_id: number; error?: string }>(
    await fetch(`${API_BASE_URL}/repcodes/${id}`, {
      method: 'DELETE',
      credentials: 'include',
    })
  );

export type BulkMatchKey = 'fidelity_g_number' | 'schwab_master_account';

export interface BulkUpsertResult {
  success: boolean;
  inserted: number;
  updated: number;
  total: number;
  errors: Array<{ row_index: number; error: string }>;
  batch_id: string | null;
  error?: string;
}

export const bulkUpsertRepcodes = async (
  matchKey: BulkMatchKey,
  rows: RepcodeWritePayload[]
) =>
  handle<BulkUpsertResult>(
    await fetch(`${API_BASE_URL}/repcodes/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ match_key: matchKey, rows }),
    })
  );

// ---------------------------------------------------------------------------
// Change history + rollback
// ---------------------------------------------------------------------------

export type RepcodeOperation =
  | 'INSERT'
  | 'UPDATE'
  | 'DELETE'
  | 'RESTORE'
  | 'BASELINE';

// A history row carries the full row snapshot (the editable columns) plus
// audit metadata. We reuse the editable fields of RepcodeRow.
export interface RepcodeHistoryRow
  extends Omit<RepcodeRow, 'repcode_id' | 'modified_by' | 'modified_at'> {
  history_id: number;
  repcode_id: number;
  operation: RepcodeOperation;
  batch_id: string | null;
  source: string | null;
  changed_by: string | null;
  changed_at: string | null;
}

export interface HistoryListResponse {
  success: boolean;
  rows: RepcodeHistoryRow[];
  editable_columns: string[];
  error?: string;
}

export const fetchRowHistory = async (id: number, signal?: AbortSignal) =>
  handle<HistoryListResponse>(
    await fetch(`${API_BASE_URL}/repcodes/${id}/history`, {
      signal,
      credentials: 'include',
    })
  );

export const fetchRecentHistory = async (limit = 50, signal?: AbortSignal) =>
  handle<HistoryListResponse>(
    await fetch(`${API_BASE_URL}/repcodes/history?limit=${limit}`, {
      signal,
      credentials: 'include',
    })
  );

export const restoreVersion = async (id: number, historyId: number) =>
  handle<{ success: boolean; repcode_id: number; restored_from: number; outcome: string; error?: string }>(
    await fetch(`${API_BASE_URL}/repcodes/${id}/restore/${historyId}`, {
      method: 'POST',
      credentials: 'include',
    })
  );

export const undoChange = async (historyId: number) =>
  handle<{ success: boolean; repcode_id: number; outcome: string; error?: string }>(
    await fetch(`${API_BASE_URL}/repcodes/history/${historyId}/undo`, {
      method: 'POST',
      credentials: 'include',
    })
  );

export const undoBatch = async (batchId: string) =>
  handle<{ success: boolean; batch_id: string; reverted: number; deleted: number; total: number; error?: string }>(
    await fetch(`${API_BASE_URL}/repcodes/history/batch/${batchId}/undo`, {
      method: 'POST',
      credentials: 'include',
    })
  );
