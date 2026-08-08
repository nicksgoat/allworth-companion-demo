// src/services/admin.ts
// Fetch helper for the /admin console. Uses the shared /api base and attaches
// X-User-Email (resolved via MSAL) for server-side audit attribution.
//
// In local-preview DEMO_MODE (npm run dev:demo) there is no backend, so every
// call is served from an in-browser localStorage store with the SAME access
// model as the server (group grants cascade to members). This lets the page be
// fully explored offline.

import { resolveUserEmail } from './auth';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api';
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export interface Tool {
  id: string;
  name: string;
  category: string;
  status: string;
}

export interface AdminUser {
  email: string;
  direct_tools: string[];
  direct_share_tools: string[]; // subset of direct_tools this user may re-share
  inherited_tools: Record<string, string[]>; // tool_id -> [group names]
  effective_tools: string[];
  groups: { id: string; name: string }[];
  created_at?: string;
  created_by?: string;
}

export interface AdminGroup {
  id: string;
  name: string;
  description: string;
  tools: string[];
  share_tools: string[]; // subset of tools that cascade SHARE access to members
  all_tools: boolean;
  all_members: boolean; // true = every user is a member (e.g. "All Users")
  members: string[];
  created_at?: string;
  created_by?: string;
}

export interface Me {
  email: string;
  effective_tools: string[];
  share_tools: string[]; // tools this user may share with others
  can_share_all: boolean;
  all_access: boolean;
  known: boolean;
  enforced?: boolean;
}

/** A user who currently has access to a tool, as seen by a sharer. */
export interface ShareRecipient {
  email: string;
  direct: boolean;
  inherited_from: string[];
  shared_by?: string | null;
  shared_at?: string | null;
}

export interface ShareInfo {
  tool: string;
  recipients: ShareRecipient[];
  roster: string[]; // every known user email, for the share picker
}

/** A roster snapshot available to restore from. */
export interface BackupInfo {
  name: string;
  size?: number | null;
  last_modified?: string | null;
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

// ── real API ─────────────────────────────────────────────────────────────────

const realApi = {
  async getTools(): Promise<Tool[]> {
    const res = await fetch(`${API_BASE_URL}/admin/tools`);
    return (await parseJson<{ tools: Tool[] }>(res)).tools;
  },
  async getMe(): Promise<Me> {
    const res = await fetch(`${API_BASE_URL}/admin/me`, { headers: { ...(await userHeaders()) } });
    return await parseJson<Me>(res);
  },
  async getUsers(): Promise<AdminUser[]> {
    const res = await fetch(`${API_BASE_URL}/admin/users`);
    return (await parseJson<{ users: AdminUser[] }>(res)).users;
  },
  async addUser(email: string): Promise<AdminUser> {
    const res = await fetch(`${API_BASE_URL}/admin/users`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ email }),
    });
    return (await parseJson<{ user: AdminUser }>(res)).user;
  },
  async removeUser(email: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/admin/users/${encodeURIComponent(email)}`, {
      method: 'DELETE',
      headers: { ...(await userHeaders()) },
    });
    await parseJson<{ ok: boolean }>(res);
  },
  async setUserTools(email: string, tools: string[], shareTools: string[] = []): Promise<AdminUser> {
    const res = await fetch(`${API_BASE_URL}/admin/users/${encodeURIComponent(email)}/tools`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ tools, share_tools: shareTools }),
    });
    return (await parseJson<{ user: AdminUser }>(res)).user;
  },
  async getGroups(): Promise<AdminGroup[]> {
    const res = await fetch(`${API_BASE_URL}/admin/groups`);
    return (await parseJson<{ groups: AdminGroup[] }>(res)).groups;
  },
  async addGroup(name: string, description: string): Promise<AdminGroup> {
    const res = await fetch(`${API_BASE_URL}/admin/groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ name, description }),
    });
    return (await parseJson<{ group: AdminGroup }>(res)).group;
  },
  async removeGroup(gid: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/admin/groups/${encodeURIComponent(gid)}`, {
      method: 'DELETE',
      headers: { ...(await userHeaders()) },
    });
    await parseJson<{ ok: boolean }>(res);
  },
  async setGroupTools(gid: string, tools: string[], shareTools: string[] = []): Promise<AdminGroup> {
    const res = await fetch(`${API_BASE_URL}/admin/groups/${encodeURIComponent(gid)}/tools`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ tools, share_tools: shareTools }),
    });
    return (await parseJson<{ group: AdminGroup }>(res)).group;
  },
  async setGroupAllTools(gid: string, allTools: boolean): Promise<AdminGroup> {
    const res = await fetch(`${API_BASE_URL}/admin/groups/${encodeURIComponent(gid)}/all-tools`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ all_tools: allTools }),
    });
    return (await parseJson<{ group: AdminGroup }>(res)).group;
  },
  async setGroupMembers(gid: string, members: string[]): Promise<AdminGroup> {
    const res = await fetch(`${API_BASE_URL}/admin/groups/${encodeURIComponent(gid)}/members`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ members }),
    });
    return (await parseJson<{ group: AdminGroup }>(res)).group;
  },
  async getShareRecipients(tool: string): Promise<ShareInfo> {
    const res = await fetch(
      `${API_BASE_URL}/admin/share/${encodeURIComponent(tool)}/recipients`,
      { headers: { ...(await userHeaders()) } }
    );
    return await parseJson<ShareInfo>(res);
  },
  async shareTool(tool: string, email: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/admin/share`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ tool, email }),
    });
    await parseJson<{ ok: boolean }>(res);
  },
  async revokeShare(tool: string, email: string): Promise<void> {
    const res = await fetch(`${API_BASE_URL}/admin/share/revoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ tool, email }),
    });
    await parseJson<{ ok: boolean }>(res);
  },
  async listBackups(): Promise<BackupInfo[]> {
    const res = await fetch(`${API_BASE_URL}/admin/backups`, { headers: { ...(await userHeaders()) } });
    return (await parseJson<{ backups: BackupInfo[] }>(res)).backups;
  },
  async restoreBackup(name: string): Promise<{ users: number; groups: number }> {
    const res = await fetch(`${API_BASE_URL}/admin/backups/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(await userHeaders()) },
      body: JSON.stringify({ name }),
    });
    return await parseJson<{ users: number; groups: number }>(res);
  },
};

