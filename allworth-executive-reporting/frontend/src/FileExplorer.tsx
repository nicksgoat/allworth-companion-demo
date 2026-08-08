// src/FileExplorer.tsx
// File Explorer tool — Uploads / Downloads. Phase 1 ships Downloads: allow-listed
// users download data-lake Delta tables as CSV or tab-delimited text. Managers
// (Admin all-access) can inline-share a directory or table with users or groups.
import { useCallback, useEffect, useMemo, useState } from 'react';
import SideNav from './components/SideNav';
import {
  fileExplorerApi,
  type DownloadResource,
  type Principals,
  type ResourceTreeNode,
  type ShareEntry,
} from './services/fileExplorer';
import './FileExplorer.css';

type Tab = 'downloads' | 'uploads';

export default function FileExplorer() {
  const [tab, setTab] = useState<Tab>('downloads');

  return (
    <div className="file-explorer has-sidenav">
      <SideNav />
      <main className="fe-main">
        <header className="fe-header">
          <div>
            <h1>File Explorer</h1>
            <p className="fe-subtitle">
              Upload files to and download files from the data lake.
            </p>
          </div>
        </header>

        <div className="fe-tabs" role="tablist" aria-label="File Explorer sections">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'downloads'}
            className={tab === 'downloads' ? 'fe-tab active' : 'fe-tab'}
            onClick={() => setTab('downloads')}
          >
            Downloads
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'uploads'}
            className="fe-tab disabled"
            title="Uploads are coming soon"
            disabled
          >
            Uploads
            <span className="fe-soon">Soon</span>
          </button>
        </div>

        {tab === 'downloads' ? <Downloads /> : null}
      </main>
    </div>
  );
}

// ── Downloads ────────────────────────────────────────────────────────────────

function Downloads() {
  const [resources, setResources] = useState<DownloadResource[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [shareTarget, setShareTarget] = useState<{ id: string; label: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fileExplorerApi.getDownloads();
      setResources(data.resources);
      setCanManage(data.can_manage);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load downloads');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const grouped = useMemo(() => {
    const map = new Map<string, { label: string; items: DownloadResource[] }>();
    for (const r of resources) {
      const entry = map.get(r.root_id) ?? { label: r.root_label, items: [] };
      entry.items.push(r);
      map.set(r.root_id, entry);
    }
    return [...map.values()];
  }, [resources]);

  if (loading) return <p className="fe-muted">Loading…</p>;
  if (error) return <p className="fe-error">{error}</p>;

  return (
    <div className="fe-downloads">
      {canManage ? <SharingPanel /> : null}

      {grouped.length === 0 ? (
        <div className="fe-empty">
          <p>No files have been shared with you yet.</p>
          <p className="fe-muted">
            Ask an administrator to grant you access to a data-lake folder.
          </p>
        </div>
      ) : (
        grouped.map((group) => (
          <section key={group.label} className="fe-group">
            <h2 className="fe-group-title">{group.label}</h2>
            <ul className="fe-list">
              {group.items.map((r) => (
                <DownloadRow
                  key={r.id}
                  resource={r}
                  busy={busy === r.id}
                  canManage={canManage}
                  onDownload={async (format) => {
                    setBusy(r.id);
                    setError(null);
                    try {
                      await fileExplorerApi.downloadFile(r.id, format);
                    } catch (e) {
                      setError(e instanceof Error ? e.message : 'Download failed');
                    } finally {
                      setBusy(null);
                    }
                  }}
                  onShare={() => setShareTarget({ id: r.id, label: r.label })}
                />
              ))}
            </ul>
          </section>
        ))
      )}

      {shareTarget ? (
        <ShareDialog
          resourceId={shareTarget.id}
          resourceLabel={shareTarget.label}
          onClose={() => setShareTarget(null)}
        />
      ) : null}
    </div>
  );
}

