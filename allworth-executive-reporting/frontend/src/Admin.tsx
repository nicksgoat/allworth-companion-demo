// Admin console — manage user access and groups. Grant tools per user, create
// groups, and cascade a group's tool access to all its members. Page chrome
// (background, orbs, shell) reuses the .t2-* classes from Tamarac2.css; the
// admin-specific UI is scoped under .admin-console in Admin.css.

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import './Tamarac2.css';
import './Admin.css';
import { ToolPage } from './components/ToolPage';
import {
  adminApi,
  type Tool,
  type AdminUser,
  type AdminGroup,
  type Assignment,
} from './services/admin';
import { AssignmentsPanel } from './components/admin/AssignmentsPanel';
import { BackupRestoreModal, BulkUploadModal } from './components/admin/AdminModals';
import { ToolsPanel } from './components/admin/ToolsPanel';

// "View as user" session overlay — consumed by the global ImpersonationBar in
// main.tsx. Non-destructive: it never mutates persisted access grants.
const IMPERSONATION_KEY = 'allworth-impersonation';
const IMPERSONATION_EVENT = 'allworth-impersonation-change';
function applyImpersonation(
  email: string,
  tools: string[],
  shareTools: string[] = [],
  shareAll = false,
  assignment?: Assignment,
  advisorId?: string | null,
) {
  try {
    sessionStorage.setItem(
      IMPERSONATION_KEY,
      JSON.stringify({ email, tools, shareTools, shareAll, assignment,
        advisor: advisorId ? { advisor_id: advisorId, resolution: 'override' } : null })
    );
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent(IMPERSONATION_EVENT));
}

interface Toast {
  id: number;
  kind: 'ok' | 'err';
  msg: string;
}

type Tab = 'users' | 'groups' | 'assignments' | 'tools';

// Per-tool access level. "share" implies "view" plus the right to re-share the
// tool with other users straight from the tool page.
type ToolLevel = 'none' | 'view' | 'share';

const LEVEL_LABELS: Record<ToolLevel, string> = {
  none: 'No access',
  view: 'Can view',
  share: 'View + share',
};

type UserSort = 'email-asc' | 'email-desc' | 'created-desc' | 'created-asc';

