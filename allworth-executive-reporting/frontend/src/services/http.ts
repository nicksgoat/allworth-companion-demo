import { resolveUserEmail } from './auth';

interface ErrorEnvelope { error?: string; code?: string; detail?: string }

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail?: string;

  constructor(message: string, status: number, code = 'request_failed', detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function authenticatedHeaders(existing?: HeadersInit): Promise<Headers> {
  const headers = new Headers(existing);
  const email = await resolveUserEmail();
  if (email && !headers.has('X-User-Email')) headers.set('X-User-Email', email);
  return headers;
}

export async function requestJson<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...init, headers: await authenticatedHeaders(init.headers) });
  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try { body = JSON.parse(text); }
    catch { throw new ApiError('The server returned an invalid response', response.status, 'invalid_response'); }
  }
  if (!response.ok) {
    const envelope = (body && typeof body === 'object' ? body : {}) as ErrorEnvelope;
    throw new ApiError(envelope.error || `Request failed (${response.status})`, response.status, envelope.code, envelope.detail);
  }
  return body as T;
}
