// Client for the Executive Brief backend (/brief/api/*).
//
// The backend decides mock vs live (USE_LIVE_MAIL + Easy Auth Graph token).
// The frontend reads /status once; when mode === 'live' the store/detail/
// composer call the live endpoints, otherwise they use bundled mock data.
// Every live call has a mock fallback at the call site, so a backend hiccup
// degrades to the demo rather than a blank screen.

import type { EmailAnalysis, ExecutiveEmail, ThreadMessage } from './types';
import { parseAnalysis } from './validate';

const BASE = '/brief/api';

export type BriefMode = 'live' | 'mock';

export type BriefStatus = {
  mode: BriefMode;
  use_live_mail: boolean;
  graph_token_available: boolean;
  anthropic_configured: boolean;
  user: string | null;
};

let _statusCache: BriefStatus | null = null;

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${path} → ${res.status}`);
  return (await res.json()) as T;
}

/** Read the capability report once; defaults to mock on any error. */
export async function getStatus(): Promise<BriefStatus> {
  if (_statusCache) return _statusCache;
  try {
    const s = await getJson<Partial<BriefStatus> & { mode?: BriefMode }>('/status');
    _statusCache = {
      mode: s.mode === 'live' ? 'live' : 'mock',
      use_live_mail: Boolean(s.use_live_mail),
      graph_token_available: Boolean(s.graph_token_available),
      anthropic_configured: Boolean(s.anthropic_configured),
      user: s.user ?? null,
    };
  } catch {
    _statusCache = {
      mode: 'mock',
      use_live_mail: false,
      graph_token_available: false,
      anthropic_configured: false,
      user: null,
    };
  }
  return _statusCache;
}

export async function isLive(): Promise<boolean> {
  return (await getStatus()).mode === 'live';
}

/** Live inbox as ExecutiveEmail[]. Throws on failure so the caller can fall
 * back to bundled mock data. */
export async function fetchLiveEmails(): Promise<ExecutiveEmail[]> {
  const data = await getJson<{ success: boolean; mode: BriefMode; emails: ExecutiveEmail[] }>('/messages');
  if (!data.success || data.mode !== 'live') throw new Error('not live');
  return data.emails;
}

export type LiveDetail = {
  thread: ThreadMessage[];
  analysis: EmailAnalysis | null;
};

/** Live message detail: thread + validated analysis (null → safe fallback). */
export async function fetchLiveDetail(id: string): Promise<LiveDetail> {
  const data = await getJson<{
    success: boolean;
    thread: { id: string; from: string; fromEmail: string; sentAt: string; body: string }[];
    analysis: unknown;
  }>(`/messages/${encodeURIComponent(id)}`);
  if (!data.success) throw new Error('detail fetch failed');
  return {
    thread: (data.thread ?? []).map((m) => ({
      id: m.id,
      from: m.from,
      fromEmail: m.fromEmail,
      sentAt: m.sentAt,
      body: m.body,
    })),
    analysis: parseAnalysis(data.analysis),
  };
}

/** Live draft generation. Returns null on failure → caller uses local generator. */
export async function fetchLiveDraft(id: string, intent: string, tone: string): Promise<string | null> {
  try {
    const data = await getJson<{ success: boolean; draft?: string }>('/draft-reply', {
      method: 'POST',
      body: JSON.stringify({ id, intent, tone }),
    });
    return data.success && data.draft ? data.draft : null;
  } catch {
    return null;
  }
}

/** Persist a reviewed draft. Returns where it landed ('outlook' | 'local'). */
export async function saveLiveDraft(id: string, text: string): Promise<'outlook' | 'local'> {
  try {
    const data = await getJson<{ success: boolean; saved?: string }>('/save-draft', {
      method: 'POST',
      body: JSON.stringify({ id, text }),
    });
    return data.saved === 'outlook' ? 'outlook' : 'local';
  } catch {
    return 'local';
  }
}

/** Send a reviewed reply via Graph. Only ever called after an explicit
 * in-composer confirmation. Resolves to an error string on failure (so the UI
 * can surface it), or null on success. Never retried automatically. */
export async function sendLiveReply(id: string, text: string): Promise<string | null> {
  try {
    const res = await fetch(`${BASE}/send-reply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, text }),
    });
    const data = (await res.json().catch(() => ({}))) as { success?: boolean; error?: string };
    if (res.ok && data.success) return null;
    return data.error ?? `send failed (${res.status})`;
  } catch (e) {
    return e instanceof Error ? e.message : 'send failed';
  }
}
