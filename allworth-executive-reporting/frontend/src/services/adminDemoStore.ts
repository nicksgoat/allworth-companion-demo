import { assignmentPresets } from '../config/toolManifest';
import type { Assignment } from './admin';

export interface DemoState {
  users: Record<string, { email: string; tools: string[]; share_tools?: string[]; created_at: string; assignment_id?: string | null; advisor_id_override?: string | null }>;
  groups: Record<string, DemoGroup>;
  assignments?: Record<string, Assignment>;
  shares?: { tool: string; email: string; by: string; at: string }[];
}

export interface DemoGroup {
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

const seedAssignments = (): Record<string, Assignment> => ({
  advisors: { id: 'advisors', name: 'Advisors', type: 'advisor', home_tool_ids: assignmentPresets.advisor },
  executives: { id: 'executives', name: 'Executive team', type: 'executive', home_tool_ids: assignmentPresets.executive },
});

export function loadDemo(): DemoState {
  try {
    const raw = localStorage.getItem(DEMO_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as DemoState;
      parsed.assignments ??= seedAssignments();
      return parsed;
    }
  } catch {
    // Corrupt browser preview data is replaced by the deterministic seed.
  }
  const createdAt = new Date().toISOString();
  const seed: DemoState = {
    users: {
      'jane.advisor@allworth.com': { email: 'jane.advisor@allworth.com', tools: ['performance', 'repcodes'], share_tools: ['repcodes'], created_at: createdAt },
      'sam.analyst@allworth.com': { email: 'sam.analyst@allworth.com', tools: [], created_at: createdAt },
    },
    shares: [],
    assignments: seedAssignments(),
    groups: {
      analysts: { id: 'analysts', name: 'Analysts', description: 'Data and reporting analysts', tools: ['performance', 'pipeline_logging'], all_tools: false, members: ['sam.analyst@allworth.com'], created_at: createdAt },
      admin: { id: 'admin', name: 'Admin', description: 'Full access to every tool, including new ones', tools: [], all_tools: true, members: [], created_at: createdAt },
      'all-users': { id: 'all-users', name: 'All Users', description: 'Every user. Grant tools here to share them with everyone.', tools: [], all_tools: false, all_members: true, members: [], created_at: createdAt },
    },
  };
  saveDemo(seed);
  return seed;
}

export function saveDemo(state: DemoState): void {
  try { localStorage.setItem(DEMO_KEY, JSON.stringify(state)); }
  catch { /* local preview remains usable in restricted browser contexts */ }
}

export const norm = (email: string) => (email || '').trim().toLowerCase();
export const slugify = (value: string) => value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'group';
