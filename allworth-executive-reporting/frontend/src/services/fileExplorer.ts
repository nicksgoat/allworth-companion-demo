// src/services/fileExplorer.ts
// Fetch helper for the File Explorer tool (/api/file-explorer). Uses the shared
// /api base and attaches X-User-Email (resolved via MSAL) for server-side
// attribution. In local-preview DEMO_MODE (npm run dev:demo) there is no
// backend, so calls are served from static sample data so the page renders.

import { resolveUserEmail } from './auth';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export interface DownloadResource {
  id: string;
  label: string;
  root_id: string;
  root_label: string;
  formats: string[];
  last_modified?: string | null;
}

export interface DownloadsResponse {
  resources: DownloadResource[];
  can_manage: boolean;
}

export interface ResourceTreeNode {
  id: string;
  label: string;
  type: 'dir';
  formats: string[];
  tables: { id: string; label: string; type: 'table'; last_modified?: string | null }[];
  error?: string;
}

export interface Principals {
  users: string[];
  groups: { id: string; name: string }[];
}

export interface ShareEntry {
  resource_id: string;
  principal_type: 'user' | 'group';
  principal_id: string;
  created_at?: string;
  created_by?: string;
}

export interface UploadTarget {
  id: string;
  label: string;
  format: string;
  columns: string[];
}

export interface UploadsResponse {
  uploads: UploadTarget[];
  can_manage: boolean;
}

export interface UploadResult {
  stored: string;
  filename: string;
}

// ── auth headers ─────────────────────────────────────────────────────────────

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

function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── real API ─────────────────────────────────────────────────────────────────

const realApi = {
  async getDownloads(): Promise<DownloadsResponse> {
    const res = await fetch(`${API_BASE_URL}/file-explorer/downloads`, {
      headers: { ...(await userHeaders()) },
    });
    return await parseJson<DownloadsResponse>(res);
  },
  async downloadFile(resourceId: string, format: string): Promise<void> {
    const res = await fetch(
      `${API_BASE_URL}/file-explorer/download/${encodeURI(resourceId)}?format=${encodeURIComponent(format)}`,
      { headers: { ...(await userHeaders()) } }
    );
    if (!res.ok) {
      await parseJson(res); // throws with server error message
      return;
    }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    const match = /filename="?([^"]+)"?/.exec(cd);
    const ext = format === 'txt' ? 'txt' : 'csv';
    const filename = match ? match[1] : `${resourceId.split('/').pop()}.${ext}`;
    triggerDownload(blob, filename);
  },
  async getResources(): Promise<ResourceTreeNode[]> {
    const res = await fetch(`${API_BASE_URL}/file-explorer/resources`, {
      headers: { ...(await userHeaders()) },
    });
    return (await parseJson<{ resources: ResourceTreeNode[] }>(res)).resources;
  },
  async getPrincipals(): Promise<Principals> {
    const res = await fetch(`${API_BASE_URL}/file-explorer/principals`, {
      headers: { ...(await userHeaders()) },
    });
    return await parseJson<Principals>(res);
  },
  async getShares(resourceId: string): Promise<ShareEntry[]> {
    const res = await fetch(
      `${API_BASE_URL}/file-explorer/shares/${encodeURI(resourceId)}`,
      { headers: { ...(await userHeaders()) } }
    );
    return (await parseJson<{ shares: ShareEntry[] }>(res)).shares;
  },
  async addShare(
    resourceId: string,
    principalType: 'user' | 'group',
    principalId: string
  ): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/file-explorer/shares`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({
        resource_id: resourceId,
        principal_type: principalType,
        principal_id: principalId,
      }),
    });
    await parseJson<{ ok: boolean }>(res);
  },
  async removeShare(
    resourceId: string,
    principalType: 'user' | 'group',
    principalId: string
  ): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/file-explorer/shares`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({
        resource_id: resourceId,
        principal_type: principalType,
        principal_id: principalId,
      }),
    });
    await parseJson<{ ok: boolean }>(res);
  },
  async getUploads(): Promise<UploadsResponse> {
    const res = await fetch(`${API_BASE_URL}/file-explorer/uploads`, {
      headers: { ...(await userHeaders()) },
    });
    return await parseJson<UploadsResponse>(res);
  },
  async uploadFile(targetId: string, file: File): Promise<UploadResult> {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(
      `${API_BASE_URL}/file-explorer/upload/${encodeURIComponent(targetId)}`,
      { method: 'POST', headers: { ...(await userHeaders()) }, body: form }
    );
    return await parseJson<UploadResult>(res);
  },
};

