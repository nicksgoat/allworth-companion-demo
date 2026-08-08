// Isolated fetch helper for the /nfbc console. Modeled on services/refreshLog.ts.
// Uses the shared /api base and attaches X-User-Email (resolved via MSAL) for
// server-side attribution of writes.

import { resolveUserEmail } from '../../services/auth';
import type {
  QueueResponse,
  EditPatch,
  ConfirmResponse,
  AuditResponse,
  NfbcRow,
  HouseholdInvestigation,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

let _userEmail: string | null | undefined;
async function userHeaders(): Promise<Record<string, string>> {
  if (_userEmail === undefined) {
    try {
      _userEmail = await resolveUserEmail();
    } catch {
      _userEmail = null;
    }
  }
  return _userEmail ? { 'X-User-Email': _userEmail } : {};
}

async function parseJson<T>(res: Response): Promise<T> {
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new Error(`HTTP ${res.status} ${res.statusText}`);
  }
  if (!res.ok) {
    const err = (body as { error?: string })?.error;
    throw new Error(err || `HTTP ${res.status} ${res.statusText}`);
  }
  return body as T;
}

export async function fetchQueue(
  opts: { status?: string; refresh?: boolean; signal?: AbortSignal } = {}
): Promise<QueueResponse> {
  const params = new URLSearchParams();
  params.set('status', opts.status ?? 'open');
  if (opts.refresh) params.set('refresh', '1');
  const res = await fetch(`${API_BASE_URL}/nfbc/queue?${params.toString()}`, {
    signal: opts.signal,
  });
  return parseJson<QueueResponse>(res);
}

export async function editRow(rowId: string, patch: EditPatch): Promise<{ ok: boolean; row: NfbcRow }> {
  const res = await fetch(`${API_BASE_URL}/nfbc/queue/${encodeURIComponent(rowId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
    body: JSON.stringify(patch),
  });
  return parseJson<{ ok: boolean; row: NfbcRow }>(res);
}

export async function confirmRow(rowId: string, resume = false): Promise<ConfirmResponse> {
  const res = await fetch(`${API_BASE_URL}/nfbc/queue/${encodeURIComponent(rowId)}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
    body: JSON.stringify({ resume }),
  });
  // confirm returns structured errors (409/422/500/502) we want to surface, not throw raw
  let body: ConfirmResponse;
  try {
    body = (await res.json()) as ConfirmResponse;
  } catch {
    throw new Error(`HTTP ${res.status} ${res.statusText}`);
  }
  return body;
}

export async function fetchAudit(): Promise<AuditResponse> {
  const res = await fetch(`${API_BASE_URL}/nfbc/audit`);
  return parseJson<AuditResponse>(res);
}

export async function fetchHousehold(avhhid: number | string): Promise<HouseholdInvestigation> {
  const res = await fetch(`${API_BASE_URL}/nfbc/household/${encodeURIComponent(String(avhhid))}`);
  return parseJson<HouseholdInvestigation>(res);
}
