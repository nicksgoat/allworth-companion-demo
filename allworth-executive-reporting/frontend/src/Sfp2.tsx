// src/Sfp2.tsx
// Admin page: browse SFP2 bronze Delta tables, diff against live Salesforce
// describe(), and (Phase 3) add/remove columns. Mirrors the Tamarac2 layout.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import PipelineNav from './components/PipelineNav';
import SideNav from './components/SideNav';
import {
  addSfp2Column,
  cancelSfp2PendingDrop,
  dropSfp2Column,
  fetchSfp2Diff,
  fetchSfp2SchemaChanges,
  fetchSfp2SObjects,
  fetchSfp2Tables,
  previewSfp2Add,
  type DiffResponse,
  type PreviewResponse,
  type SchemaChangeRow,
  type SfField,
  type SfObjectSummary,
} from './services/sfp2';
import './Sfp2.css';

interface TableRow {
  name: string;
}

const Sfp2 = () => {
  const [tables, setTables] = useState<TableRow[]>([]);
  const [sobjects, setSObjects] = useState<SfObjectSummary[]>([]);
  const [tableFilter, setTableFilter] = useState('');
  const [sobjectFilter, setSObjectFilter] = useState('');
  const [selectedTable, setSelectedTable] = useState<string>('');
  const [selectedSObject, setSelectedSObject] = useState<string>('');
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [diffBucketFilter, setDiffBucketFilter] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [pendingMutation, setPendingMutation] = useState<string | null>(null);
  // Tracks which column was most recently copied so we can flash the button.
  const [copiedColumn, setCopiedColumn] = useState<string | null>(null);
  const copyResetTimer = useRef<number | null>(null);
  // Preview state for the add-column flow. When set, the matching row in the
  // "Only in Salesforce" bucket renders an inline preview + Confirm/Cancel.
  const [addPreview, setAddPreview] = useState<
    | {
        field: SfField;
        loading: boolean;
        result?: PreviewResponse;
        error?: string;
      }
    | null
  >(null);
  // Modal state for the drop-column flow.
  const [dropTarget, setDropTarget] = useState<
    | {
        column: string;
        delta_type?: string;
        referenced_in?: string[];
        typed: string;
        submitting: boolean;
        error?: string;
        remediation?: string;
      }
    | null
  >(null);
  const diffAbort = useRef<AbortController | null>(null);

  // Recent schema changes (audit log) for the selected table.
  const [changes, setChanges] = useState<SchemaChangeRow[]>([]);
  const [changesLoading, setChangesLoading] = useState(false);
  const [changesError, setChangesError] = useState<string | null>(null);
  const changesAbort = useRef<AbortController | null>(null);

  const loadChanges = useCallback(async (table: string) => {
    if (!table) {
      setChanges([]);
      return;
    }
    changesAbort.current?.abort();
    const ctrl = new AbortController();
    changesAbort.current = ctrl;
    setChangesLoading(true);
    setChangesError(null);
    try {
      const res = await fetchSfp2SchemaChanges(table, 100, ctrl.signal);
      setChanges(res.rows ?? []);
    } catch (e) {
      if ((e as Error).name === 'AbortError') return;
      setChangesError((e as Error).message);
    } finally {
      setChangesLoading(false);
    }
  }, []);

  const handleCancelPending = useCallback(
    async (column: string) => {
      if (!selectedTable) return;
      try {
        const res = await cancelSfp2PendingDrop(selectedTable, column);
        if (!res.success) {
          setChangesError(res.error || 'Cancel failed');
          return;
        }
        await loadChanges(selectedTable);
      } catch (e) {
        setChangesError((e as Error).message);
      }
    },
    [selectedTable, loadChanges]
  );

  // Load tables + sobjects on mount.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [t, s] = await Promise.all([fetchSfp2Tables(), fetchSfp2SObjects()]);
        if (cancelled) return;
        setTables(t.tables ?? []);
        setSObjects(s.sobjects ?? []);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Auto-suggest matching SObject when a table is selected.
  useEffect(() => {
    if (!selectedTable) return;
    const exact = sobjects.find((s) => s.name?.toLowerCase() === selectedTable.toLowerCase());
    if (exact) setSelectedSObject(exact.name);
    else setSelectedSObject(selectedTable);
  }, [selectedTable, sobjects]);

  const loadDiff = useCallback(async (table: string, sobject: string) => {
    if (!table || !sobject) return;
    diffAbort.current?.abort();
    const ctrl = new AbortController();
    diffAbort.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const d = await fetchSfp2Diff(table, sobject, ctrl.signal);
      setDiff(d);
    } catch (e) {
      if ((e as Error).name === 'AbortError') return;
      setError((e as Error).message);
      setDiff(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTable && selectedSObject) {
      void loadDiff(selectedTable, selectedSObject);
    }
  }, [selectedTable, selectedSObject, loadDiff]);

  useEffect(() => {
    void loadChanges(selectedTable);
  }, [selectedTable, loadChanges]);

  const filteredTables = useMemo(() => {
    const q = tableFilter.trim().toLowerCase();
    if (!q) return tables;
    return tables.filter((t) => t.name.toLowerCase().includes(q));
  }, [tables, tableFilter]);

  const filteredSObjects = useMemo(() => {
    const q = sobjectFilter.trim().toLowerCase();
    if (!q) return sobjects;
    return sobjects.filter(
      (s) =>
        s.name?.toLowerCase().includes(q) ||
        s.label?.toLowerCase().includes(q)
    );
  }, [sobjects, sobjectFilter]);

  const matchesBucketFilter = useCallback(
    (name?: string) => {
      const q = diffBucketFilter.trim().toLowerCase();
      if (!q) return true;
      return (name ?? '').toLowerCase().includes(q);
    },
    [diffBucketFilter]
  );

  /**
   * Map of lowercase column name -> 'pending' (drop queued) | 'add_pending'
   * (add queued) for the currently selected table. Built from the audit
   * `changes` list so the diff buckets can swap the Add / Remove buttons for
   * a "Pending overnight" pill the moment the user clicks confirm.
   */
  const pendingByColumn = useMemo(() => {
    const map = new Map<string, 'pending' | 'add_pending'>();
    for (const r of changes) {
      if (r.state === 'pending' || r.state === 'add_pending') {
        const key = (r.column ?? '').toLowerCase();
        if (key && !map.has(key)) map.set(key, r.state);
      }
    }
    return map;
  }, [changes]);

  const handleCopy = useCallback(async (column: string) => {
    if (!column) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(column);
      } else {
        // Fallback for non-secure contexts: hidden textarea + execCommand.
        const ta = document.createElement('textarea');
        ta.value = column;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      setCopiedColumn(column);
      if (copyResetTimer.current) window.clearTimeout(copyResetTimer.current);
      copyResetTimer.current = window.setTimeout(() => setCopiedColumn(null), 1200);
    } catch {
      /* copy failures are non-fatal */
    }
  }, []);

  const handleAddPreview = useCallback(
    async (field: SfField) => {
      if (!selectedTable || !field.name) return;
      setAddPreview({ field, loading: true });
      try {
        const result = await previewSfp2Add(selectedTable, field.name, field);
        setAddPreview({
          field,
          loading: false,
          result,
          error: result.success ? undefined : result.error || 'Preview failed',
        });
      } catch (e) {
        setAddPreview({ field, loading: false, error: (e as Error).message });
      }
    },
    [selectedTable]
  );

  const handleAddConfirm = useCallback(async () => {
    if (!selectedTable || !addPreview?.field?.name) return;
    const field = addPreview.field;
    const key = `add:${field.name}`;
    setPendingMutation(key);
    setError(null);
    try {
      const result = await addSfp2Column(selectedTable, field.name, field);
      if (!result.success) {
        setError(result.error || `Add failed (HTTP ${result.status ?? '?'}).`);
        return;
      }
      setAddPreview(null);
      await loadDiff(selectedTable, selectedSObject);
      void loadChanges(selectedTable);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPendingMutation(null);
    }
  }, [selectedTable, selectedSObject, addPreview, loadDiff, loadChanges]);

  const openDropModal = useCallback(
    (column: string, delta_type?: string, referenced_in?: string[]) => {
      setDropTarget({
        column,
        delta_type,
        referenced_in,
        typed: '',
        submitting: false,
      });
    },
    []
  );

  const handleDropConfirm = useCallback(async () => {
    if (!selectedTable || !dropTarget) return;
    if (dropTarget.typed !== dropTarget.column) return;
    setDropTarget((prev) => (prev ? { ...prev, submitting: true, error: undefined, remediation: undefined } : prev));
    try {
      const result = await dropSfp2Column(selectedTable, dropTarget.column);
      if (!result.success) {
        setDropTarget((prev) =>
          prev
            ? {
                ...prev,
                submitting: false,
                error: result.error || `Drop failed (HTTP ${result.status ?? '?'}).`,
                remediation: result.remediation,
              }
            : prev
        );
        return;
      }
      setDropTarget(null);
      await loadDiff(selectedTable, selectedSObject);
      void loadChanges(selectedTable);
    } catch (e) {
      setDropTarget((prev) =>
        prev ? { ...prev, submitting: false, error: (e as Error).message } : prev
      );
    }
  }, [selectedTable, selectedSObject, dropTarget, loadDiff, loadChanges]);

  return (
    <div className="sfp2-page has-sidenav">
      <SideNav />
      <div className="sfp2-shell">
        <header className="sfp2-hero">
          <div>
            <div className="sfp2-kicker">Pipeline Monitor · SFP2 Schema</div>
            <h1 className="sfp2-title">Salesforce ⇄ Bronze Delta schema</h1>
          </div>
          <PipelineNav />
        </header>

        {error && <div className="sfp2-banner error">{error}</div>}

        <div className="sfp2-grid">
          {/* LEFT: pickers */}
          <div>
            <div className="sfp2-card">
              <h3>Bronze Delta tables</h3>
              <input
                className="sfp2-input"
                type="search"
                placeholder="Filter tables…"
                value={tableFilter}
                onChange={(e) => setTableFilter(e.target.value)}
              />
              <div className="sfp2-list">
                {filteredTables.length === 0 && (
                  <div className="sfp2-empty">No tables loaded.</div>
                )}
                {filteredTables.map((t) => (
                  <div
                    key={t.name}
                    className={
                      'sfp2-list-item' + (selectedTable === t.name ? ' active' : '')
                    }
                    onClick={() => setSelectedTable(t.name)}
                  >
                    <span>{t.name}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="sfp2-card">
              <h3>Salesforce SObject</h3>
              <input
                className="sfp2-input"
                type="search"
                placeholder="Filter SObjects…"
                value={sobjectFilter}
                onChange={(e) => setSObjectFilter(e.target.value)}
              />
              <div className="sfp2-list">
                {filteredSObjects.length === 0 && (
                  <div className="sfp2-empty">No SObjects loaded.</div>
                )}
                {filteredSObjects.slice(0, 500).map((s) => (
                  <div
                    key={s.name}
                    className={
                      'sfp2-list-item' + (selectedSObject === s.name ? ' active' : '')
                    }
                    onClick={() => s.name && setSelectedSObject(s.name)}
                  >
                    <span>{s.name}</span>
                    {s.custom && <span className="sfp2-row-meta">custom</span>}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* RIGHT: diff */}
          <div>
            <div className="sfp2-card">
              <div className="sfp2-toolbar">
                <strong>{selectedTable || '— select a table —'}</strong>
                <span className="sfp2-row-meta">vs SObject</span>
                <strong>{selectedSObject || '—'}</strong>
                <button
                  className="sfp2-btn"
                  type="button"
                  onClick={() => selectedTable && loadDiff(selectedTable, selectedSObject)}
                  disabled={!selectedTable || !selectedSObject || loading}
                >
                  {loading ? 'Loading…' : 'Refresh'}
                </button>
                <input
                  className="sfp2-input sfp2-toolbar-search"
                  type="search"
                  placeholder="Filter columns in any bucket…"
                  value={diffBucketFilter}
                  onChange={(e) => setDiffBucketFilter(e.target.value)}
                />
              </div>

              {diff && (
                <div className="sfp2-counts">
                  <span className="sfp2-pill">Delta: {diff.counts.delta}</span>
                  <span className="sfp2-pill">SF: {diff.counts.sf}</span>
                  <span className="sfp2-pill">Both: {diff.counts.in_both}</span>
                  <span className="sfp2-pill">Only delta: {diff.counts.only_in_delta}</span>
                  <span className="sfp2-pill">Only SF: {diff.counts.only_in_sf}</span>
                </div>
              )}

              <div className="sfp2-buckets">
                {/* In both */}
                <div className="sfp2-bucket">
                  <div className="sfp2-bucket-header">
                    <span className="sfp2-bucket-title both">In both</span>
                    <span className="sfp2-bucket-count">
                      {diff?.in_both.filter((r) => matchesBucketFilter(r.name)).length ?? 0}
                    </span>
                  </div>
                  <div className="sfp2-bucket-rows">
                    {!diff && <div className="sfp2-empty">No diff loaded.</div>}
                    {diff?.in_both
                      .filter((r) => matchesBucketFilter(r.name))
                      .map((r) => {
                        const pendingState = pendingByColumn.get(r.name.toLowerCase());
                        return (
                        <div key={r.name} className="sfp2-row">
                          <span className="sfp2-row-name">
                            {r.name}
                            {r.referenced_in && r.referenced_in.length > 0 && (
                              <span
                                className="sfp2-ref-pill"
                                title={`Referenced in:\n${r.referenced_in.join('\n')}`}
                              >
                                📎 {r.referenced_in.length}
                              </span>
                            )}
                          </span>
                          <span className="sfp2-row-meta">
                            delta: {r.delta_type} · sf: {r.sf_type ?? '?'}
                            {r.custom ? ' · custom' : ''}
                          </span>
                          <div className="sfp2-row-actions">
                            <button
                              className="sfp2-btn sfp2-btn-copy"
                              type="button"
                              onClick={() => handleCopy(r.name)}
                              title={`Copy "${r.name}" to clipboard`}
                            >
                              {copiedColumn === r.name ? 'Copied!' : 'Copy'}
                            </button>
                            {pendingState === 'pending' ? (
                              <PendingPill
                                kind="drop"
                                onCancel={() => handleCancelPending(r.name)}
                              />
                            ) : (
                              <button
                                className="sfp2-btn danger"
                                type="button"
                                onClick={() => openDropModal(r.name, r.delta_type, r.referenced_in)}
                                disabled={pendingMutation === `drop:${r.name}`}
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        </div>
                        );
                      })}
                  </div>
                </div>

                {/* Only delta */}
                <div className="sfp2-bucket">
                  <div className="sfp2-bucket-header">
                    <span className="sfp2-bucket-title delta">Only in Delta</span>
                    <span className="sfp2-bucket-count">
                      {diff?.only_in_delta.filter((r) => matchesBucketFilter(r.name)).length ??
                        0}
                    </span>
                  </div>
                  <div className="sfp2-bucket-rows">
                    {!diff && <div className="sfp2-empty">No diff loaded.</div>}
                    {diff?.only_in_delta
                      .filter((r) => matchesBucketFilter(r.name))
                      .map((r) => {
                        const pendingState = pendingByColumn.get(r.name.toLowerCase());
                        return (
                        <div key={r.name} className="sfp2-row">
                          <span className="sfp2-row-name">
                            {r.name}
                            {r.referenced_in && r.referenced_in.length > 0 && (
                              <span
                                className="sfp2-ref-pill"
                                title={`Referenced in:\n${r.referenced_in.join('\n')}`}
                              >
                                📎 {r.referenced_in.length}
                              </span>
                            )}
                          </span>
                          <span className="sfp2-row-meta">delta: {r.delta_type}</span>
                          <div className="sfp2-row-actions">
                            <button
                              className="sfp2-btn sfp2-btn-copy"
                              type="button"
                              onClick={() => handleCopy(r.name)}
                              title={`Copy "${r.name}" to clipboard`}
                            >
                              {copiedColumn === r.name ? 'Copied!' : 'Copy'}
                            </button>
                            {pendingState === 'pending' ? (
                              <PendingPill
                                kind="drop"
                                onCancel={() => handleCancelPending(r.name)}
                              />
                            ) : (
                              <button
                                className="sfp2-btn danger"
                                type="button"
                                onClick={() => openDropModal(r.name, r.delta_type, r.referenced_in)}
                                disabled={pendingMutation === `drop:${r.name}`}
                              >
                                Remove
                              </button>
                            )}
                          </div>
                        </div>
                        );
                      })}
                  </div>
                </div>

                {/* Only SF */}
                <div className="sfp2-bucket">
                  <div className="sfp2-bucket-header">
                    <span className="sfp2-bucket-title sf">Only in Salesforce</span>
                    <span className="sfp2-bucket-count">
                      {diff?.only_in_sf.filter((r) => matchesBucketFilter(r.name)).length ?? 0}
                    </span>
                  </div>
                  <div className="sfp2-bucket-rows">
                    {!diff && <div className="sfp2-empty">No diff loaded.</div>}
                    {diff?.only_in_sf
                      .filter((r) => matchesBucketFilter(r.name))
                      .map((r) => {
                        const isPreviewing = addPreview?.field?.name === r.name;
                        const previewKey = `add:${r.name}`;
                        return (
                          <div key={r.name}>
                            <div className="sfp2-row">
                              <span className="sfp2-row-name">
                                {r.name}
                                {r.custom ? ' ✦' : ''}
                              </span>
                              <span className="sfp2-row-meta">
                                sf: {r.type ?? '?'}
                                {r.label ? ` · ${r.label}` : ''}
                              </span>
                              <div className="sfp2-row-actions">
                                <button
                                  className="sfp2-btn sfp2-btn-copy"
                                  type="button"
                                  onClick={() => handleCopy(r.name!)}
                                  title={`Copy "${r.name}" to clipboard`}
                                >
                                  {copiedColumn === r.name ? 'Copied!' : 'Copy'}
                                </button>
                                {pendingByColumn.get((r.name ?? '').toLowerCase()) === 'add_pending' ? (
                                  <PendingPill
                                    kind="add"
                                    onCancel={() => handleCancelPending(r.name!)}
                                  />
                                ) : (
                                  <>
                                    {!isPreviewing && (
                                      <button
                                        className="sfp2-btn primary"
                                        type="button"
                                        onClick={() => handleAddPreview(r)}
                                        disabled={pendingMutation === previewKey}
                                      >
                                        Add to Delta…
                                      </button>
                                    )}
                                    {isPreviewing && (
                                      <button
                                        className="sfp2-btn"
                                        type="button"
                                        onClick={() => setAddPreview(null)}
                                        disabled={pendingMutation === previewKey}
                                      >
                                        Cancel
                                      </button>
                                    )}
                                  </>
                                )}
                              </div>
                            </div>
                            {isPreviewing && (
                              <div className="sfp2-preview">
                                {addPreview.loading && (
                                  <span className="sfp2-row-meta">Computing preview…</span>
                                )}
                                {addPreview.error && (
                                  <div className="sfp2-banner error inline">
                                    {addPreview.error}
                                  </div>
                                )}
                                {addPreview.result && addPreview.result.success && (
                                  <>
                                    <div className="sfp2-preview-line">
                                      <strong>Proposed:</strong>{' '}
                                      <code>{addPreview.result.delta_type}</code>
                                      {addPreview.result.nullable === false ? '' : ' · nullable'}
                                    </div>
                                    {addPreview.result.warnings &&
                                      addPreview.result.warnings.length > 0 && (
                                        <ul className="sfp2-preview-warnings">
                                          {addPreview.result.warnings.map((w, i) => (
                                            <li key={i}>{w}</li>
                                          ))}
                                        </ul>
                                      )}
                                    <div className="sfp2-preview-line muted">
                                      Confirming queues this column for the next
                                      overnight refresh, when the column is added
                                      and Salesforce data lands in the same run.
                                    </div>
                                    <div className="sfp2-row-actions">
                                      <button
                                        className="sfp2-btn primary"
                                        type="button"
                                        onClick={handleAddConfirm}
                                        disabled={pendingMutation === previewKey}
                                      >
                                        {pendingMutation === previewKey
                                          ? 'Queuing…'
                                          : 'Queue add for tonight'}
                                      </button>
                                    </div>
                                  </>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })}
                  </div>
                </div>
              </div>
            </div>

            <div className="sfp2-banner muted sfp2-tip">
              Tip: ingestion only queries Salesforce for fields that already exist in the
              Delta schema. Adding a column here makes the next ingestion run pick it up
              automatically — no notebook change required.
            </div>

            <SchemaChangesPanel
              table={selectedTable}
              rows={changes}
              loading={changesLoading}
              error={changesError}
              onRefresh={() => void loadChanges(selectedTable)}
              onCancel={(col) => void handleCancelPending(col)}
            />
          </div>
        </div>
      </div>

      {dropTarget && (
        <div
          className="sfp2-modal-backdrop"
          role="dialog"
          aria-modal="true"
          onClick={() => !dropTarget.submitting && setDropTarget(null)}
        >
          <div className="sfp2-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Remove column {dropTarget.column}</h3>
            <p>
              Removing <code>{dropTarget.column}</code> from <code>{selectedTable}</code>
              {dropTarget.delta_type ? <> ({dropTarget.delta_type})</> : null} queues a
              drop that runs during the next overnight refresh. The column stays in the
              bronze Delta table until then; you can cancel the request from the
              "Recent schema changes" panel below.
            </p>
            {dropTarget.referenced_in && dropTarget.referenced_in.length > 0 && (
              <div className="sfp2-banner error inline">
                <strong>This column is referenced in {dropTarget.referenced_in.length} Synapse notebook{dropTarget.referenced_in.length === 1 ? '' : 's'}:</strong>
                <ul className="sfp2-modal-refs">
                  {dropTarget.referenced_in.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
            <p className="sfp2-row-meta">
              Type the column name <code>{dropTarget.column}</code> to confirm:
            </p>
            <input
              className="sfp2-input"
              type="text"
              autoFocus
              aria-label={`Type ${dropTarget.column} to confirm removal`}
              placeholder={dropTarget.column}
              value={dropTarget.typed}
              disabled={dropTarget.submitting}
              onChange={(e) =>
                setDropTarget((prev) => (prev ? { ...prev, typed: e.target.value } : prev))
              }
            />
            {dropTarget.error && (
              <div className="sfp2-banner error inline">
                {dropTarget.error}
                {dropTarget.remediation && (
                  <pre className="sfp2-remediation">{dropTarget.remediation}</pre>
                )}
              </div>
            )}
            <div className="sfp2-modal-actions">
              <button
                className="sfp2-btn"
                type="button"
                onClick={() => setDropTarget(null)}
                disabled={dropTarget.submitting}
              >
                Cancel
              </button>
              <button
                className="sfp2-btn danger"
                type="button"
                onClick={handleDropConfirm}
                disabled={
                  dropTarget.submitting || dropTarget.typed !== dropTarget.column
                }
              >
                {dropTarget.submitting ? 'Removing…' : 'Confirm remove'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

interface SchemaChangesPanelProps {
  table: string;
  rows: SchemaChangeRow[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onCancel: (column: string) => void;
}

const _stateLabel: Record<string, string> = {
  pending: 'Pending overnight (drop)',
  add_pending: 'Pending overnight (add)',
  done: 'Dropped',
  failed: 'Drop failed',
  canceled: 'Canceled',
  add_canceled: 'Canceled',
  added: 'Added',
  add_failed: 'Add failed',
  superseded: 'Superseded',
};

const _formatTs = (ts?: string) => {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
};

/**
 * Inline pill rendered in place of the Add / Remove button once a column
 * change has been queued for the overnight worker. Shows the kind of
 * pending change (add or drop) and a Cancel link.
 */
const PendingPill = ({
  kind,
  onCancel,
}: {
  kind: 'add' | 'drop';
  onCancel: () => void;
}) => (
  <span className={`sfp2-pending-pill state-${kind === 'add' ? 'add_pending' : 'pending'}`}>
    <span className="sfp2-pending-pill-label">
      {kind === 'add' ? 'Add pending overnight' : 'Drop pending overnight'}
    </span>
    <button
      type="button"
      className="sfp2-pending-pill-cancel"
      onClick={onCancel}
      title="Cancel this pending change"
    >
      Cancel
    </button>
  </span>
);

const SchemaChangesPanel = ({
  table,
  rows,
  loading,
  error,
  onRefresh,
  onCancel,
}: SchemaChangesPanelProps) => {
  return (
    <div className="sfp2-card sfp2-changes-card">
      <div className="sfp2-toolbar">
        <h3 className="sfp2-changes-title">Recent schema changes</h3>
        <span className="sfp2-row-meta">
          {table ? `for ${table}` : '— select a table —'}
        </span>
        <button
          className="sfp2-btn"
          type="button"
          onClick={onRefresh}
          disabled={!table || loading}
        >
          {loading ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {error && <div className="sfp2-banner error inline">{error}</div>}
      {!table && (
        <div className="sfp2-empty">Select a table to view its change history.</div>
      )}
      {table && rows.length === 0 && !loading && !error && (
        <div className="sfp2-empty">No recent schema changes for {table}.</div>
      )}
      {rows.length > 0 && (
        <div className="sfp2-changes-rows">
          {rows.map((r, i) => {
            const state = r.state || '';
            const label = _stateLabel[state] || state || r.action || '';
            return (
              <div
                key={`${r.ts}-${r.column}-${i}`}
                className={`sfp2-change-row state-${state}`}
              >
                <div className="sfp2-change-main">
                  <span className="sfp2-row-name">{r.column}</span>
                  <span className={`sfp2-state-badge state-${state}`}>{label}</span>
                  <span className="sfp2-row-meta">{_formatTs(r.ts)}</span>
                </div>
                <div className="sfp2-row-meta">
                  {r.action} · {r.user_email || 'unknown'}
                  {r.delta_type ? ` · ${r.delta_type}` : ''}
                  {r.error ? ` · error: ${r.error}` : ''}
                </div>
                {state === 'pending' && (
                  <div className="sfp2-row-actions">
                    <button
                      className="sfp2-btn"
                      type="button"
                      onClick={() => onCancel(r.column!)}
                    >
                      Cancel pending drop
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Sfp2;
