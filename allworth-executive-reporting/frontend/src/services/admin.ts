// src/services/admin.ts
// Fetch helper for the /admin console. Uses the shared /api base and attaches
// X-User-Email (resolved via MSAL) for server-side audit attribution.
//
// In local-preview DEMO_MODE (npm run dev:demo) there is no backend, so every
// call is served from an in-browser localStorage store with the SAME access
// model as the server (group grants cascade to members). This lets the page be
// fully explored offline.

import { assignableTools } from '../config/toolManifest';
import { requestJson } from './http';
import { loadDemo, norm, saveDemo, slugify, type DemoGroup, type DemoState } from './adminDemoStore';

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
  assignment_id?: string | null;
  advisor_id_override?: string | null;
  created_at?: string;
  created_by?: string;
}

export type AssignmentType = 'advisor' | 'executive' | 'operations' | 'platform_admin' | 'general';

export interface Assignment {
  id: string;
  name: string;
  type: AssignmentType;
  home_tool_ids: string[];
  built_in?: boolean;
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
  assignment?: Assignment;
  home_tool_ids?: string[];
  advisor_id_override?: string | null;
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

// ── real API ─────────────────────────────────────────────────────────────────

const api = <T>(path: string, init?: RequestInit) => requestJson<T>(`${API_BASE_URL}${path}`, init);
const write = <T>(path: string, method: 'POST' | 'PUT' | 'DELETE', body?: unknown) => api<T>(path, {
  method,
  headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
});

const realApi = {
  async getTools(): Promise<Tool[]> {
    return (await api<{ tools: Tool[] }>('/admin/tools')).tools;
  },
  async getMe(): Promise<Me> {
    return api<Me>('/admin/me');
  },
  async getUsers(): Promise<AdminUser[]> {
    return (await api<{ users: AdminUser[] }>('/admin/users')).users;
  },
  async addUser(email: string): Promise<AdminUser> {
    return (await write<{ user: AdminUser }>('/admin/users', 'POST', { email })).user;
  },
  async removeUser(email: string): Promise<void> {
    await write(`/admin/users/${encodeURIComponent(email)}`, 'DELETE');
  },
  async setUserTools(email: string, tools: string[], shareTools: string[] = []): Promise<AdminUser> {
    return (await write<{ user: AdminUser }>(`/admin/users/${encodeURIComponent(email)}/tools`, 'PUT', { tools, share_tools: shareTools })).user;
  },
  async setUserAssignment(email: string, assignmentId: string | null, advisorIdOverride?: string | null): Promise<AdminUser> {
    return (await write<{ user: AdminUser }>(`/admin/users/${encodeURIComponent(email)}/assignment`, 'PUT', { assignment_id: assignmentId, advisor_id_override: advisorIdOverride ?? null })).user;
  },
  async getAssignments(): Promise<Assignment[]> {
    return (await api<{ assignments: Assignment[] }>('/admin/assignments')).assignments;
  },
  async addAssignment(name: string, type: AssignmentType, homeToolIds: string[]): Promise<Assignment> {
    return (await write<{ assignment: Assignment }>('/admin/assignments', 'POST', { name, type, home_tool_ids: homeToolIds })).assignment;
  },
  async updateAssignment(id: string, name: string, type: AssignmentType, homeToolIds: string[]): Promise<Assignment> {
    return (await write<{ assignment: Assignment }>(`/admin/assignments/${encodeURIComponent(id)}`, 'PUT', { name, type, home_tool_ids: homeToolIds })).assignment;
  },
  async removeAssignment(id: string): Promise<void> {
    await write(`/admin/assignments/${encodeURIComponent(id)}`, 'DELETE');
  },
  async getGroups(): Promise<AdminGroup[]> {
    return (await api<{ groups: AdminGroup[] }>('/admin/groups')).groups;
  },
  async addGroup(name: string, description: string): Promise<AdminGroup> {
    return (await write<{ group: AdminGroup }>('/admin/groups', 'POST', { name, description })).group;
  },
  async removeGroup(gid: string): Promise<void> {
    await write(`/admin/groups/${encodeURIComponent(gid)}`, 'DELETE');
  },
  async setGroupTools(gid: string, tools: string[], shareTools: string[] = []): Promise<AdminGroup> {
    return (await write<{ group: AdminGroup }>(`/admin/groups/${encodeURIComponent(gid)}/tools`, 'PUT', { tools, share_tools: shareTools })).group;
  },
  async setGroupAllTools(gid: string, allTools: boolean): Promise<AdminGroup> {
    return (await write<{ group: AdminGroup }>(`/admin/groups/${encodeURIComponent(gid)}/all-tools`, 'PUT', { all_tools: allTools })).group;
  },
  async setGroupMembers(gid: string, members: string[]): Promise<AdminGroup> {
    return (await write<{ group: AdminGroup }>(`/admin/groups/${encodeURIComponent(gid)}/members`, 'PUT', { members })).group;
  },
  async getShareRecipients(tool: string): Promise<ShareInfo> {
    return api<ShareInfo>(`/admin/share/${encodeURIComponent(tool)}/recipients`);
  },
  async shareTool(tool: string, email: string): Promise<void> {
    await write('/admin/share', 'POST', { tool, email });
  },
  async revokeShare(tool: string, email: string): Promise<void> {
    await write('/admin/share/revoke', 'POST', { tool, email });
  },
  async listBackups(): Promise<BackupInfo[]> {
    return (await api<{ backups: BackupInfo[] }>('/admin/backups')).backups;
  },
  async restoreBackup(name: string): Promise<{ users: number; groups: number }> {
    return write<{ users: number; groups: number }>('/admin/backups/restore', 'POST', { name });
  },
};

// ── demo store (localStorage) ────────────────────────────────────────────────

const DEMO_TOOLS: Tool[] = assignableTools.map(({ id, name, category, status }) => ({ id, name, category, status }));

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
    assignment_id: u?.assignment_id ?? null,
    advisor_id_override: u?.advisor_id_override ?? null,
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
      assignment: { id: 'general', name: 'General workspace', type: 'general', home_tool_ids: [], built_in: true },
      home_tool_ids: [],
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
  async setUserAssignment(email: string, assignmentId: string | null, advisorIdOverride?: string | null) {
    const s = loadDemo();
    const e = norm(email);
    if (!s.users[e]) throw new Error(`Unknown user ${e}`);
    if (assignmentId && assignmentId !== 'general' && !s.assignments?.[assignmentId]) throw new Error(`Unknown assignment ${assignmentId}`);
    s.users[e].assignment_id = assignmentId;
    s.users[e].advisor_id_override = advisorIdOverride ?? null;
    saveDemo(s);
    return userView(e, s);
  },
  async getAssignments(): Promise<Assignment[]> {
    const s = loadDemo();
    return [
      { id: 'general', name: 'General workspace', type: 'general', home_tool_ids: [], built_in: true },
      ...Object.values(s.assignments ?? {}),
    ];
  },
  async addAssignment(name: string, type: AssignmentType, homeToolIds: string[]): Promise<Assignment> {
    const s = loadDemo();
    const id = slugify(name);
    s.assignments ??= {};
    if (s.assignments[id]) throw new Error(`An assignment named '${name}' already exists`);
    const assignment = { id, name, type, home_tool_ids: homeToolIds };
    s.assignments[id] = assignment;
    saveDemo(s);
    return assignment;
  },
  async updateAssignment(id: string, name: string, type: AssignmentType, homeToolIds: string[]): Promise<Assignment> {
    const s = loadDemo();
    if (!s.assignments?.[id]) throw new Error(`Unknown assignment ${id}`);
    const assignment = { ...s.assignments[id], name, type, home_tool_ids: homeToolIds };
    s.assignments[id] = assignment;
    saveDemo(s);
    return assignment;
  },
  async removeAssignment(id: string): Promise<void> {
    const s = loadDemo();
    if (Object.values(s.users).some((user) => user.assignment_id === id)) throw new Error('Reassign its users before deleting this assignment');
    if (s.assignments) delete s.assignments[id];
    saveDemo(s);
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