// ── demo store (localStorage) ────────────────────────────────────────────────

const DEMO_TOOLS: Tool[] = [
  { id: 'performance', name: 'Performance by Channel', category: 'live', status: 'live' },
  { id: 'jarvis', name: 'Jarvis Encyclopedia', category: 'live', status: 'live' },
  { id: 'nfbc', name: 'NFBC Adjustments', category: 'live', status: 'new' },
  { id: 'fee_calculator', name: 'Fee Calculator', category: 'live', status: 'live' },
  { id: 'file_explorer', name: 'File Explorer', category: 'live', status: 'new' },
  { id: 'admin', name: 'Admin', category: 'live', status: 'new' },
  { id: 'pipeline_logging', name: 'Pipeline Logging', category: 'analytics', status: 'live' },
  { id: 'data_catalog', name: 'Data Catalog', category: 'analytics', status: 'new' },
  { id: 'sfp2', name: 'Salesforce Column Updater', category: 'utilities', status: 'live' },
  { id: 'repcodes', name: 'Rep Codes', category: 'utilities', status: 'live' },
  { id: 'heatmaps', name: 'Heatmaps', category: 'analytics', status: 'soon' },
  { id: 'reconciliations', name: 'Reconciliations', category: 'analytics', status: 'soon' },
];

interface DemoState {
  users: Record<string, { email: string; tools: string[]; share_tools?: string[]; created_at: string }>;
  groups: Record<string, DemoGroup>;
  shares?: { tool: string; email: string; by: string; at: string }[];
}
interface DemoGroup {
  id: string;
  name: string;
  description: string;
  tools: string[];
  share_tools?: string[];
  all_tools: boolean;
  all_members?: boolean;
  members: string[];
  created_at: string;
}

const DEMO_KEY = 'allworth-admin-demo';

function loadDemo(): DemoState {
  try {
    const raw = localStorage.getItem(DEMO_KEY);
    if (raw) return JSON.parse(raw) as DemoState;
  } catch {
    /* ignore */
  }
  const seed: DemoState = {
    users: {
      'jane.advisor@allworth.com': {
        email: 'jane.advisor@allworth.com',
        tools: ['performance', 'repcodes'],
        share_tools: ['repcodes'],
        created_at: new Date().toISOString(),
      },
      'sam.analyst@allworth.com': {
        email: 'sam.analyst@allworth.com',
        tools: [],
        created_at: new Date().toISOString(),
      },
    },
    shares: [],
    groups: {
      analysts: {
        id: 'analysts',
        name: 'Analysts',
        description: 'Data & reporting analysts',
        tools: ['performance', 'pipeline_logging'],
        all_tools: false,
        members: ['sam.analyst@allworth.com'],
        created_at: new Date().toISOString(),
      },
      admin: {
        id: 'admin',
        name: 'Admin',
        description: 'Full access to every tool, including new ones',
        tools: [],
        all_tools: true,
        members: [],
        created_at: new Date().toISOString(),
      },
      'all-users': {
        id: 'all-users',
        name: 'All Users',
        description: 'Every user. Grant tools here to share them with everyone.',
        tools: [],
        all_tools: false,
        all_members: true,
        members: [],
        created_at: new Date().toISOString(),
      },
    },
  };
  saveDemo(seed);
  return seed;
}

