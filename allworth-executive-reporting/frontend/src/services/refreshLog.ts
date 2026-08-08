// src/services/refreshLog.ts
// Isolated fetch helper for the /refresh_log page. Does NOT depend on any
// KPI/Synapse types so a Synapse outage cannot affect this code path.

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

export type TransformationLogRow = Record<string, string | number | boolean | null>;

export interface TransformationLogResponse {
  success: boolean;
  source: string;
  row_count: number;
  columns: string[];
  fetched_at: string;
  rows: TransformationLogRow[];
  error?: string;
}

export interface FetchTransformationLogOptions {
  limit?: number;
  since?: string;
  /** When true, bypasses the server cache. */
  noCache?: boolean;
  signal?: AbortSignal;
}

export const fetchTransformationLog = async (
  opts: FetchTransformationLogOptions = {}
): Promise<TransformationLogResponse> => {
  const params = new URLSearchParams();
  if (opts.limit != null) params.set('limit', String(opts.limit));
  if (opts.since) params.set('since', opts.since);
  if (opts.noCache) params.set('no_cache', '1');

  const qs = params.toString();
  const url = `${API_BASE_URL}/transformation-log${qs ? `?${qs}` : ''}`;

  const res = await fetch(url, { signal: opts.signal });
  if (!res.ok) {
    // Attempt to surface the server's error message
    let detail = '';
    try {
      const body = await res.json();
      detail = body?.error ? `: ${body.error}` : '';
    } catch {
      // ignore
    }
    throw new Error(`HTTP ${res.status} ${res.statusText}${detail}`);
  }

  const body = (await res.json()) as TransformationLogResponse;
  if (!body.success) {
    throw new Error(body.error || 'Unknown error fetching transformation log');
  }
  return body;
};
