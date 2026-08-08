// NFBC Adjustment console — page shell. Owns queue state; renders the editable
// queue grid, the focused 3-pane detail, audit overlay, and toasts.

import { useCallback, useEffect, useState } from 'react';
import '../Tamarac2.css';
import './Nfbc.css';
import type { NfbcRow, EditPatch, AuditResponse, JiraDiag, BuildProgress } from './types';
import { fetchQueue, editRow, confirmRow, fetchAudit, fetchHousehold } from './services/nfbc';
import { QueueGrid } from './components/QueueGrid';
import { QueueSummary } from './components/QueueSummary';
import { QueueSkeleton } from './components/QueueSkeleton';
import { PastAdjustments } from './components/PastAdjustments';
import { RowDetail } from './components/RowDetail';

type AdjRow = AuditResponse['db_adjustments'][number];
const pastKey = (avhhid: unknown, period: unknown, amount: unknown) =>
  `${String(avhhid ?? '').trim()}|${String(period ?? '').slice(0, 10)}|${Math.round(Number(amount) || 0)}`;

const ADJUSTMENT_TYPES = [
  'Net New', 'courtesy', 'RD Approval', 'Account Processing Delay',
  'Transition', 'Estate', 'Correction',
];

interface Toast { id: number; kind: 'ok' | 'err' | 'info'; msg: string; }