function createdTs(u: AdminUser): number {
  const t = u.created_at ? Date.parse(u.created_at) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

function compareUsers(a: AdminUser, b: AdminUser, sort: UserSort): number {
  switch (sort) {
    case 'email-desc':
      return b.email.localeCompare(a.email);
    case 'created-desc':
      return createdTs(b) - createdTs(a) || a.email.localeCompare(b.email);
    case 'created-asc':
      return createdTs(a) - createdTs(b) || a.email.localeCompare(b.email);
    case 'email-asc':
    default:
      return a.email.localeCompare(b.email);
  }
}

function formatCreated(iso?: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

export default function Admin() {
  const [tab, setTab] = useState<Tab>('users');
  const [tools, setTools] = useState<Tool[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  const toast = useCallback((kind: Toast['kind'], msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 5000);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [t, u, g, a] = await Promise.all([
        adminApi.getTools(),
        adminApi.getUsers(),
        adminApi.getGroups(),
        adminApi.getAssignments(),
      ]);
      setTools(t);
      setUsers(u);
      setGroups(g);
      setAssignments(a);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toolName = useMemo(() => {
    const map: Record<string, string> = {};
    for (const t of tools) map[t.id] = t.name;
    return map;
  }, [tools]);

  // ── user actions ───────────────────────────────────────────────────────────
  const [userQuery, setUserQuery] = useState('');
  const [userSort, setUserSort] = useState<UserSort>('email-asc');
  const [confirmDeleteUser, setConfirmDeleteUser] = useState<string | null>(null);

  const addUser = async (email: string) => {
    const clean = email.trim().toLowerCase();
    if (!clean) return;
    try {
      await adminApi.addUser(clean);
      setUserQuery('');
      toast('ok', `Added ${clean}`);
      await load();
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const removeUser = async (email: string) => {
    try {
      await adminApi.removeUser(email);
      toast('ok', `Removed ${email}`);
      await load();
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const confirmRemoveUser = async () => {
    if (!confirmDeleteUser) return;
    const email = confirmDeleteUser;
    setConfirmDeleteUser(null);
    await removeUser(email);
  };

  const setUserToolLevel = async (user: AdminUser, toolId: string, level: ToolLevel) => {
    const view = new Set(user.direct_tools);
    const share = new Set(user.direct_share_tools);
    view.delete(toolId);
    share.delete(toolId);
    if (level === 'view' || level === 'share') view.add(toolId);
    if (level === 'share') share.add(toolId);
    try {
      const updated = await adminApi.setUserTools(user.email, [...view], [...share]);
      setUsers((us) => us.map((u) => (u.email === user.email ? updated : u)));
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const viewAsUser = (user: AdminUser) => {
    // Resolve the impersonated user's effective SHARE access (direct grants +
    // any group that cascades share/all-tools) so the "view as" overlay shows
    // the share affordance exactly as that user would experience it.
    const memberGroups = groups.filter(
      (g) => g.all_members || g.members.includes(user.email)
    );
    const shareAll = memberGroups.some((g) => g.all_tools);
    const shareSet = new Set(user.direct_share_tools);
    for (const g of memberGroups) for (const t of g.share_tools) shareSet.add(t);
    const assignment = assignments.find((item) => item.id === user.assignment_id)
      ?? assignments.find((item) => item.id === 'general');
    applyImpersonation(user.email, user.effective_tools, [...shareSet], shareAll,
      assignment, user.advisor_id_override);
    toast('ok', `Now viewing as ${user.email}. Use the Revert view button to return.`);
  };

  const setUserAssignment = async (user: AdminUser, assignmentId: string | null, advisorIdOverride?: string | null) => {
    try {
      const updated = await adminApi.setUserAssignment(user.email, assignmentId, advisorIdOverride);
      setUsers((current) => current.map((item) => item.email === user.email ? updated : item));
      toast('ok', `Updated ${user.email}'s workspace`);
    } catch (e) { toast('err', e instanceof Error ? e.message : String(e)); }
  };

  // ── group actions ──────────────────────────────────────────────────────────
  const [newGroupName, setNewGroupName] = useState('');
  const [newGroupDesc, setNewGroupDesc] = useState('');
  const [confirmDeleteGroup, setConfirmDeleteGroup] = useState<{ id: string; name: string } | null>(
    null
  );
  const [bulkOpen, setBulkOpen] = useState(false);
  const [restoreOpen, setRestoreOpen] = useState(false);

  const addGroup = async () => {
    const name = newGroupName.trim();
    if (!name) return;
    try {
      await adminApi.addGroup(name, newGroupDesc.trim());
      setNewGroupName('');
      setNewGroupDesc('');
      toast('ok', `Created group ${name}`);
      await load();
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const removeGroup = async (gid: string, name: string) => {
    try {
      await adminApi.removeGroup(gid);
      toast('ok', `Deleted group ${name}`);
      await load();
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const confirmRemoveGroup = async () => {
    if (!confirmDeleteGroup) return;
    const { id, name } = confirmDeleteGroup;
    setConfirmDeleteGroup(null);
    await removeGroup(id, name);
  };

  const bulkUpload = async (emails: string[], groupIds: string[]) => {
    let added = 0;
    for (const email of emails) {
      try {
        await adminApi.addUser(email);
        added += 1;
      } catch {
        /* already exists — still eligible for group assignment below */
      }
    }
    for (const gid of groupIds) {
      const g = groups.find((x) => x.id === gid);
      if (!g) continue;
      const union = [...new Set([...g.members, ...emails])];
      try {
        await adminApi.setGroupMembers(gid, union);
      } catch (e) {
        toast('err', e instanceof Error ? e.message : String(e));
      }
    }
    setBulkOpen(false);
    await load();
    const groupNote = groupIds.length ? ` and assigned to ${groupIds.length} group(s)` : '';
    toast('ok', `Uploaded ${emails.length} email(s): ${added} new${groupNote}.`);
  };

  const setGroupToolLevel = async (group: AdminGroup, toolId: string, level: ToolLevel) => {
    if (group.all_tools) return;
    const view = new Set(group.tools);
    const share = new Set(group.share_tools);
    view.delete(toolId);
    share.delete(toolId);
    if (level === 'view' || level === 'share') view.add(toolId);
    if (level === 'share') share.add(toolId);
    try {
      const updated = await adminApi.setGroupTools(group.id, [...view], [...share]);
      setGroups((gs) => gs.map((g) => (g.id === group.id ? updated : g)));
      // Membership-derived access changed → refresh users so inherited chips update.
      setUsers(await adminApi.getUsers());
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const toggleGroupAllTools = async (group: AdminGroup, value: boolean) => {
    try {
      const updated = await adminApi.setGroupAllTools(group.id, value);
      setGroups((gs) => gs.map((g) => (g.id === group.id ? updated : g)));
      setUsers(await adminApi.getUsers());
      toast('ok', value
        ? `${group.name} now has access to all tools (including new ones)`
        : `${group.name} no longer has all-tools access`);
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const addGroupMember = async (group: AdminGroup, email: string) => {
    const e = email.trim().toLowerCase();
    if (!e) return;
    if (group.members.includes(e)) return;
    try {
      const updated = await adminApi.setGroupMembers(group.id, [...group.members, e]);
      setGroups((gs) => gs.map((g) => (g.id === group.id ? updated : g)));
      setUsers(await adminApi.getUsers());
      toast('ok', `Added ${e} to ${group.name}`);
    } catch (err) {
      toast('err', err instanceof Error ? err.message : String(err));
    }
  };

  const removeGroupMember = async (group: AdminGroup, email: string) => {
    try {
      const updated = await adminApi.setGroupMembers(
        group.id,
        group.members.filter((m) => m !== email)
      );
      setGroups((gs) => gs.map((g) => (g.id === group.id ? updated : g)));
      setUsers(await adminApi.getUsers());
    } catch (err) {
      toast('err', err instanceof Error ? err.message : String(err));
    }
  };

  // ── tool sharing (Tools tab) ────────────────────────────────────────────────
  // Sharing a tool with a user grants it directly; sharing with a group adds it
  // to the group so access cascades to every member. Both reuse the same
  // set-tools endpoints as the Users/Groups tabs.
  const shareToolWithUser = async (toolId: string, email: string, grant: boolean) => {
    const user = users.find((u) => u.email === email);
    if (!user) return;
    const has = user.direct_tools.includes(toolId);
    if (grant === has) return;
    const next = grant
      ? [...user.direct_tools, toolId]
      : user.direct_tools.filter((t) => t !== toolId);
    const share = grant
      ? user.direct_share_tools
      : user.direct_share_tools.filter((t) => t !== toolId);
    try {
      const updated = await adminApi.setUserTools(email, next, share);
      setUsers((us) => us.map((u) => (u.email === email ? updated : u)));
      toast(
        'ok',
        grant
          ? `Shared ${toolName[toolId] ?? toolId} with ${email}`
          : `Removed ${toolName[toolId] ?? toolId} from ${email}`
      );
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  const shareToolWithGroup = async (toolId: string, group: AdminGroup, grant: boolean) => {
    if (group.all_tools) return; // already has every tool
    const has = group.tools.includes(toolId);
    if (grant === has) return;
    const next = grant
      ? [...group.tools, toolId]
      : group.tools.filter((t) => t !== toolId);
    const share = grant
      ? group.share_tools
      : group.share_tools.filter((t) => t !== toolId);
    try {
      const updated = await adminApi.setGroupTools(group.id, next, share);
      setGroups((gs) => gs.map((g) => (g.id === group.id ? updated : g)));
      setUsers(await adminApi.getUsers());
      toast(
        'ok',
        grant
          ? `Shared ${toolName[toolId] ?? toolId} with ${group.name}`
          : `Removed ${toolName[toolId] ?? toolId} from ${group.name}`
      );
    } catch (e) {
      toast('err', e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <ToolPage
      eyebrow="Access control"
      title="Admin"
      description="Grant tool access by email, build groups, and let group access cascade to every member."
      width="full"
      className="t2-page admin-console"
      actions={
            <div className="admin-tabs">
              <button
                type="button"
                className={tab === 'assignments' ? 'admin-tab active' : 'admin-tab'}
                onClick={() => setTab('assignments')}
              >
                Assignments <span className="admin-tab-count">{assignments.length}</span>
              </button>
              <button
                type="button"
                className={tab === 'users' ? 'admin-tab active' : 'admin-tab'}
                onClick={() => setTab('users')}
              >
                Users <span className="admin-tab-count">{users.length}</span>
              </button>
              <button
                type="button"
                className={tab === 'groups' ? 'admin-tab active' : 'admin-tab'}
                onClick={() => setTab('groups')}
              >
                Groups <span className="admin-tab-count">{groups.length}</span>
              </button>
              <button
                type="button"
                className={tab === 'tools' ? 'admin-tab active' : 'admin-tab'}
                onClick={() => setTab('tools')}
              >
                Tools <span className="admin-tab-count">{tools.length}</span>
              </button>
            </div>
      }
    >

        {error && <div className="admin-error">{error}</div>}

        {loading ? (
          <div className="admin-loading">Loading…</div>
        ) : tab === 'users' ? (
          <section className="admin-panel">
            {(() => {
              const q = userQuery.trim().toLowerCase();
              const base = q ? users.filter((u) => u.email.includes(q)) : users;
              const filtered = [...base].sort((a, b) => compareUsers(a, b, userSort));
              const isEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(q);
              const exists = users.some((u) => u.email === q);
              const canAdd = isEmail && !exists;
              return (
                <>
                  <div className="admin-addbar">
                    <input
                      type="text"
                      placeholder="Search users, or type a new email to add…"
                      value={userQuery}
                      onChange={(e) => setUserQuery(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && canAdd && addUser(q)}
                    />
                    <button
                      className="admin-primary"
                      onClick={() => addUser(q)}
                      disabled={!canAdd}
                      title={
                        canAdd
                          ? `Add ${q}`
                          : exists
                            ? 'That user already exists'
                            : 'Type a full email address to add a new user'
                      }
                    >
                      Add user
                    </button>
                    <button
                      className="admin-secondary admin-bulk-btn"
                      onClick={() => setBulkOpen(true)}
                      title="Add many users at once and assign them to groups"
                    >
                      Bulk upload
                    </button>
                    <button
                      className="admin-secondary"
                      onClick={() => setRestoreOpen(true)}
                      title="Restore the user list from a saved backup"
                    >
                      Restore backup
                    </button>
                  </div>

                  {users.length === 0 ? (
                    <div className="admin-empty">No users yet. Add one by email above.</div>
                  ) : filtered.length === 0 ? (
                    <div className="admin-empty">
                      No users match “{userQuery}”.
                      {canAdd && (
                        <>
                          {' '}
                          <button className="admin-linkbtn" onClick={() => addUser(q)}>
                            Add {q} as a new user
                          </button>
                        </>
                      )}
                    </div>
                  ) : (
                    <>
                      <div className="admin-listbar">
                        <div className="admin-result-count">
                          {filtered.length} of {users.length}{' '}
                          {users.length === 1 ? 'user' : 'users'}
                        </div>
                        <label className="admin-sort">
                          <span>Sort</span>
                          <select
                            value={userSort}
                            onChange={(e) => setUserSort(e.target.value as UserSort)}
                          >
                            <option value="email-asc">Email A–Z</option>
                            <option value="email-desc">Email Z–A</option>
                            <option value="created-desc">Newest first</option>
                            <option value="created-asc">Oldest first</option>
                          </select>
                        </label>
                      </div>
                      <div className="admin-list admin-list-single">
                        {filtered.map((u) => (
                          <UserCard
                            key={u.email}
                            user={u}
                            tools={tools}
                            toolName={toolName}
                            onSetLevel={setUserToolLevel}
                            onRemove={(email) => setConfirmDeleteUser(email)}
                            onViewAs={viewAsUser}
                            assignments={assignments}
                            onSetAssignment={setUserAssignment}
                          />
                        ))}
                      </div>
                    </>
                  )}
                </>
              );
            })()}
          </section>
        ) : tab === 'groups' ? (
          <section className="admin-panel">
            <div className="admin-addbar">
              <input
                type="text"
                placeholder="Group name (e.g. Analysts)"
                value={newGroupName}
                onChange={(e) => setNewGroupName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addGroup()}
              />
              <input
                type="text"
                placeholder="Description (optional)"
                value={newGroupDesc}
                onChange={(e) => setNewGroupDesc(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addGroup()}
              />
              <button className="admin-primary" onClick={addGroup}>
                Create group
              </button>
            </div>

            {groups.length === 0 ? (
              <div className="admin-empty">No groups yet. Create one above.</div>
            ) : (
              <div className="admin-list">
                {groups.map((g) => (
                  <GroupCard
                    key={g.id}
                    group={g}
                    tools={tools}
                    users={users}
                    onSetLevel={setGroupToolLevel}
                    onToggleAllTools={toggleGroupAllTools}
                    onAddMember={addGroupMember}
                    onRemoveMember={removeGroupMember}
                    onDelete={(gid, name) => setConfirmDeleteGroup({ id: gid, name })}
                  />
                ))}
              </div>
            )}
          </section>
        ) : tab === 'assignments' ? (
          <AssignmentsPanel
            assignments={assignments}
            tools={tools.filter((tool) => tool.status !== 'soon')}
            users={users}
            onChanged={load}
            onToast={toast}
          />
        ) : (
          <ToolsPanel
            tools={tools}
            users={users}
            groups={groups}
            onShareUser={shareToolWithUser}
            onShareGroup={shareToolWithGroup}
          />
        )}
      <div className="admin-toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`admin-toast ${t.kind}`}>
            {t.msg}
          </div>
        ))}
      </div>

      {confirmDeleteUser && (
        <div className="admin-modal-overlay" onClick={() => setConfirmDeleteUser(null)}>
          <div
            className="admin-modal admin-modal-sm"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="admin-modal-title">Remove user?</h2>
            <p className="admin-modal-text">
              Are you sure you want to remove <strong>{confirmDeleteUser}</strong>? They will lose
              all tool access and be removed from every group. This can’t be undone.
            </p>
            <div className="admin-modal-actions">
              <button className="admin-secondary" onClick={() => setConfirmDeleteUser(null)}>
                Cancel
              </button>
              <button className="admin-danger admin-danger-solid" onClick={confirmRemoveUser}>
                Remove user
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDeleteGroup && (
        <div className="admin-modal-overlay" onClick={() => setConfirmDeleteGroup(null)}>
          <div
            className="admin-modal admin-modal-sm"
            role="dialog"
            aria-modal="true"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="admin-modal-title">Delete group?</h2>
            <p className="admin-modal-text">
              Are you sure you want to delete <strong>{confirmDeleteGroup.name}</strong>? Members
              will lose any access this group granted them. This can’t be undone.
            </p>
            <div className="admin-modal-actions">
              <button className="admin-secondary" onClick={() => setConfirmDeleteGroup(null)}>
                Cancel
              </button>
              <button className="admin-danger admin-danger-solid" onClick={confirmRemoveGroup}>
                Delete group
              </button>
            </div>
          </div>
        </div>
      )}

      {bulkOpen && (
        <BulkUploadModal
          groups={groups}
          onClose={() => setBulkOpen(false)}
          onUpload={bulkUpload}
        />
      )}

      {restoreOpen && (
        <BackupRestoreModal
          onClose={() => setRestoreOpen(false)}
          onRestored={async (summary) => {
            setRestoreOpen(false);
            await load();
            toast('ok', `Restored ${summary.users} user(s) and ${summary.groups} group(s) from backup`);
          }}
        />
      )}
    </ToolPage>
  );
}

interface UserCardProps {
  user: AdminUser;
  tools: Tool[];
  toolName: Record<string, string>;
  onSetLevel: (user: AdminUser, toolId: string, level: ToolLevel) => void;
  onRemove: (email: string) => void;
  onViewAs: (user: AdminUser) => void;
  assignments: Assignment[];
  onSetAssignment: (user: AdminUser, assignmentId: string | null, advisorIdOverride?: string | null) => void;
}

function UserCard({ user, tools, toolName, onSetLevel, onRemove, onViewAs, assignments, onSetAssignment }: UserCardProps) {
  const [open, setOpen] = useState(false);
  const [advisorOverride, setAdvisorOverride] = useState(user.advisor_id_override ?? '');
  const assignment = assignments.find((item) => item.id === user.assignment_id)
    ?? assignments.find((item) => item.id === 'general');

  return (
    <div className={'admin-card' + (open ? ' open' : '')}>
      <div className="admin-card-head">
        <button
          type="button"
          className="admin-card-toggle"
          onClick={() => setOpen((o) => !o)}
        >
          <span className="admin-chevron" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
          </span>
          <span className="admin-card-titlewrap">
            <span className="admin-card-title">{user.email}</span>
            <span className="admin-card-count">Added {formatCreated(user.created_at)}</span>
          </span>
        </button>
        <div className="admin-head-actions">
          <button
            type="button"
            className="admin-secondary admin-viewas"
            onClick={() => onViewAs(user)}
            title="View the site as this user"
          >
            View as
          </button>
          <button
            type="button"
            className="admin-danger"
            onClick={() => onRemove(user.email)}
            title="Remove user"
          >
            Remove
          </button>
        </div>
      </div>

      {open && (
        <div className="admin-card-body">
          <div className="admin-user-assignment">
            <label><span>Primary assignment</span>
              <select value={assignment?.id ?? 'general'} onChange={(event) => onSetAssignment(user, event.target.value, advisorOverride)}>
                {assignments.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
            {assignment?.type === 'advisor' && <label><span>Advisor ID override <small>Optional</small></span>
              <div className="admin-assignment-override"><input value={advisorOverride} onChange={(event) => setAdvisorOverride(event.target.value)} placeholder="Matched by email" />
                <button className="admin-secondary" onClick={() => onSetAssignment(user, assignment.id, advisorOverride)}>Save</button></div>
            </label>}
          </div>
          {user.groups.length > 0 && (
            <div className="admin-meta">
              Member of:{' '}
              {user.groups.map((g) => (
                <span className="admin-pill" key={g.id}>
                  {g.name}
                </span>
              ))}
            </div>
          )}

          <div className="admin-section-label">Tool access</div>
          <div className="admin-tools admin-tools-levels">
            {tools.map((t) => {
              const direct = user.direct_tools.includes(t.id);
              const canShare = user.direct_share_tools.includes(t.id);
              const level: ToolLevel = direct ? (canShare ? 'share' : 'view') : 'none';
              const inheritedFrom = user.inherited_tools[t.id];
              const inherited = !!inheritedFrom?.length;
              return (
                <div
                  key={t.id}
                  className={
                    'admin-tool-level' + (direct ? ' on' : '') + (inherited ? ' inherited' : '')
                  }
                  title={inherited ? `Also inherited from: ${inheritedFrom!.join(', ')}` : t.name}
                >
                  <span className="admin-tool-level-name">
                    {t.name}
                    {inherited && !direct && <span className="admin-inherit-tag">group</span>}
                  </span>
                  <select
                    className="admin-level-select"
                    value={level}
                    onChange={(e) => onSetLevel(user, t.id, e.target.value as ToolLevel)}
                  >
                    <option value="none">{LEVEL_LABELS.none}</option>
                    <option value="view">{LEVEL_LABELS.view}</option>
                    <option value="share">{LEVEL_LABELS.share}</option>
                  </select>
                </div>
              );
            })}
          </div>

          <div className="admin-effective">
            Effective:{' '}
            {user.effective_tools.length === 0 ? (
              <span className="admin-muted">none</span>
            ) : (
              user.effective_tools.map((tid) => (
                <span className="admin-chip" key={tid}>
                  {toolName[tid] ?? tid}
                  {user.direct_share_tools.includes(tid) && (
                    <span className="admin-share-tag" title="Can share this tool">
                      share
                    </span>
                  )}
                </span>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface GroupCardProps {
  group: AdminGroup;
  tools: Tool[];
  users: AdminUser[];
  onSetLevel: (group: AdminGroup, toolId: string, level: ToolLevel) => void;
  onToggleAllTools: (group: AdminGroup, value: boolean) => void;
  onAddMember: (group: AdminGroup, email: string) => void;
  onRemoveMember: (group: AdminGroup, email: string) => void;
  onDelete: (gid: string, name: string) => void;
}

function GroupCard({
  group,
  tools,
  users,
  onSetLevel,
  onToggleAllTools,
  onAddMember,
  onRemoveMember,
  onDelete,
}: GroupCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className={'admin-card' + (open ? ' open' : '')}>
      <div className="admin-card-head">
        <button
          type="button"
          className="admin-card-toggle"
          onClick={() => setOpen((o) => !o)}
        >
          <span className="admin-chevron" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
          </span>
          <span className="admin-card-titlewrap">
            <span className="admin-card-title">
              {group.name}
              {group.all_members && <span className="admin-alltools-badge">Everyone</span>}
              {group.all_tools && <span className="admin-alltools-badge">All tools</span>}
            </span>
            <span className="admin-card-count">
              {group.members.length} {group.members.length === 1 ? 'member' : 'members'}
            </span>
          </span>
        </button>
        <div className="admin-head-actions">
          {!group.all_members && (
            <button
              type="button"
              className="admin-danger"
              onClick={() => onDelete(group.id, group.name)}
              title="Delete group"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {open && (
        <div className="admin-card-body">
          {group.description && <div className="admin-card-sub">{group.description}</div>}

          <label className="admin-alltools-toggle">
            <input
              type="checkbox"
              checked={group.all_tools}
              onChange={(e) => onToggleAllTools(group, e.target.checked)}
            />
            <span className="admin-alltools-text">
              <strong>All tools</strong>
              <span className="admin-alltools-hint">
                Grant access to every tool, including ones added in the future.
              </span>
            </span>
          </label>

          <div className="admin-section-label">Tool access (cascades to members)</div>
          <div className={'admin-tools admin-tools-levels' + (group.all_tools ? ' admin-tools-locked' : '')}>
            {tools.map((t) => {
              const view = group.all_tools || group.tools.includes(t.id);
              const canShare = group.share_tools.includes(t.id);
              const level: ToolLevel = view ? (canShare ? 'share' : 'view') : 'none';
              return (
                <div
                  key={t.id}
                  className={'admin-tool-level' + (view ? ' on' : '')}
                  title={group.all_tools ? 'Granted via "All tools"' : t.name}
                >
                  <span className="admin-tool-level-name">{t.name}</span>
                  <select
                    className="admin-level-select"
                    value={group.all_tools ? 'view' : level}
                    disabled={group.all_tools}
                    onChange={(e) => onSetLevel(group, t.id, e.target.value as ToolLevel)}
                  >
                    <option value="none">{LEVEL_LABELS.none}</option>
                    <option value="view">{LEVEL_LABELS.view}</option>
                    <option value="share">{LEVEL_LABELS.share}</option>
                  </select>
                </div>
              );
            })}
          </div>

          <div className="admin-section-label">
            Members <span className="admin-tab-count">{group.members.length}</span>
          </div>
          {group.all_members ? (
            <>
              <div className="admin-card-sub admin-members-empty">
                Everyone is a member of this group automatically — new users join
                as soon as they're added. Grant tools above to share them with
                the whole organisation.
              </div>
              {group.members.length > 0 && (
                <div className="admin-members">
                  {group.members.map((m) => (
                    <span className="admin-member" key={m}>
                      {m}
                    </span>
                  ))}
                </div>
              )}
            </>
          ) : (
            <>
              <MemberSearchAdd
                group={group}
                users={users}
                onAdd={(email) => onAddMember(group, email)}
              />
              {group.members.length === 0 ? (
                <div className="admin-muted admin-members-empty">No members.</div>
              ) : (
                <div className="admin-members">
                  {group.members.map((m) => (
                    <span className="admin-member" key={m}>
                      {m}
                      <button
                        type="button"
                        className="admin-member-x"
                        onClick={() => onRemoveMember(group, m)}
                        title="Remove from group"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface MemberSearchAddProps {
  group: AdminGroup;
  users: AdminUser[];
  onAdd: (email: string) => void;
}

function MemberSearchAdd({ group, users, onAdd }: MemberSearchAddProps) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);

  const memberSet = useMemo(() => new Set(group.members), [group.members]);
  const q = query.trim().toLowerCase();
  const matches = useMemo(
    () =>
      users
        .filter((u) => !memberSet.has(u.email) && u.email.includes(q))
        .slice(0, 6),
    [users, memberSet, q]
  );
  const canAddNew =
    q.includes('@') && !users.some((u) => u.email === q) && !memberSet.has(q);

  const pick = (email: string) => {
    onAdd(email);
    setQuery('');
    setFocused(false);
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    if (matches.length > 0) pick(matches[0].email);
    else if (canAddNew) pick(q);
  };

  const showMenu = focused && (matches.length > 0 || canAddNew);

  return (
    <div className="admin-search">
      <input
        type="text"
        placeholder="Search users by email…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 120)}
        onKeyDown={onKeyDown}
      />
      {showMenu && (
        <div className="admin-search-menu">
          {matches.map((u) => (
            <button
              type="button"
              key={u.email}
              className="admin-search-item"
              onMouseDown={() => pick(u.email)}
            >
              {u.email}
            </button>
          ))}
          {canAddNew && (
            <button
              type="button"
              className="admin-search-item admin-search-new"
              onMouseDown={() => pick(q)}
            >
              Add new user: <strong>{q}</strong>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