function DownloadRow({
  resource,
  busy,
  canManage,
  onDownload,
  onShare,
}: {
  resource: DownloadResource;
  busy: boolean;
  canManage: boolean;
  onDownload: (format: string) => void;
  onShare: () => void;
}) {
  const [format, setFormat] = useState(resource.formats[0] ?? 'csv');
  const labelFor = (f: string) => (f === 'txt' ? 'Text (tab)' : f.toUpperCase());

  return (
    <li className="fe-row">
      <span className="fe-file-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
          <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
          <path d="M14 3v5h5" />
        </svg>
      </span>
      <span className="fe-row-name">{resource.label}</span>
      <div className="fe-row-actions">
        <label className="fe-format">
          <span className="fe-format-label">Format</span>
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            {resource.formats.map((f) => (
              <option key={f} value={f}>
                {labelFor(f)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="fe-btn primary"
          disabled={busy}
          onClick={() => onDownload(format)}
        >
          {busy ? (
            <>
              <span className="fe-spinner" aria-hidden="true" />
              Preparing…
            </>
          ) : (
            'Download'
          )}
        </button>
        {canManage ? (
          <button type="button" className="fe-btn ghost" onClick={onShare}>
            Share
          </button>
        ) : null}
      </div>
    </li>
  );
}

// ── Sharing (manager only) ───────────────────────────────────────────────────

function SharingPanel() {
  const [open, setOpen] = useState(false);
  const [tree, setTree] = useState<ResourceTreeNode[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shareTarget, setShareTarget] = useState<{ id: string; label: string } | null>(null);

  useEffect(() => {
    if (!open || loaded) return;
    void (async () => {
      try {
        setTree(await fileExplorerApi.getResources());
        setLoaded(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load resources');
      }
    })();
  }, [open, loaded]);

  return (
    <section className="fe-sharing">
      <button
        type="button"
        className="fe-sharing-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="fe-sharing-chevron">{open ? '▾' : '▸'}</span>
        Manage sharing
      </button>
      {open ? (
        <div className="fe-sharing-body">
          {error ? <p className="fe-error">{error}</p> : null}
          {!loaded && !error ? <p className="fe-muted">Loading…</p> : null}
          {tree.map((root) => (
            <div key={root.id} className="fe-tree-root">
              <div className="fe-tree-row">
                <span className="fe-tree-dir">📁 {root.label}</span>
                <button
                  type="button"
                  className="fe-btn ghost sm"
                  onClick={() => setShareTarget({ id: root.id, label: `${root.label} (folder)` })}
                >
                  Share folder
                </button>
              </div>
              {root.error ? <p className="fe-error">{root.error}</p> : null}
              <ul className="fe-tree-tables">
                {root.tables.map((t) => (
                  <li key={t.id} className="fe-tree-row">
                    <span className="fe-tree-file">📄 {t.label}</span>
                    <button
                      type="button"
                      className="fe-btn ghost sm"
                      onClick={() => setShareTarget({ id: t.id, label: t.label })}
                    >
                      Share
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : null}

      {shareTarget ? (
        <ShareDialog
          resourceId={shareTarget.id}
          resourceLabel={shareTarget.label}
          onClose={() => setShareTarget(null)}
        />
      ) : null}
    </section>
  );
}

function ShareDialog({
  resourceId,
  resourceLabel,
  onClose,
}: {
  resourceId: string;
  resourceLabel: string;
  onClose: () => void;
}) {
  const [shares, setShares] = useState<ShareEntry[]>([]);
  const [principals, setPrincipals] = useState<Principals>({ users: [], groups: [] });
  const [mode, setMode] = useState<'user' | 'group'>('user');
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([
        fileExplorerApi.getShares(resourceId),
        fileExplorerApi.getPrincipals(),
      ]);
      setShares(s);
      setPrincipals(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load sharing');
    } finally {
      setLoading(false);
    }
  }, [resourceId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const add = async () => {
    if (!value) return;
    setSaving(true);
    setError(null);
    try {
      await fileExplorerApi.addShare(resourceId, mode, value);
      setValue('');
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to add share');
    } finally {
      setSaving(false);
    }
  };

  const remove = async (s: ShareEntry) => {
    setError(null);
    try {
      await fileExplorerApi.removeShare(s.resource_id, s.principal_type, s.principal_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to remove share');
    }
  };

  const groupName = (id: string) =>
    principals.groups.find((g) => g.id === id)?.name ?? id;

  return (
    <div className="fe-modal-backdrop" onClick={onClose}>
      <div className="fe-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <header className="fe-modal-header">
          <h3>Share “{resourceLabel}”</h3>
          <button type="button" className="fe-modal-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {error ? <p className="fe-error">{error}</p> : null}

        <div className="fe-share-add">
          <div className="fe-seg">
            <button
              type="button"
              className={mode === 'user' ? 'active' : ''}
              onClick={() => {
                setMode('user');
                setValue('');
              }}
            >
              User
            </button>
            <button
              type="button"
              className={mode === 'group' ? 'active' : ''}
              onClick={() => {
                setMode('group');
                setValue('');
              }}
            >
              Group
            </button>
          </div>

          {mode === 'user' ? (
            <input
              className="fe-input"
              list="fe-user-options"
              placeholder="email@allworthfinancial.com"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          ) : (
            <select className="fe-input" value={value} onChange={(e) => setValue(e.target.value)}>
              <option value="">Select a group…</option>
              {principals.groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          )}
          <datalist id="fe-user-options">
            {principals.users.map((u) => (
              <option key={u} value={u} />
            ))}
          </datalist>

          <button type="button" className="fe-btn primary" disabled={saving || !value} onClick={add}>
            {saving ? 'Adding…' : 'Add'}
          </button>
        </div>

        <div className="fe-share-list">
          <h4>Shared with</h4>
          {loading ? (
            <p className="fe-muted">Loading…</p>
          ) : shares.length === 0 ? (
            <p className="fe-muted">Not shared with anyone yet.</p>
          ) : (
            <ul>
              {shares.map((s) => (
                <li key={`${s.principal_type}:${s.principal_id}`}>
                  <span className={`fe-pill ${s.principal_type}`}>
                    {s.principal_type === 'group' ? 'Group' : 'User'}
                  </span>
                  <span className="fe-principal">
                    {s.principal_type === 'group' ? groupName(s.principal_id) : s.principal_id}
                  </span>
                  <button type="button" className="fe-btn ghost sm" onClick={() => remove(s)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
