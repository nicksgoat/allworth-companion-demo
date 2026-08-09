import { useEffect, useMemo, useState } from 'react';
import { adminApi, type AdminGroup, type BackupInfo } from '../../services/admin';

function formatBackupName(name: string): string {
  const match = name.match(/(\d{4})(\d{2})(\d{2})/);
  if (!match) return name;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return Number.isNaN(date.getTime()) ? name : date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

export function BackupRestoreModal({ onClose, onRestored }: { onClose: () => void; onRestored: (summary: { users: number; groups: number }) => void }) {
  const [backups, setBackups] = useState<BackupInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmName, setConfirmName] = useState<string | null>(null);

  useEffect(() => { void adminApi.listBackups().then(setBackups).catch((reason) => { setError(reason instanceof Error ? reason.message : String(reason)); setBackups([]); }); }, []);
  const restore = async (name: string) => {
    setBusy(name); setError(null);
    try { onRestored(await adminApi.restoreBackup(name)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); setBusy(null); setConfirmName(null); }
  };

  return <div className="admin-modal-overlay" onClick={onClose}><div className="admin-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
    <h2 className="admin-modal-title">Restore the user list</h2>
    <p className="admin-modal-text">Pick a saved snapshot to restore the roster, groups, assignments, and tool grants. This becomes the shared roster.</p>
    {error && <div className="admin-error">{error}</div>}
    {backups === null ? <div className="admin-loading">Loading backups…</div> : backups.length === 0 ? <div className="admin-empty">No saved backups were found.</div> : <div className="admin-backup-list">{backups.map((backup) => <div className="admin-backup-row" key={backup.name}>
      <div className="admin-backup-meta"><span className="admin-backup-name">{formatBackupName(backup.name)}</span><span className="admin-backup-sub">{backup.name}</span></div>
      {confirmName === backup.name ? <div className="admin-backup-confirm"><button className="admin-danger admin-danger-solid" disabled={busy === backup.name} onClick={() => void restore(backup.name)}>{busy === backup.name ? 'Restoring…' : 'Confirm restore'}</button><button className="admin-secondary" disabled={busy === backup.name} onClick={() => setConfirmName(null)}>Cancel</button></div> : <button className="admin-secondary" disabled={Boolean(busy)} onClick={() => setConfirmName(backup.name)}>Restore</button>}
    </div>)}</div>}
    <div className="admin-modal-actions"><button className="admin-secondary" onClick={onClose}>Close</button></div>
  </div></div>;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function BulkUploadModal({ groups, onClose, onUpload }: { groups: AdminGroup[]; onClose: () => void; onUpload: (emails: string[], groupIds: string[]) => void }) {
  const [text, setText] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const tokens = useMemo(() => text.split(/[\s,;]+/).map((token) => token.trim().toLowerCase()).filter(Boolean), [text]);
  const valid = useMemo(() => [...new Set(tokens.filter((token) => EMAIL_RE.test(token)))], [tokens]);
  const invalid = useMemo(() => [...new Set(tokens.filter((token) => !EMAIL_RE.test(token)))], [tokens]);
  const toggleGroup = (groupId: string) => setSelected((current) => { const next = new Set(current); if (next.has(groupId)) next.delete(groupId); else next.add(groupId); return next; });

  return <div className="admin-modal-overlay" onClick={onClose}><div className="admin-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
    <h2 className="admin-modal-title">Bulk upload users</h2>
    <p className="admin-modal-text">Paste email addresses separated by new lines, commas, or spaces. Existing users are reused.</p>
    <textarea className="admin-bulk-textarea" placeholder={'jane@allworth.com\nsam@allworth.com\n…'} value={text} onChange={(event) => setText(event.target.value)} rows={8} />
    <div className="admin-bulk-summary"><span className="admin-chip">{valid.length} valid</span>{invalid.length > 0 && <span className="admin-chip admin-chip-warn">{invalid.length} invalid</span>}</div>
    <div className="admin-section-label">Add to groups (optional)</div>
    {groups.length === 0 ? <div className="admin-muted">No groups yet.</div> : <div className="admin-bulk-groups">{groups.map((group) => <label key={group.id} className={`admin-tool${selected.has(group.id) ? ' on' : ''}`}><input type="checkbox" checked={selected.has(group.id)} onChange={() => toggleGroup(group.id)} /><span>{group.name}</span>{group.all_tools && <span className="admin-alltools-badge">All tools</span>}</label>)}</div>}
    <div className="admin-modal-actions"><button className="admin-secondary" onClick={onClose}>Cancel</button><button className="admin-primary" onClick={() => valid.length && onUpload(valid, [...selected])} disabled={!valid.length}>Upload {valid.length ? `${valid.length} user(s)` : 'users'}</button></div>
  </div></div>;
}