function saveDemo(state: DemoState): void {
  try {
    localStorage.setItem(DEMO_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

const norm = (e: string) => (e || '').trim().toLowerCase();
const slugify = (v: string) =>
  v.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'group';

function groupsFor(email: string, state: DemoState): DemoGroup[] {
  return Object.values(state.groups).filter(
    (g) => g.all_members || g.members.map(norm).includes(norm(email))
  );
}

function userView(email: string, state: DemoState): AdminUser {
  const u = state.users[norm(email)];
  const direct = [...new Set(u?.tools ?? [])].sort();
  const directShare = [...new Set(u?.share_tools ?? [])].filter((t) => direct.includes(t)).sort();
  const groups = groupsFor(email, state);
  const allToolIds = DEMO_TOOLS.map((t) => t.id);
  const inherited: Record<string, string[]> = {};
  for (const g of groups) {
    const granted = g.all_tools ? allToolIds : g.tools;
    for (const t of granted) (inherited[t] ??= []).push(g.name);
  }
  const effective = [...new Set([...direct, ...Object.keys(inherited)])].sort();
  return {
    email: norm(email),
    direct_tools: direct,
    direct_share_tools: directShare,
    inherited_tools: inherited,
    effective_tools: effective,
    groups: groups.map((g) => ({ id: g.id, name: g.name })),
    created_at: u?.created_at,
  };
}

function groupView(g: DemoGroup, state: DemoState): AdminGroup {
  const members = g.all_members
    ? Object.keys(state.users).map(norm)
    : g.members.map(norm);
  const tools = [...new Set(g.tools)].sort();
  return {
    id: g.id,
    name: g.name,
    description: g.description,
    tools,
    share_tools: [...new Set(g.share_tools ?? [])].filter((t) => tools.includes(t)).sort(),
    all_tools: !!g.all_tools,
    all_members: !!g.all_members,
    members: [...new Set(members)].sort(),
    created_at: g.created_at,
  };
}

const demoApi = {
  async getTools() {
    return DEMO_TOOLS;
  },
  async getMe(): Promise<Me> {
    // The local developer previewing demo mode is treated as an all-access
    // admin, so non-impersonated browsing is never gated offline.
    return {
      email: 'demo@allworth.com',
      effective_tools: DEMO_TOOLS.map((t) => t.id),
      share_tools: DEMO_TOOLS.map((t) => t.id),
      can_share_all: true,
      all_access: true,
      known: true,
    };
  },
  async getUsers() {
    const s = loadDemo();
    return Object.keys(s.users)
      .map((e) => userView(e, s))
      .sort((a, b) => a.email.localeCompare(b.email));
  },
  async addUser(email: string) {
    const s = loadDemo();
    const e = norm(email);
    if (!e || !e.includes('@')) throw new Error('A valid email address is required');
    if (s.users[e]) throw new Error(`User ${e} already exists`);
    s.users[e] = { email: e, tools: [], created_at: new Date().toISOString() };
    saveDemo(s);
    return userView(e, s);
  },
  async removeUser(email: string) {
    const s = loadDemo();
    const e = norm(email);
    delete s.users[e];
    for (const g of Object.values(s.groups)) g.members = g.members.filter((m) => norm(m) !== e);
    saveDemo(s);
  },
  async setUserTools(email: string, tools: string[], shareTools: string[] = []) {
    const s = loadDemo();
    const e = norm(email);
    const valid = new Set(DEMO_TOOLS.map((t) => t.id));
    if (!s.users[e]) throw new Error(`Unknown user ${e}`);
    const cleaned = [...new Set(tools.filter((t) => valid.has(t)))].sort();
    s.users[e].tools = cleaned;
    s.users[e].share_tools = [...new Set(shareTools.filter((t) => cleaned.includes(t)))].sort();
    saveDemo(s);
    return userView(e, s);
  },
  async getGroups() {
    const s = loadDemo();
    return Object.values(s.groups)
      .map((g) => groupView(g, s))
      .sort((a, b) => a.name.localeCompare(b.name));
  },
  async addGroup(name: string, description: string) {
    const s = loadDemo();
    const n = name.trim();
    if (!n) throw new Error('A group name is required');
    const id = slugify(n);
    if (s.groups[id]) throw new Error(`A group named '${n}' already exists`);
    s.groups[id] = {
      id,
      name: n,
      description: description.trim(),
      tools: [],
      all_tools: false,
      members: [],
      created_at: new Date().toISOString(),
    };
    saveDemo(s);
    return groupView(s.groups[id], s);
  },
  async removeGroup(gid: string) {
    const s = loadDemo();
    if (gid === 'admin' || gid === 'all-users')
      throw new Error("This group is built-in and can't be deleted");
    delete s.groups[gid];
    saveDemo(s);
  },
  async setGroupTools(gid: string, tools: string[], shareTools: string[] = []) {
    const s = loadDemo();
    const valid = new Set(DEMO_TOOLS.map((t) => t.id));
    if (!s.groups[gid]) throw new Error(`Unknown group ${gid}`);
    const cleaned = [...new Set(tools.filter((t) => valid.has(t)))].sort();
    s.groups[gid].tools = cleaned;
    s.groups[gid].share_tools = [...new Set(shareTools.filter((t) => cleaned.includes(t)))].sort();
    saveDemo(s);
    return groupView(s.groups[gid], s);
  },
  async setGroupAllTools(gid: string, allTools: boolean) {
    const s = loadDemo();
    if (!s.groups[gid]) throw new Error(`Unknown group ${gid}`);
    s.groups[gid].all_tools = allTools;
    saveDemo(s);
    return groupView(s.groups[gid], s);
  },
  async setGroupMembers(gid: string, members: string[]) {
    const s = loadDemo();
    if (!s.groups[gid]) throw new Error(`Unknown group ${gid}`);
    if (s.groups[gid].all_members)
      throw new Error('This group includes every user automatically');
    const cleaned = [...new Set(members.map(norm).filter(Boolean))].sort();
    for (const e of cleaned) {
      s.users[e] ??= { email: e, tools: [], created_at: new Date().toISOString() };
    }
    s.groups[gid].members = cleaned;
    saveDemo(s);
    return groupView(s.groups[gid], s);
  },
  async getShareRecipients(tool: string): Promise<ShareInfo> {
    const s = loadDemo();
    const ledger = s.shares ?? [];
    const recipients: ShareRecipient[] = [];
    for (const email of Object.keys(s.users)) {
      const e = norm(email);
      const direct = (s.users[e]?.tools ?? []).includes(tool);
      const inheritedFrom = direct
        ? []
        : groupsFor(e, s)
            .filter((g) => g.all_tools || g.tools.includes(tool))
            .map((g) => g.name);
      if (!direct && inheritedFrom.length === 0) continue;
      const rec = ledger.find((x) => x.tool === tool && norm(x.email) === e);
      recipients.push({
        email: e,
        direct,
        inherited_from: inheritedFrom,
        shared_by: rec?.by ?? null,
        shared_at: rec?.at ?? null,
      });
    }
    recipients.sort((a, b) => a.email.localeCompare(b.email));
    return { tool, recipients, roster: Object.keys(s.users).map(norm).sort() };
  },
  async shareTool(tool: string, email: string): Promise<void> {
    const s = loadDemo();
    const e = norm(email);
    if (!e || !e.includes('@')) throw new Error('A valid recipient email address is required');
    if (!DEMO_TOOLS.some((t) => t.id === tool)) throw new Error(`Unknown tool ${tool}`);
    s.users[e] ??= { email: e, tools: [], created_at: new Date().toISOString() };
    if (!s.users[e].tools.includes(tool)) s.users[e].tools = [...s.users[e].tools, tool].sort();
    s.shares ??= [];
    if (!s.shares.some((x) => x.tool === tool && norm(x.email) === e))
      s.shares.push({ tool, email: e, by: 'demo@allworth.com', at: new Date().toISOString() });
    saveDemo(s);
  },
  async revokeShare(tool: string, email: string): Promise<void> {
    const s = loadDemo();
    const e = norm(email);
    if (s.users[e]) {
      s.users[e].tools = (s.users[e].tools ?? []).filter((t) => t !== tool);
      s.users[e].share_tools = (s.users[e].share_tools ?? []).filter((t) => t !== tool);
    }
    s.shares = (s.shares ?? []).filter((x) => !(x.tool === tool && norm(x.email) === e));
    saveDemo(s);
  },
  async listBackups(): Promise<BackupInfo[]> {
    // Synthetic daily snapshots so the restore UI can be explored offline.
    const today = new Date();
    return [0, 1, 2, 7].map((d) => {
      const dt = new Date(today);
      dt.setDate(today.getDate() - d);
      const ymd = dt.toISOString().slice(0, 10).replace(/-/g, '');
      return { name: `admin_state_${ymd}.json`, size: 2048, last_modified: dt.toISOString() };
    });
  },
  async restoreBackup(_name: string): Promise<{ users: number; groups: number }> {
    const s = loadDemo();
    return { users: Object.keys(s.users).length, groups: Object.keys(s.groups).length };
  },
};

export const adminApi = DEMO_MODE ? demoApi : realApi;
