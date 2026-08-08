/**
 * Email Batch API Service
 * Wraps the Flask email-batch endpoints (backend/app/routers/email_batch.py).
 * The global auth fetch (installAuthFetch) attaches the bearer token to /api/*.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';

export interface EmailBatchGroup {
  id: number;
  advisors: string[];
  email: string | null;
  cc: string[];
  row_count: number;
  subject: string;
  html: string;
  sendable: boolean;
}

export interface PreviewResponse {
  batch_id: string;
  subject: string;
  sender_email: string | null;
  advisor_column: string;
  total_rows: number;
  sendable_rows: number;
  columns: string[];
  rows: EmailBatchRow[];
  numeric_totals: Record<string, number>;
  groups: EmailBatchGroup[];
  missing_advisors: string[];
  warnings: string[];
}

export type RowStatus = 'ready' | 'missing_email' | 'missing_advisor';

export interface EmailBatchRow {
  __advisor: string | null;
  __email: string | null;
  __group_id: number | null;
  __status: RowStatus;
  [column: string]: string | number | boolean | null;
}

export interface SendResult {
  group_id: number;
  email: string | null;
  advisors: string[];
  sent: boolean;
  error: string | null;
}

export interface SendResponse {
  sent_count: number;
  failed_count: number;
  skipped_count: number;
  results: SendResult[];
}

export interface MailerStatus {
  graph_token_available: boolean;
  mailbox_fallback: boolean;
  ready: boolean;
  user: { email: string | null; name: string | null } | null;
}

export async function getMailerStatus(): Promise<MailerStatus> {
  try {
    const res = await fetch(`${API_BASE_URL}/email-batch/status`);
    if (res.ok) return res.json();
  } catch { /* fall through */ }
  return { graph_token_available: false, mailbox_fallback: false, ready: false, user: null };
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === 'string') return data.detail;
    if (data?.detail) return JSON.stringify(data.detail);
  } catch {
    /* fall through */
  }
  return `Request failed (HTTP ${res.status})`;
}

export async function previewEmailBatch(file: File, body?: string): Promise<PreviewResponse> {
  const form = new FormData();
  form.append('file', file);
  if (body != null) form.append('body', body);
  const res = await fetch(`${API_BASE_URL}/email-batch/preview`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function sendEmailBatch(
  batchId: string,
  groupIds?: number[],
  groupCc?: Record<string, string[]>,
  replyTo?: string,
  subject?: string,
): Promise<SendResponse> {
  const res = await fetch(`${API_BASE_URL}/email-batch/send`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ batch_id: batchId, group_ids: groupIds ?? null, group_cc: groupCc ?? null, reply_to: replyTo ?? null, subject: subject ?? null }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}
