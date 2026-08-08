// src/services/sfp2.ts
// Typed fetch helpers for the SFP2 schema-manager page. Isolated from the
// KPI/Synapse code path so a Synapse outage cannot break this view.

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

export interface DeltaColumn {
  name: string;
  type: string;
  nullable?: boolean;
}

export interface SfField {
  name: string;
  label?: string;
  type?: string;
  length?: number | null;
  precision?: number | null;
  scale?: number | null;
  nillable?: boolean;
  custom?: boolean;
}

export interface SfObjectSummary {
  name: string;
  label?: string;
  custom?: boolean;
  queryable?: boolean;
}

export interface DiffBothRow {
  name: string;
  delta_type: string;
  sf_type?: string;
  sf_label?: string;
  custom?: boolean;
  /** Notebook paths that mention this column name. Present only when non-empty. */
  referenced_in?: string[];
}

export interface DiffOnlyDeltaRow {
  name: string;
  delta_type: string;
  /** Notebook paths that mention this column name. Present only when non-empty. */
  referenced_in?: string[];
}

export interface DiffOnlySfRow extends SfField {}

export interface DiffResponse {
  success: boolean;
  table: string;
  sobject: string;
  counts: {
    delta: number;
    sf: number;
    in_both: number;
    only_in_delta: number;
    only_in_sf: number;
  };
  in_both: DiffBothRow[];
  only_in_delta: DiffOnlyDeltaRow[];
  only_in_sf: DiffOnlySfRow[];
  error?: string;
}

interface BaseResponse {
  success: boolean;
  error?: string;
}

export interface MutationResponse extends BaseResponse {
  status?: number;
  object?: string;
  column?: string;
  delta_type?: string;
  sf_type?: string;
  version?: number;
  /** True when the request was enqueued for the overnight worker (HTTP 202). */
  queued?: boolean;
  /** Spark DDL type the worker will use for an enqueued add. */
  spark_ddl_type?: string;
  /** Human-readable message returned with 202 enqueue responses. */
  message?: string;
  /** 409 from drop_column when delta.columnMapping.mode is not set. */
  remediation?: string;
}

export interface PreviewResponse extends MutationResponse {
  nullable?: boolean;
  warnings?: string[];
}

const handle = async <T extends BaseResponse>(res: Response): Promise<T> => {
  let body: T | null = null;
  try {
    body = (await res.json()) as T;
  } catch {
    /* fallthrough */
  }
  if (!res.ok || !body || !body.success) {
    const detail = body?.error ? `: ${body.error}` : '';
    throw new Error(`HTTP ${res.status} ${res.statusText}${detail}`);
  }
  return body;
};

/**
 * Like `handle`, but returns the parsed body even on a non-success response
 * so the caller can surface structured errors (e.g. 409 + `remediation`).
 * Throws only on transport / non-JSON failures.
 */
const handleStructured = async <T extends BaseResponse>(res: Response): Promise<T> => {
  let body: T | null = null;
  try {
    body = (await res.json()) as T;
  } catch {
    /* fallthrough */
  }
  if (!body) {
    throw new Error(`HTTP ${res.status} ${res.statusText} (no JSON body)`);
  }
  return body;
};

export const fetchSfp2Tables = async (signal?: AbortSignal) =>
  handle<{ success: boolean; tables: { name: string }[]; error?: string }>(
    await fetch(`${API_BASE_URL}/sfp2/tables`, { signal, credentials: 'include' })
  );

export const fetchSfp2SObjects = async (customOnly = false, signal?: AbortSignal) => {
  const qs = customOnly ? '?custom=1' : '';
  return handle<{ success: boolean; sobjects: SfObjectSummary[]; error?: string }>(
    await fetch(`${API_BASE_URL}/sfp2/sobjects${qs}`, { signal, credentials: 'include' })
  );
};

export const fetchSfp2Diff = async (
  table: string,
  sobject: string,
  signal?: AbortSignal
) => {
  const params = new URLSearchParams({ table, sobject });
  return handle<DiffResponse>(
    await fetch(`${API_BASE_URL}/sfp2/diff?${params.toString()}`, {
      signal,
      credentials: 'include',
    })
  );
};

export const previewSfp2Add = async (
  table: string,
  column: string,
  sfField: SfField
) => {
  const res = await fetch(`${API_BASE_URL}/sfp2/columns/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ table, column, sf_field: sfField }),
  });
  return handleStructured<PreviewResponse>(res);
};

export const addSfp2Column = async (
  table: string,
  column: string,
  sfField: SfField
) => {
  const res = await fetch(`${API_BASE_URL}/sfp2/columns`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ table, column, sf_field: sfField }),
  });
  return handleStructured<MutationResponse>(res);
};

export const dropSfp2Column = async (table: string, column: string) => {
  const res = await fetch(`${API_BASE_URL}/sfp2/columns`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ table, column }),
  });
  return handleStructured<MutationResponse>(res);
};

export type SchemaChangeState =
  | 'pending'
  | 'add_pending'
  | 'done'
  | 'failed'
  | 'canceled'
  | 'add_canceled'
  | 'added'
  | 'add_failed'
  | 'superseded'
  | string;

export interface SchemaChangeRow {
  ts?: string;
  action?: string;
  table?: string;
  column?: string;
  sf_type?: string | null;
  delta_type?: string | null;
  user_email?: string | null;
  success?: boolean;
  error?: string | null;
  request_id?: string | null;
  app_version?: string | null;
  state?: SchemaChangeState;
}

export const fetchSfp2SchemaChanges = async (
  table?: string,
  limit = 100,
  signal?: AbortSignal
) => {
  const params = new URLSearchParams();
  if (table) params.set('table', table);
  params.set('limit', String(limit));
  return handle<{ success: boolean; rows: SchemaChangeRow[]; error?: string }>(
    await fetch(`${API_BASE_URL}/sfp2/schema-changes?${params.toString()}`, {
      signal,
      credentials: 'include',
    })
  );
};

export const cancelSfp2PendingDrop = async (table: string, column: string) => {
  const res = await fetch(`${API_BASE_URL}/sfp2/schema-changes/pending`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ table, column }),
  });
  return handleStructured<MutationResponse>(res);
};