// ── demo store (offline preview) ─────────────────────────────────────────────

const DEMO_TREE: ResourceTreeNode[] = [
  {
    id: 'recon',
    label: 'Reconciliation',
    type: 'dir',
    formats: ['txt', 'csv'],
    tables: [
      { id: 'recon/cust_positions', label: 'cust_positions', type: 'table', last_modified: '2026-01-15T09:30:00Z' },
      { id: 'recon/trade_recon', label: 'trade_recon', type: 'table', last_modified: '2026-01-14T22:05:00Z' },
    ],
  },
];

let _demoShares: ShareEntry[] = [];

const demoApi: typeof realApi = {
  async getDownloads() {
    return {
      can_manage: true,
      resources: DEMO_TREE.flatMap((r) =>
        r.tables.map((t) => ({
          id: t.id,
          label: t.label,
          root_id: r.id,
          root_label: r.label,
          formats: r.formats,
          last_modified: t.last_modified ?? null,
        }))
      ),
    };
  },
  async downloadFile(resourceId, format) {
    const ext = format === 'txt' ? 'txt' : 'csv';
    const sep = format === 'txt' ? '\t' : ',';
    const body = `col_a${sep}col_b\n1${sep}demo\n2${sep}preview\n`;
    triggerDownload(new Blob([body]), `${resourceId.split('/').pop()}.${ext}`);
  },
  async getResources() {
    return DEMO_TREE;
  },
  async getPrincipals() {
    return {
      users: ['jane.advisor@allworth.com', 'sam.analyst@allworth.com'],
      groups: [
        { id: 'analysts', name: 'Analysts' },
        { id: 'all-users', name: 'All Users' },
      ],
    };
  },
  async getShares(resourceId) {
    return _demoShares.filter((s) => s.resource_id === resourceId);
  },
  async addShare(resourceId, principalType, principalId) {
    if (
      !_demoShares.some(
        (s) =>
          s.resource_id === resourceId &&
          s.principal_type === principalType &&
          s.principal_id === principalId
      )
    ) {
      _demoShares.push({
        resource_id: resourceId,
        principal_type: principalType,
        principal_id: principalId,
        created_at: new Date().toISOString(),
        created_by: 'demo@allworth.com',
      });
    }
  },
  async removeShare(resourceId, principalType, principalId) {
    _demoShares = _demoShares.filter(
      (s) =>
        !(
          s.resource_id === resourceId &&
          s.principal_type === principalType &&
          s.principal_id === principalId
        )
    );
  },
  async getUploads() {
    return {
      can_manage: true,
      uploads: [
        {
          id: 'accounting-gl',
          label: 'Accounting GL File',
          format: 'csv',
          columns: [
            'GL', 'Description', 'Posted dt.', 'Doc dt.', 'Doc', 'Memo/Description',
            'Department name', 'Vendor name', 'Legal Entitiy name (or Legal Entity name)',
            'Location name', 'Project name', 'JNL', 'Debit', 'Credit', 'Balance',
          ],
        },
      ],
    };
  },
  async uploadFile(_targetId, file) {
    return { stored: `gl_data/gl_raw/demo_${file.name}`, filename: `demo_${file.name}` };
  },
};

export const fileExplorerApi = DEMO_MODE ? demoApi : realApi;
