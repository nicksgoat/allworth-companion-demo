// Admin console — manage user access and groups. Grant tools per user, create
// groups, and cascade a group's tool access to all its members. Page chrome
// (background, orbs, shell) reuses the .t2-* classes from Tamarac2.css; the
// admin-specific UI is scoped under .admin-console in Admin.css.

import { useCallback, useEffect, useMemo, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import './Tamarac2.css';
import './Admin.css';
import SideNav from './components/SideNav';
import {
  adminApi,
  type Tool,
  type AdminUser,
  type AdminGroup,
  type BackupInfo,
} from './services/admin';

// "View as user" session overlay — consumed by the global ImpersonationBar in
// main.tsx. Non-destructive: it never mutates persisted access grants.
const IMPERSONATION_KEY = 'allworth-impersonation';
const IMPERSONATION_EVENT = 'allworth-impersonation-change';
function applyImpersonation(
  email: string,
  tools: string[],
  shareTools: string[] = [],
  shareAll = false
) {
  try {
    sessionStorage.setItem(
      IMPERSONATION_KEY,
      JSON.stringify({ email, tools, shareTools, shareAll })
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

type Tab = 'users' | 'groups' | 'tools';

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

// Turn a snapshot file name (admin_state_YYYYMMDD.json) into a readable date.
function formatBackupName(name: string): string {
  const m = name.match(/(\d{4})(\d{2})(\d{2})/);
  if (!m) return name;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(d.getTime())) return name;
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

interface BackupRestoreModalProps {
  onClose: () => void;
  onRestored: (summary: { users: number; groups: number }) => void;
}

function BackupRestoreModal({ onClose, onRestored }: BackupRestoreModalProps) {
  const [backups, setBackups] = useState<BackupInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmName, setConfirmName] = useState<string | null>(null);

  useEffect(() => {
    adminApi
      .listBackups()
      .then(setBackups)
      .catch((e) => {
        setError(e instanceof Error ? e.message : String(e));
        setBackups([]);
      });
  }, []);

  const restore = async (name: string) => {
    setBusy(name);
    setError(null);
    try {
      const summary = await adminApi.restoreBackup(name);
      onRestored(summary);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(null);
      setConfirmName(null);
    }
  };

  return (
    <div className="admin-modal-overlay" onClick={onClose}>
      <div
        className="admin-modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="admin-modal-title">Restore the user list</h2>
        <p className="admin-modal-text">
          Pick a saved snapshot to restore the roster (users, groups and tool
          grants). This replaces the current list and becomes the shared roster.
        </p>
        {error && <div className="admin-error">{error}</div>}
        {backups === null ? (
          <div className="admin-loading">Loading backups…</div>
        ) : backups.length === 0 ? (
          <div className="admin-empty">No saved backups were found.</div>
        ) : (
          <div className="admin-backup-list">
            {backups.map((b) => (
              <div className="admin-backup-row" key={b.name}>
                <div className="admin-backup-meta">
                  <span className="admin-backup-name">{formatBackupName(b.name)}</span>
                  <span className="admin-backup-sub">{b.name}</span>
                </div>
                {confirmName === b.name ? (
                  <div className="admin-backup-confirm">
                    <button
                      className="admin-danger admin-danger-solid"
                      disabled={busy === b.name}
                      onClick={() => restore(b.name)}
                    >
                      {busy === b.name ? 'Restoring…' : 'Confirm restore'}
                    </button>
                    <button
                      className="admin-secondary"
                      disabled={busy === b.name}
                      onClick={() => setConfirmName(null)}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    className="admin-secondary"
                    disabled={!!busy}
                    onClick={() => setConfirmName(b.name)}
                  >
                    Restore
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="admin-modal-actions">
          <button className="admin-secondary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Admin() {
  const [tab, setTab] = useState<Tab>('users');
  const [tools, setTools] = useState<Tool[]>([]);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [groups, setGroups] = useState<AdminGroup[]>([]);
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
      const [t, u, g] = await Promise.all([
        adminApi.getTools(),
        adminApi.getUsers(),
        adminApi.getGroups(),
      ]);
      setTools(t);
      setUsers(u);
      setGroups(g);
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
    applyImpersonation(user.email, user.effective_tools, [...shareSet], shareAll);
    toast('ok', `Now viewing as ${user.email}. Use the Revert view button to return.`);
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
    <div className="t2-page has-sidenav">
      <SideNav />
      <div className="t2-bg" aria-hidden="true">
        <div className="t2-orb t2-orb-1" />
        <div className="t2-orb t2-orb-2" />
        <div className="t2-orb t2-orb-3" />
        <div className="t2-orb t2-orb-4" />
        <div className="t2-orb t2-orb-5" />
      </div>

      <div className="t2-shell admin-console">
        <header className="admin-hero">
          <div className="admin-hero-left">
            <div className="admin-kicker-row">
              <a className="admin-home" href="/">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                Back to hub
              </a>
              <span className="admin-kicker">Access control</span>
            </div>
            <div className="admin-title">
              <h1>Admin</h1>
            </div>
            <p className="admin-tagline">
              Grant tool access by email, build groups, and let group access cascade to
              every member.
            </p>
          </div>
          <div className="admin-hero-right">
            <div className="admin-tabs">
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
          </div>
        </header>

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
        ) : (
          <ToolsPanel
            tools={tools}
            users={users}
            groups={groups}
            onShareUser={shareToolWithUser}
            onShareGroup={shareToolWithGroup}
          />
        )}
      </div>

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
    </div>
  );
}

interface UserCardProps {
  user: AdminUser;
  tools: Tool[];
  toolName: Record<string, string>;
  onSetLevel: (user: AdminUser, toolId: string, level: ToolLevel) => void;
  onRemove: (email: string) => void;
  onViewAs: (user: AdminUser) => void;
}

function UserCard({ user, tools, toolName, onSetLevel, onRemove, onViewAs }: UserCardProps) {
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

interface BulkUploadModalProps {
  groups: AdminGroup[];
  onClose: () => void;
  onUpload: (emails: string[], groupIds: string[]) => void;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function BulkUploadModal({ groups, onClose, onUpload }: BulkUploadModalProps) {
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Split on commas, semicolons, or any whitespace (newlines included).
  const tokens = useMemo(
    () =>
      text
        .split(/[\s,;]+/)
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean),
    [text]
  );
  const valid = useMemo(() => [...new Set(tokens.filter((t) => EMAIL_RE.test(t)))], [tokens]);
  const invalid = useMemo(() => [...new Set(tokens.filter((t) => !EMAIL_RE.test(t)))], [tokens]);

  const toggleGroup = (gid: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(gid)) next.delete(gid);
      else next.add(gid);
      return next;
    });

  const submit = () => {
    if (valid.length === 0) return;
    onUpload(valid, [...selected]);
  };

  return (
    <div className="admin-modal-overlay" onClick={onClose}>
      <div
        className="admin-modal"
        role="dialog"
        aria-modal="true"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="admin-modal-title">Bulk upload users</h2>
        <p className="admin-modal-text">
          Paste a list of email addresses (separated by new lines, commas, or spaces). New
          addresses are created; existing ones are reused.
        </p>

        <textarea
          className="admin-bulk-textarea"
          placeholder={'jane@allworth.com\nsam@allworth.com\n…'}
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
        />

        <div className="admin-bulk-summary">
          <span className="admin-chip">{valid.length} valid</span>
          {invalid.length > 0 && (
            <span className="admin-chip admin-chip-warn">{invalid.length} invalid</span>
          )}
        </div>

        <div className="admin-section-label">Add to groups (optional)</div>
        {groups.length === 0 ? (
          <div className="admin-muted">No groups yet.</div>
        ) : (
          <div className="admin-bulk-groups">
            {groups.map((g) => (
              <label key={g.id} className={'admin-tool' + (selected.has(g.id) ? ' on' : '')}>
                <input
                  type="checkbox"
                  checked={selected.has(g.id)}
                  onChange={() => toggleGroup(g.id)}
                />
                <span>{g.name}</span>
                {g.all_tools && <span className="admin-alltools-badge">All tools</span>}
              </label>
            ))}
          </div>
        )}

        <div className="admin-modal-actions">
          <button className="admin-secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="admin-primary" onClick={submit} disabled={valid.length === 0}>
            Upload {valid.length > 0 ? `${valid.length} user(s)` : 'users'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Tools tab ─────────────────────────────────────────────────────────────────
// A tool-first view of access: tools are grouped into their category (the
// hierarchy), each category drills into its individual tools, and each tool can
// be shared with a user or group via search. Sharing reuses the same set-tools
// endpoints as the Users/Groups tabs, so grants stay consistent across all three.

const CATEGORY_META: { key: string; label: string; blurb: string }[] = [
  { key: 'live', label: 'Live tools', blurb: 'Shipped and in production today.' },
  { key: 'analytics', label: 'Analytics & reports', blurb: 'Reporting, visual analytics and exports.' },
  { key: 'utilities', label: 'Utilities', blurb: 'Internal apps and lookup tools.' },
];

const STATUS_LABEL: Record<string, string> = { live: 'Live', new: 'New', soon: 'Soon' };

interface ToolsPanelProps {
  tools: Tool[];
  users: AdminUser[];
  groups: AdminGroup[];
  onShareUser: (toolId: string, email: string, grant: boolean) => void;
  onShareGroup: (toolId: string, group: AdminGroup, grant: boolean) => void;
}

function ToolsPanel({ tools, users, groups, onShareUser, onShareGroup }: ToolsPanelProps) {
  // Group tools by category, honouring the fixed category order and appending
  // any unknown categories at the end so nothing is ever hidden.
  const categories = useMemo(() => {
    const byCat = new Map<string, Tool[]>();
    for (const t of tools) {
      if (!byCat.has(t.category)) byCat.set(t.category, []);
      byCat.get(t.category)!.push(t);
    }
    const ordered: { key: string; label: string; blurb: string; items: Tool[] }[] = [];
    for (const meta of CATEGORY_META) {
      const items = byCat.get(meta.key);
      if (items?.length) ordered.push({ ...meta, items });
    }
    for (const [key, items] of byCat) {
      if (!CATEGORY_META.some((m) => m.key === key)) {
        ordered.push({ key, label: key, blurb: '', items });
      }
    }
    return ordered;
  }, [tools]);

  if (tools.length === 0) {
    return (
      <section className="admin-panel">
        <div className="admin-empty">No tools registered.</div>
      </section>
    );
  }

  return (
    <section className="admin-panel">
      <p className="admin-tools-intro">
        Browse tools by section, drill into a tool, then share it with a user or
        group. Group shares cascade to every member.
      </p>
      <div className="admin-list">
        {categories.map((cat) => (
          <ToolCategoryCard
            key={cat.key}
            label={cat.label}
            blurb={cat.blurb}
            items={cat.items}
            users={users}
            groups={groups}
            onShareUser={onShareUser}
            onShareGroup={onShareGroup}
          />
        ))}
      </div>
    </section>
  );
}

interface ToolCategoryCardProps {
  label: string;
  blurb: string;
  items: Tool[];
  users: AdminUser[];
  groups: AdminGroup[];
  onShareUser: (toolId: string, email: string, grant: boolean) => void;
  onShareGroup: (toolId: string, group: AdminGroup, grant: boolean) => void;
}

function ToolCategoryCard({
  label,
  blurb,
  items,
  users,
  groups,
  onShareUser,
  onShareGroup,
}: ToolCategoryCardProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className={'admin-card' + (open ? ' open' : '')}>
      <div className="admin-card-head">
        <button type="button" className="admin-card-toggle" onClick={() => setOpen((o) => !o)}>
          <span className="admin-chevron" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
          </span>
          <span className="admin-card-titlewrap">
            <span className="admin-card-title">{label}</span>
            <span className="admin-card-count">
              {items.length} {items.length === 1 ? 'tool' : 'tools'}
            </span>
          </span>
        </button>
      </div>

      {open && (
        <div className="admin-card-body">
          {blurb && <div className="admin-card-sub">{blurb}</div>}
          <div className="admin-list admin-tool-sublist">
            {items.map((t) => (
              <ToolShareRow
                key={t.id}
                tool={t}
                users={users}
                groups={groups}
                onShareUser={onShareUser}
                onShareGroup={onShareGroup}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

interface ToolShareRowProps {
  tool: Tool;
  users: AdminUser[];
  groups: AdminGroup[];
  onShareUser: (toolId: string, email: string, grant: boolean) => void;
  onShareGroup: (toolId: string, group: AdminGroup, grant: boolean) => void;
}

function ToolShareRow({ tool, users, groups, onShareUser, onShareGroup }: ToolShareRowProps) {
  const [open, setOpen] = useState(false);

  const grantingGroups = useMemo(
    () => groups.filter((g) => g.all_tools || g.tools.includes(tool.id)),
    [groups, tool.id]
  );
  const directUsers = useMemo(
    () => users.filter((u) => u.direct_tools.includes(tool.id)),
    [users, tool.id]
  );
  const shareCount = grantingGroups.length + directUsers.length;

  return (
    <div className={'admin-card admin-tool-card' + (open ? ' open' : '')}>
      <div className="admin-card-head">
        <button type="button" className="admin-card-toggle" onClick={() => setOpen((o) => !o)}>
          <span className="admin-chevron" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg>
          </span>
          <span className="admin-card-titlewrap">
            <span className="admin-card-title">
              {tool.name}
              {STATUS_LABEL[tool.status] && (
                <span className={'admin-status-badge admin-status-' + tool.status}>
                  {STATUS_LABEL[tool.status]}
                </span>
              )}
            </span>
            <span className="admin-card-count">
              {shareCount === 0
                ? 'Not shared'
                : `Shared with ${shareCount} ${shareCount === 1 ? 'recipient' : 'recipients'}`}
            </span>
          </span>
        </button>
      </div>

      {open && (
        <div className="admin-card-body">
          <div className="admin-section-label">Share with a user or group</div>
          <ToolShareControl
            tool={tool}
            users={users}
            groups={groups}
            onShareUser={onShareUser}
            onShareGroup={onShareGroup}
          />

          <div className="admin-section-label">
            Groups <span className="admin-tab-count">{grantingGroups.length}</span>
          </div>
          {grantingGroups.length === 0 ? (
            <div className="admin-muted admin-members-empty">No groups have this tool.</div>
          ) : (
            <div className="admin-members">
              {grantingGroups.map((g) => (
                <span className="admin-member" key={g.id}>
                  {g.name}
                  {g.all_tools ? (
                    <span className="admin-alltools-badge">All tools</span>
                  ) : (
                    <button
                      type="button"
                      className="admin-member-x"
                      onClick={() => onShareGroup(tool.id, g, false)}
                      title={`Remove ${tool.name} from ${g.name}`}
                    >
                      ×
                    </button>
                  )}
                </span>
              ))}
            </div>
          )}

          <div className="admin-section-label">
            Users (direct) <span className="admin-tab-count">{directUsers.length}</span>
          </div>
          {directUsers.length === 0 ? (
            <div className="admin-muted admin-members-empty">
              No users have this tool granted directly.
            </div>
          ) : (
            <div className="admin-members">
              {directUsers.map((u) => (
                <span className="admin-member" key={u.email}>
                  {u.email}
                  <button
                    type="button"
                    className="admin-member-x"
                    onClick={() => onShareUser(tool.id, u.email, false)}
                    title={`Remove ${tool.name} from ${u.email}`}
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface ToolShareControlProps {
  tool: Tool;
  users: AdminUser[];
  groups: AdminGroup[];
  onShareUser: (toolId: string, email: string, grant: boolean) => void;
  onShareGroup: (toolId: string, group: AdminGroup, grant: boolean) => void;
}

function ToolShareControl({
  tool,
  users,
  groups,
  onShareUser,
  onShareGroup,
}: ToolShareControlProps) {
  const [query, setQuery] = useState('');
  const [focused, setFocused] = useState(false);
  const q = query.trim().toLowerCase();

  const groupMatches = useMemo(
    () =>
      groups
        .filter(
          (g) => !g.all_tools && !g.tools.includes(tool.id) && g.name.toLowerCase().includes(q)
        )
        .slice(0, 5),
    [groups, tool.id, q]
  );
  const userMatches = useMemo(
    () =>
      users.filter((u) => !u.direct_tools.includes(tool.id) && u.email.includes(q)).slice(0, 6),
    [users, tool.id, q]
  );

  const showMenu = focused && (groupMatches.length > 0 || userMatches.length > 0);

  const pickGroup = (g: AdminGroup) => {
    onShareGroup(tool.id, g, true);
    setQuery('');
    setFocused(false);
  };
  const pickUser = (email: string) => {
    onShareUser(tool.id, email, true);
    setQuery('');
    setFocused(false);
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLInputElement>) => {
    if (e.key !== 'Enter') return;
    if (groupMatches.length > 0) pickGroup(groupMatches[0]);
    else if (userMatches.length > 0) pickUser(userMatches[0].email);
  };

  return (
    <div className="admin-search">
      <input
        type="text"
        placeholder="Search users or groups to share with…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setTimeout(() => setFocused(false), 120)}
        onKeyDown={onKeyDown}
      />
      {showMenu && (
        <div className="admin-search-menu">
          {groupMatches.length > 0 && (
            <div className="admin-search-group">Groups</div>
          )}
          {groupMatches.map((g) => (
            <button
              type="button"
              key={g.id}
              className="admin-search-item"
              onMouseDown={() => pickGroup(g)}
            >
              <span>{g.name}</span>
              <span className="admin-search-kind">group</span>
            </button>
          ))}
          {userMatches.length > 0 && (
            <div className="admin-search-group">Users</div>
          )}
          {userMatches.map((u) => (
            <button
              type="button"
              key={u.email}
              className="admin-search-item"
              onMouseDown={() => pickUser(u.email)}
            >
              <span>{u.email}</span>
              <span className="admin-search-kind">user</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