export default function Nfbc() {
  const [rows, setRows] = useState<NfbcRow[]>([]);
  const [builtAt, setBuiltAt] = useState<number | null>(null);
  const [diag, setDiag] = useState<JiraDiag | null>(null);
  const [jqlCount, setJqlCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [progress, setProgress] = useState<BuildProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [audit, setAudit] = useState<AuditResponse | null>(null);
  const [pastAdj, setPastAdj] = useState<AuditResponse['db_adjustments']>([]);
  const [pastConfirmed, setPastConfirmed] = useState<NfbcRow[]>([]);
  const [pastSelected, setPastSelected] = useState<NfbcRow | null>(null);
  const [pastSelectedKey, setPastSelectedKey] = useState<string | null>(null);
  const [pastLoading, setPastLoading] = useState(true);

  const toast = useCallback((kind: Toast['kind'], msg: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, kind, msg }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  const load = useCallback(async (refresh: boolean) => {
    setLoading(true);
    setError(null);
    try {
      let res = await fetchQueue({ refresh });
      // 202 building: backend builds the queue in a background thread
      // (Jira + Claude + Synapse per ticket can take minutes). Poll until done,
      // surfacing per-ticket progress so the UI can show a determinate bar.
      while (res.ok && res.building) {
        setBuilding(true);
        setProgress(res.progress ?? null);
        await new Promise((r) => setTimeout(r, 5000));
        res = await fetchQueue({});
      }
      setBuilding(false);
      setProgress(null);
      if (!res.ok) throw new Error(res.error || 'Failed to build queue');
      setRows(res.rows);
      setBuiltAt(res.built_at ?? null);
      setDiag(res.diag ?? null);
      setJqlCount(res.jql_ticket_count ?? null);
      if (!selectedId && res.rows.length) setSelectedId(res.rows[0].row_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
      setBuilding(false);
    }
  }, [selectedId]);

  useEffect(() => { void load(false); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Esc closes whichever adjustment-flow modal is open.
  useEffect(() => {
    if (!selectedId && !pastSelected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { setSelectedId(null); setPastSelected(null); setPastSelectedKey(null); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selectedId, pastSelected]);

  const loadPast = useCallback(async () => {
    setPastLoading(true);
    try {
      const a = await fetchAudit();
      setPastAdj(a.db_adjustments ?? []);
      setPastConfirmed(a.confirmed ?? []);
    } catch (e) {
      toast('err', `Past adjustments failed to load: ${e instanceof Error ? e.message : e}`);
    } finally {
      setPastLoading(false);
    }
  }, [toast]);

  useEffect(() => { void loadPast(); }, [loadPast]);

  const patchRow = (rowId: string, patch: EditPatch) =>
    setRows((rs) => rs.map((r) => (r.row_id === rowId ? { ...r, ...patch } : r)));

  const onEdit = useCallback(async (rowId: string, patch: EditPatch) => {
    patchRow(rowId, patch); // optimistic
    try {
      await editRow(rowId, patch);
    } catch (e) {
      toast('err', `Edit failed: ${e instanceof Error ? e.message : e}`);
      void load(false);
    }
  }, [toast, load]);

  const onConfirm = useCallback(async (rowId: string) => {
    const row = rows.find((r) => r.row_id === rowId);
    const resume = row?.status === 'written_pending_jira';
    setBusyId(rowId);
    try {
      const res = await confirmRow(rowId, resume);
      if (res.ok) {
        patchRow(rowId, { } as EditPatch);
        setRows((rs) => rs.map((r) => (r.row_id === rowId ? { ...r, status: 'confirmed' } : r)));
        toast('ok', `${row?.ticket_key}: written, reply posted, moved to Done.`);
        void loadPast(); // reflect the newly-written row in the past-adjustments panel
      } else {
        const newStatus = res.partial_failure ? 'written_pending_jira' : 'error';
        setRows((rs) => rs.map((r) => (r.row_id === rowId ? { ...r, status: newStatus } : r)));
        toast('err', res.error || 'Confirm failed');
      }
    } catch (e) {
      toast('err', `Confirm failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setBusyId(null);
    }
  }, [rows, toast]);

  const openAudit = useCallback(async () => {
    if (audit) { setAudit(null); return; }
    try {
      setAudit(await fetchAudit());
    } catch (e) {
      toast('err', `Audit load failed: ${e instanceof Error ? e.message : e}`);
    }
  }, [audit, toast]);

  const selected = rows.find((r) => r.row_id === selectedId) ?? null;

  // Select a past adjustment: rich proposal if the tool wrote it, otherwise pull
  // live household investigation (dim + 12-month flows + existing adjustments)
  // so any historical row still opens with full flow detail + reconciliation.
  const onSelectPast = useCallback(async (dbRow: AdjRow, prop: NfbcRow | null) => {
    const k = pastKey(dbRow.avhhid, dbRow.reportingperiod, dbRow.flow_adjustment);
    setPastSelectedKey(k);
    setSelectedId(null);
    if (prop) { setPastSelected(prop); return; }
    const period = String(dbRow.reportingperiod ?? '');
    const amount = Number(dbRow.flow_adjustment);
    // Open immediately with what we have, then fill flows from the investigation.
    setPastSelected({
      row_id: `past:${k}`, ticket_key: '(written outside console)', ticket_summary: '',
      avhhid: Number(dbRow.avhhid), household: (dbRow.sfhhname as string) ?? null,
      advisor: (dbRow.sfadvisor as string) ?? null, period, amount,
      adjustment_type: String(dbRow.adjustment_type ?? ''), rationale: '', draft_reply: '',
      status: 'confirmed', flows: [], existing_adjustments: [],
    });
    try {
      const inv = await fetchHousehold(dbRow.avhhid as string | number);
      setPastSelected((cur) => (cur && cur.row_id === `past:${k}` ? {
        ...cur,
        household: (inv.dim?.sfhhname as string) ?? cur.household,
        advisor: (inv.dim?.sfadvisor as string) ?? cur.advisor,
        flows: inv.flows ?? [],
        existing_adjustments: inv.adjustments ?? [],
      } : cur));
    } catch (e) {
      toast('err', `Household detail failed: ${e instanceof Error ? e.message : e}`);
    }
  }, [toast]);

  return (
    <div className="t2-page">
      <div className="t2-bg" aria-hidden="true">
        <div className="t2-orb t2-orb-1" />
        <div className="t2-orb t2-orb-2" />
        <div className="t2-orb t2-orb-3" />
        <div className="t2-orb t2-orb-4" />
        <div className="t2-orb t2-orb-5" />
      </div>

      <div className="t2-shell">
        <header className="nfbc-hero">
          <div className="nfbc-hero-left">
            <div className="nfbc-kicker-row">
              <a className="nfbc-home" href="/">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                Back to hub
              </a>
              <span className="nfbc-kicker">Agentic ops</span>
            </div>
            <div className="nfbc-title"><h1>NFBC Adjustments</h1></div>
            <p className="nfbc-tagline">
              Review Claude-proposed flow adjustments, edit inline, and confirm to
              write Synapse, run rollforward, and reply to Jira in one click.
            </p>
          </div>
          <div className="nfbc-hero-right">
            {builtAt && (
              <span className="nfbc-built">
                queue built {new Date(builtAt * 1000).toLocaleTimeString()}
              </span>
            )}
            <button className="nfbc-ghost" onClick={openAudit}>Audit</button>
            <button className="nfbc-ghost" onClick={() => load(true)} disabled={loading}>
              {building ? 'Building…' : loading ? 'Loading…' : '↻ Rebuild queue'}
            </button>
          </div>
        </header>

        <main className="nfbc-main">
          {error && <div className="nfbc-error">⚠ {error}</div>}

          {diag && !diag.configured && (
            <div className="nfbc-error">
              ⚠ Jira credentials not loaded (source: <strong>{diag.source ?? 'unknown'}</strong>
              {diag.kv_error ? <> — KV error: <code>{diag.kv_error}</code></> : null}).
              Verify the App Service managed identity has <em>Key Vault Secrets User</em> on{' '}
              <code>{diag.key_vault ?? 'allworthsynapse'}</code>.
            </div>
          )}
          {diag && diag.configured && rows.length === 0 && jqlCount === 0 && (
            <div className="nfbc-info">
              Jira reachable (source: <strong>{diag.source}</strong>) — zero issues match{' '}
              <code>labels = "NFBC_Adjustment" AND statusCategory != Done</code>.
              Either no open NFBC tickets exist, or the label/JQL needs adjusting.
            </div>
          )}

          {loading && rows.length === 0 ? (
            <QueueSkeleton progress={progress} rowCount={jqlCount ?? 6} />
          ) : (
            <>
              <div className="nfbc-queue-col">
                <QueueSummary rows={rows} />
                <div className="nfbc-section-head">
                  <h2>Proposal queue</h2>
                  <span className="nfbc-section-count">
                    {rows.length} item{rows.length === 1 ? '' : 's'}
                  </span>
                </div>
                <QueueGrid
                  rows={rows}
                  selectedRowId={selectedId}
                  busyRowId={busyId}
                  adjustmentTypes={ADJUSTMENT_TYPES}
                  onSelect={setSelectedId}
                  onEdit={onEdit}
                  onConfirm={onConfirm}
                />
              </div>
            </>
          )}

          {selected && (
            <div
              className="nfbc-flow-overlay"
              onClick={() => setSelectedId(null)}
              role="presentation"
            >
              <div
                className="nfbc-flow-modal"
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-label={`Adjustment flow for ${selected.household ?? selected.ticket_key}`}
              >
                <button
                  className="nfbc-flow-close"
                  onClick={() => setSelectedId(null)}
                  aria-label="Close (Esc)"
                  title="Close (Esc)"
                >
                  ✕
                </button>
                <RowDetail
                  row={selected}
                  busy={busyId === selected.row_id}
                  onEditReply={(rid, draft_reply) => onEdit(rid, { draft_reply })}
                  onConfirm={onConfirm}
                />
              </div>
            </div>
          )}

          <PastAdjustments
            rows={pastAdj}
            confirmed={pastConfirmed}
            selectedKey={pastSelectedKey}
            loading={pastLoading}
            onRefresh={loadPast}
            onSelect={onSelectPast}
          />

          {pastSelected && (
            <div
              className="nfbc-flow-overlay"
              onClick={() => { setPastSelected(null); setPastSelectedKey(null); }}
              role="presentation"
            >
              <div
                className="nfbc-flow-modal"
                onClick={(e) => e.stopPropagation()}
                role="dialog"
                aria-modal="true"
                aria-label={`Adjustment detail for ${pastSelected.household ?? pastSelected.ticket_key}`}
              >
                <button
                  className="nfbc-flow-close"
                  onClick={() => { setPastSelected(null); setPastSelectedKey(null); }}
                  aria-label="Close (Esc)"
                  title="Close (Esc)"
                >
                  ✕
                </button>
                <RowDetail
                  row={pastSelected}
                  busy={false}
                  onEditReply={() => { /* historical — read only */ }}
                  onConfirm={() => { /* historical — read only */ }}
                />
              </div>
            </div>
          )}
        </main>

        <footer className="nfbc-footer">
          Powered by <strong>Jarvis</strong>
        </footer>
      </div>

      {audit && (
        <div className="nfbc-audit-overlay" onClick={() => setAudit(null)}>
          <div className="nfbc-audit" onClick={(e) => e.stopPropagation()}>
            <h3>Recent actions</h3>
            <ul className="nfbc-audit-log">
              {audit.actions.slice(0, 50).map((a, i) => {
                const e = a as Record<string, unknown>;
                const ts = e.ts ? new Date(String(e.ts)).toLocaleString() : '';
                const meta = [e.row_id, e.ticket, e.user].filter(Boolean).map(String).join(' · ');
                return (
                  <li key={i} className="nfbc-audit-entry">
                    <span className="nfbc-audit-when">{ts}</span>
                    <span className="nfbc-audit-action">{String(e.action ?? '—')}</span>
                    <span className="nfbc-audit-meta mono">{meta}</span>
                  </li>
                );
              })}
              {audit.actions.length === 0 && (
                <li className="nfbc-audit-empty">No actions recorded yet.</li>
              )}
            </ul>
            <h3>Adjustments in Synapse ({audit.db_adjustments.length})</h3>
            <table className="nfbc-mini">
              <thead><tr><th>avhhid</th><th>Household</th><th>Period</th><th className="num">Amount</th><th>Type</th></tr></thead>
              <tbody>
                {audit.db_adjustments.slice(0, 100).map((a, i) => (
                  <tr key={i}>
                    <td className="mono">{String(a.avhhid ?? '')}</td>
                    <td>{String(a.sfhhname ?? '')}</td>
                    <td>{String(a.reportingperiod ?? '')}</td>
                    <td className="num">{String(a.flow_adjustment ?? '')}</td>
                    <td>{String(a.adjustment_type ?? '')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button className="nfbc-ghost" onClick={() => setAudit(null)}>Close</button>
          </div>
        </div>
      )}

      <div className="nfbc-toasts">
        {toasts.map((t) => (
          <div key={t.id} className={`nfbc-toast ${t.kind}`}>{t.msg}</div>
        ))}
      </div>
    </div>
  );
}
