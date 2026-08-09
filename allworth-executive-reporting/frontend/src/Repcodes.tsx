// src/Repcodes.tsx
// Editable grid for tho.repcodes (Synapse dedicated SQL pool).
// - Click any non-bit cell to edit; Enter/blur saves, Esc cancels.
// - Click a bit checkbox to toggle; saves immediately.
// - "Add row" inserts a blank row; fill it in and the first save persists it.
// - Trash icon deletes a row (with confirm).
//
// Concurrency model: last-write-wins. The server stamps modified_by/modified_at
// from the JWT on every write.

import { useCallback, useEffect, useMemo, useState, type UIEvent } from 'react';
import {
  bulkUpsertRepcodes,
  createRepcode,
  deleteRepcode,
  fetchRecentHistory,
  fetchRepcodes,
  fetchRowHistory,
  restoreVersion,
  undoBatch,
  undoChange,
  updateRepcode,
  type BulkMatchKey,
  type BulkUpsertResult,
  type RepcodeHistoryRow,
  type RepcodeRow,
  type RepcodeWritePayload,
} from './services/repcodes';
import './Repcodes.css';
import { ToolPage } from './components/ToolPage';
import ShareTool from './components/ShareTool';

interface ColumnDef {
  key: keyof RepcodeRow;
  label: string;
  type: 'text' | 'bit';
  width?: number;
}

const COLUMNS: ColumnDef[] = [
  { key: 'custodian',                    label: 'Custodian',           type: 'text', width: 110 },
  { key: 'actively_used',                label: 'Active',              type: 'bit'  },
  { key: 'wrap_fee_type',                label: 'Wrap Fee Type',       type: 'text', width: 100 },
  { key: 'for_employee_accounts',        label: 'Employee',            type: 'bit'  },
  { key: 'fidelity_g_number',            label: 'Fidelity G #',        type: 'text', width: 110 },
  { key: 'g_number_usage',               label: 'G # Usage',           type: 'text', width: 130 },
  { key: 'description',                  label: 'Description',         type: 'text', width: 200 },
  { key: 'notes',                        label: 'Notes',               type: 'text', width: 240 },
  { key: 'schwab_master_account',        label: 'Schwab Master Acct',  type: 'text', width: 130 },
  { key: 'master_account_type',          label: 'Master Acct Type',    type: 'text', width: 130 },
  { key: 'allworth_advisor',             label: 'Advisor',             type: 'text', width: 150 },
  { key: 'allworth_office',              label: 'Office',              type: 'text', width: 130 },
  { key: 'separate_account_manager',     label: 'SAM',                 type: 'text', width: 130 },
  { key: 'sma_strategy',                 label: 'SMA Strategy',        type: 'text', width: 130 },
  { key: 'other_third_party',            label: '3rd Party',           type: 'text', width: 130 },
  { key: 'american_funds_rep_number',    label: 'AF Rep #',            type: 'text', width: 100 },
  { key: 'american_funds_branch_number', label: 'AF Branch #',         type: 'text', width: 100 },
  { key: 'bloomwell_529_rep_code',       label: 'Bloomwell 529',       type: 'text', width: 110 },
];

const EDITABLE_KEYS = COLUMNS.map((c) => c.key);

// Build header alias map: normalized header -> canonical column key.
// Accepts both exact column names (e.g. 'fidelity_g_number') and friendly
// labels (e.g. 'Fidelity G #').
const normalizeHeader = (s: string): string =>
  s.toLowerCase().replace(/[^a-z0-9]/g, '');

const HEADER_ALIASES: Record<string, keyof RepcodeRow> = (() => {
  const map: Record<string, keyof RepcodeRow> = {};
  for (const c of COLUMNS) {
    map[normalizeHeader(c.key as string)] = c.key;
    map[normalizeHeader(c.label)] = c.key;
  }
  return map;
})();

// Minimal CSV parser: handles quoted fields, embedded commas, doubled quotes,
// and CRLF or LF line endings. Returns array of arrays (raw cell strings).
const parseCsv = (text: string): string[][] => {
  const out: string[][] = [];
  let row: string[] = [];
  let cell = '';
  let inQuotes = false;
  let i = 0;
  const n = text.length;
  while (i < n) {
    const ch = text[i];
    if (inQuotes) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          cell += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i += 1;
        continue;
      }
      cell += ch;
      i += 1;
      continue;
    }
    if (ch === '"') {
      inQuotes = true;
      i += 1;
      continue;
    }
    if (ch === ',') {
      row.push(cell);
      cell = '';
      i += 1;
      continue;
    }
    if (ch === '\r') {
      i += 1;
      continue;
    }
    if (ch === '\n') {
      row.push(cell);
      out.push(row);
      row = [];
      cell = '';
      i += 1;
      continue;
    }
    cell += ch;
    i += 1;
  }
  // Trailing cell / row
  if (cell !== '' || row.length > 0) {
    row.push(cell);
    out.push(row);
  }
  // Drop fully empty trailing rows
  while (out.length > 0 && out[out.length - 1].every((c) => c === '')) {
    out.pop();
  }
  return out;
};

interface ParseResult {
  rows: RepcodeWritePayload[];
  unknownHeaders: string[];
  mappedHeaders: Array<keyof RepcodeRow | null>;
}

const parseCsvToPayloads = (text: string): ParseResult => {
  const grid = parseCsv(text);
  if (grid.length < 2) {
    return { rows: [], unknownHeaders: [], mappedHeaders: [] };
  }
  const headerRow = grid[0];
  const mapped: Array<keyof RepcodeRow | null> = headerRow.map((h) => {
    const key = HEADER_ALIASES[normalizeHeader(h)];
    return key ?? null;
  });
  const unknown = headerRow.filter((h, idx) => mapped[idx] === null && h.trim() !== '');
  const rows: RepcodeWritePayload[] = [];
  for (let r = 1; r < grid.length; r++) {
    const raw = grid[r];
    const payload: RepcodeWritePayload = {};
    let hasAny = false;
    for (let c = 0; c < raw.length && c < mapped.length; c++) {
      const key = mapped[c];
      if (!key) continue;
      const v = raw[c].trim();
      // Blank => null (per spec); backend coerces.
      (payload as Record<string, unknown>)[key as string] = v === '' ? null : v;
      if (v !== '') hasAny = true;
    }
    if (hasAny) rows.push(payload);
  }
  return { rows, unknownHeaders: unknown, mappedHeaders: mapped };
};

const BLANK_ROW: RepcodeRow = {
  repcode_id: 0,
  custodian: null,
  actively_used: false,
  wrap_fee_type: null,
  for_employee_accounts: false,
  fidelity_g_number: null,
  g_number_usage: null,
  description: null,
  notes: null,
  schwab_master_account: null,
  master_account_type: null,
  allworth_advisor: null,
  allworth_office: null,
  separate_account_manager: null,
  sma_strategy: null,
  other_third_party: null,
  american_funds_rep_number: null,
  american_funds_branch_number: null,
  bloomwell_529_rep_code: null,
  modified_by: null,
  modified_at: null,
};

const buildPayload = (row: RepcodeRow): RepcodeWritePayload => {
  const out: RepcodeWritePayload = {};
  for (const key of EDITABLE_KEYS) {
    (out as Record<string, unknown>)[key as string] = row[key];
  }
  return out;
};

const rowMatchesFilter = (row: RepcodeRow, q: string): boolean => {
  if (!q) return true;
  const needle = q.toLowerCase();
  for (const col of COLUMNS) {
    const v = row[col.key];
    if (v == null) continue;
    if (String(v).toLowerCase().includes(needle)) return true;
  }
  return false;
};

// --- Change-history helpers --------------------------------------------------

const cellText = (v: unknown): string =>
  v == null || v === '' ? '∅' : String(v);

interface FieldChange {
  label: string;
  from: string;
  to: string;
}

// Compare a history entry to the older entry that preceded it. Entries arrive
// newest-first, so the "previous" version is the next item in the array.
const diffEntries = (
  newer: RepcodeHistoryRow,
  older: RepcodeHistoryRow | undefined
): FieldChange[] => {
  const changes: FieldChange[] = [];
  for (const c of COLUMNS) {
    const key = c.key as keyof RepcodeHistoryRow;
    const to = newer[key];
    const from = older ? older[key] : undefined;
    if (cellText(from) !== cellText(to)) {
      changes.push({ label: c.label, from: cellText(from), to: cellText(to) });
    }
  }
  return changes;
};

const fmtTimestamp = (iso: string | null): string =>
  iso ? iso.replace('T', ' ').slice(0, 16) : '';

const OP_LABEL: Record<string, string> = {
  INSERT: 'Created',
  UPDATE: 'Edited',
  DELETE: 'Deleted',
  RESTORE: 'Restored',
  BASELINE: 'Baseline',
};

// How many rows to render per page, and how close to the bottom (px) the user
// must scroll before the next page is appended.
const PAGE_SIZE = 250;
const SCROLL_THRESHOLD_PX = 300;

const Repcodes = () => {
  const [rows, setRows] = useState<RepcodeRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [filter, setFilter] = useState('');
  const [filterInput, setFilterInput] = useState('');
  const [editing, setEditing] = useState<{ id: number; key: keyof RepcodeRow } | null>(null);
  const [draft, setDraft] = useState<string>('');
  const [savingIds, setSavingIds] = useState<Set<number>>(new Set());
  // Negative ids indicate locally-created rows that haven't been saved yet.
  const [nextLocalId, setNextLocalId] = useState(-1);

  // Bulk upload state
  const [showUpload, setShowUpload] = useState(false);
  const [uploadFileName, setUploadFileName] = useState<string>('');
  const [parsedRows, setParsedRows] = useState<RepcodeWritePayload[]>([]);
  const [unknownHeaders, setUnknownHeaders] = useState<string[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);
  const [matchKey, setMatchKey] = useState<BulkMatchKey>('fidelity_g_number');
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<BulkUpsertResult | null>(null);

  // Per-row history drawer state
  const [historyRowId, setHistoryRowId] = useState<number | null>(null);
  const [historyRows, setHistoryRows] = useState<RepcodeHistoryRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Recent-changes feed state
  const [showFeed, setShowFeed] = useState(false);
  const [feedRows, setFeedRows] = useState<RepcodeHistoryRow[]>([]);
  const [feedLoading, setFeedLoading] = useState(false);

  // Shared busy flag so history actions disable their buttons while in flight.
  const [historyBusy, setHistoryBusy] = useState(false);

  // Render rows in pages so 900+ × 18 cells don't grind the browser to a halt
  // on first paint. We render PAGE_SIZE rows, then grow as the user scrolls.
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // Debounce filter input so each keystroke doesn't re-render the entire grid.
  useEffect(() => {
    const handle = window.setTimeout(() => setFilter(filterInput), 200);
    return () => window.clearTimeout(handle);
  }, [filterInput]);

  // Reset paging to the top whenever the result set changes.
  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [filter]);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchRepcodes();
      setRows(resp.rows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  const flashInfo = (msg: string) => {
    setInfo(msg);
    window.setTimeout(() => setInfo((cur) => (cur === msg ? null : cur)), 2500);
  };

  const markSaving = (id: number, on: boolean) => {
    setSavingIds((cur) => {
      const next = new Set(cur);
      if (on) next.add(id);
      else next.delete(id);
      return next;
    });
  };

  const persistRow = useCallback(async (row: RepcodeRow) => {
    markSaving(row.repcode_id, true);
    setError(null);
    try {
      if (row.repcode_id < 0) {
        const resp = await createRepcode(buildPayload(row));
        // Reload the row from server so we get the real id + audit cols.
        setRows((cur) =>
          cur.map((r) =>
            r.repcode_id === row.repcode_id
              ? { ...row, repcode_id: resp.repcode_id }
              : r
          )
        );
        flashInfo(`Created row #${resp.repcode_id}`);
        // Refresh in background to capture modified_by / modified_at.
        void loadAll();
      } else {
        await updateRepcode(row.repcode_id, buildPayload(row));
        flashInfo(`Saved row #${row.repcode_id}`);
        // Update audit columns optimistically; full reload would be expensive.
        setRows((cur) =>
          cur.map((r) =>
            r.repcode_id === row.repcode_id
              ? { ...row, modified_at: new Date().toISOString() }
              : r
          )
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      markSaving(row.repcode_id, false);
    }
  }, [loadAll]);

  const handleCellSave = useCallback(
    (rowId: number, key: keyof RepcodeRow, raw: string) => {
      setEditing(null);
      const trimmed = raw.trim();
      const newVal: string | null = trimmed === '' ? null : trimmed;
      const target = rows.find((r) => r.repcode_id === rowId);
      if (!target) return;
      if (target[key] === newVal) return;
      const updated: RepcodeRow = { ...target, [key]: newVal };
      setRows((cur) => cur.map((r) => (r.repcode_id === rowId ? updated : r)));
      void persistRow(updated);
    },
    [rows, persistRow]
  );

  const handleBitToggle = useCallback(
    (rowId: number, key: keyof RepcodeRow, checked: boolean) => {
      const target = rows.find((r) => r.repcode_id === rowId);
      if (!target) return;
      const updated: RepcodeRow = { ...target, [key]: checked };
      setRows((cur) => cur.map((r) => (r.repcode_id === rowId ? updated : r)));
      void persistRow(updated);
    },
    [rows, persistRow]
  );

  const handleDelete = useCallback(
    async (rowId: number) => {
      if (rowId < 0) {
        // Unsaved local row — just drop it.
        setRows((cur) => cur.filter((r) => r.repcode_id !== rowId));
        return;
      }
      if (!window.confirm(`Delete row #${rowId}? This cannot be undone.`)) return;
      markSaving(rowId, true);
      setError(null);
      try {
        await deleteRepcode(rowId);
        setRows((cur) => cur.filter((r) => r.repcode_id !== rowId));
        flashInfo(`Deleted row #${rowId}`);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        markSaving(rowId, false);
      }
    },
    []
  );

  const handleAddRow = () => {
    const id = nextLocalId;
    setNextLocalId((cur) => cur - 1);
    setRows((cur) => [{ ...BLANK_ROW, repcode_id: id }, ...cur]);
  };

  const resetUpload = () => {
    setUploadFileName('');
    setParsedRows([]);
    setUnknownHeaders([]);
    setParseError(null);
    setUploadResult(null);
  };

  const handleFilePick = async (file: File | null) => {
    setParseError(null);
    setUploadResult(null);
    if (!file) {
      setUploadFileName('');
      setParsedRows([]);
      setUnknownHeaders([]);
      return;
    }
    setUploadFileName(file.name);
    try {
      const text = await file.text();
      const result = parseCsvToPayloads(text);
      if (result.rows.length === 0) {
        setParseError('No data rows detected. Ensure the file has a header row and at least one data row.');
        setParsedRows([]);
        setUnknownHeaders(result.unknownHeaders);
        return;
      }
      setParsedRows(result.rows);
      setUnknownHeaders(result.unknownHeaders);
    } catch (e) {
      setParseError((e as Error).message);
      setParsedRows([]);
    }
  };

  const uploadPreview = useMemo(() => {
    if (parsedRows.length === 0) return { willUpdate: 0, willInsert: 0, missingKey: 0 };
    const existingKeys = new Set<string>();
    for (const r of rows) {
      const v = r[matchKey];
      if (v != null && v !== '') existingKeys.add(String(v));
    }
    let willUpdate = 0;
    let willInsert = 0;
    let missingKey = 0;
    for (const p of parsedRows) {
      const v = (p as Record<string, unknown>)[matchKey];
      if (v == null || v === '') {
        missingKey += 1;
        willInsert += 1;
      } else if (existingKeys.has(String(v))) {
        willUpdate += 1;
      } else {
        willInsert += 1;
      }
    }
    return { willUpdate, willInsert, missingKey };
  }, [parsedRows, rows, matchKey]);

  const handleApplyUpload = async () => {
    if (parsedRows.length === 0) return;
    setUploading(true);
    setError(null);
    setUploadResult(null);
    try {
      const res = await bulkUpsertRepcodes(matchKey, parsedRows);
      setUploadResult(res);
      flashInfo(`Bulk upsert: ${res.inserted} inserted, ${res.updated} updated`);
      await loadAll();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
    }
  };

  const handleDownloadTemplate = () => {
    const header = EDITABLE_KEYS.join(',');
    const blob = new Blob([header + '\n'], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'repcodes_template.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  // --- History / rollback -------------------------------------------------

  const loadRowHistory = useCallback(async (id: number) => {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const resp = await fetchRowHistory(id);
      setHistoryRows(resp.rows);
    } catch (e) {
      setHistoryError((e as Error).message);
      setHistoryRows([]);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  const openHistory = useCallback(
    (id: number) => {
      setHistoryRowId(id);
      setHistoryRows([]);
      void loadRowHistory(id);
    },
    [loadRowHistory]
  );

  const closeHistory = () => {
    setHistoryRowId(null);
    setHistoryRows([]);
    setHistoryError(null);
  };

  const loadFeed = useCallback(async () => {
    setFeedLoading(true);
    try {
      const resp = await fetchRecentHistory(50);
      setFeedRows(resp.rows);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setFeedLoading(false);
    }
  }, []);

  const toggleFeed = () => {
    setShowFeed((open) => {
      const next = !open;
      if (next) void loadFeed();
      return next;
    });
  };

  const handleRestore = useCallback(
    async (id: number, historyId: number) => {
      if (!window.confirm(`Restore row #${id} to this version?`)) return;
      setHistoryBusy(true);
      setError(null);
      try {
        const res = await restoreVersion(id, historyId);
        flashInfo(`Row #${id} ${res.outcome === 'inserted' ? 'restored (re-created)' : 'restored'}`);
        await loadAll();
        await loadRowHistory(id);
        if (showFeed) void loadFeed();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setHistoryBusy(false);
      }
    },
    [loadAll, loadRowHistory, loadFeed, showFeed]
  );

  const handleUndo = useCallback(
    async (entry: RepcodeHistoryRow) => {
      const verb = OP_LABEL[entry.operation] ?? entry.operation;
      if (
        !window.confirm(
          `Undo this change ("${verb}" on row #${entry.repcode_id})? The row will be reverted to its previous state.`
        )
      )
        return;
      setHistoryBusy(true);
      setError(null);
      try {
        const res = await undoChange(entry.history_id);
        flashInfo(
          res.outcome === 'deleted'
            ? `Row #${entry.repcode_id} removed (undid its creation)`
            : `Row #${entry.repcode_id} reverted`
        );
        await loadAll();
        await loadFeed();
        if (historyRowId === entry.repcode_id) await loadRowHistory(historyRowId);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setHistoryBusy(false);
      }
    },
    [loadAll, loadFeed, loadRowHistory, historyRowId]
  );

  const handleUndoBatch = useCallback(
    async (batchId: string, count: number) => {
      if (
        !window.confirm(
          `Undo this entire import (${count} change${count === 1 ? '' : 's'})? Every affected row will be reverted to its prior state.`
        )
      )
        return;
      setHistoryBusy(true);
      setError(null);
      try {
        const res = await undoBatch(batchId);
        flashInfo(`Import undone: ${res.reverted} reverted, ${res.deleted} removed`);
        await loadAll();
        await loadFeed();
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setHistoryBusy(false);
      }
    },
    [loadAll, loadFeed]
  );

  // Group the feed so a bulk import shows as one undoable block. Consecutive
  // entries sharing a batch_id collapse into a single group.
  const feedGroups = useMemo(() => {
    const groups: Array<
      | { kind: 'single'; entry: RepcodeHistoryRow }
      | { kind: 'batch'; batchId: string; entries: RepcodeHistoryRow[] }
    > = [];
    for (const entry of feedRows) {
      if (entry.batch_id) {
        const last = groups[groups.length - 1];
        if (last && last.kind === 'batch' && last.batchId === entry.batch_id) {
          last.entries.push(entry);
          continue;
        }
        groups.push({ kind: 'batch', batchId: entry.batch_id, entries: [entry] });
      } else {
        groups.push({ kind: 'single', entry });
      }
    }
    return groups;
  }, [feedRows]);

  const filteredRows = useMemo(
    () => rows.filter((r) => rowMatchesFilter(r, filter)),
    [rows, filter]
  );

  const visibleRows = useMemo(
    () => filteredRows.slice(0, visibleCount),
    [filteredRows, visibleCount]
  );
  const hasMore = visibleCount < filteredRows.length;

  // Append the next page when the user scrolls near the bottom of the grid.
  const handleTableScroll = useCallback(
    (e: UIEvent<HTMLDivElement>) => {
      const el = e.currentTarget;
      if (el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_THRESHOLD_PX) {
        setVisibleCount((c) => (c < filteredRows.length ? c + PAGE_SIZE : c));
      }
    },
    [filteredRows.length]
  );

  const startEdit = (id: number, key: keyof RepcodeRow, current: unknown) => {
    setEditing({ id, key });
    setDraft(current == null ? '' : String(current));
  };

  return (
    <ToolPage
      eyebrow="Synapse · tho.repcodes"
      title="Allworth Rep Codes"
      description="Review, edit, upload, and audit representative-code mappings in the warehouse."
      actions={<ShareTool toolId="repcodes" toolName="Rep Codes" />}
      width="full"
      className="repcodes-page"
    >

        {error && <div className="repcodes-banner error">{error}</div>}
        {info && <div className="repcodes-banner success">{info}</div>}

        <div className="repcodes-toolbar">
          <input
            type="text"
            placeholder="Filter rows…"
            value={filterInput}
            onChange={(e) => setFilterInput(e.target.value)}
          />
          <button className="repcodes-btn" type="button" onClick={handleAddRow}>
            + Add row
          </button>
          <button
            className="repcodes-btn secondary"
            type="button"
            onClick={() => setShowUpload((v) => !v)}
          >
            {showUpload ? 'Close upload' : 'Upload CSV'}
          </button>
          <button
            className="repcodes-btn secondary"
            type="button"
            onClick={toggleFeed}
          >
            {showFeed ? 'Close changes' : 'Recent changes'}
          </button>
          <button
            className="repcodes-btn secondary"
            type="button"
            onClick={() => void loadAll()}
            disabled={loading}
          >
            {loading ? 'Loading…' : 'Refresh'}
          </button>
          <span className="repcodes-status">
            {hasMore
              ? `Showing ${visibleRows.length} of ${filteredRows.length} matches — scroll to load more…`
              : `${filteredRows.length} of ${rows.length} rows`}
          </span>
        </div>

        {showUpload && (
          <div className="repcodes-upload-panel">
            <div className="repcodes-upload-row">
              <label className="repcodes-upload-label">
                CSV file:
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={(e) => void handleFilePick(e.target.files?.[0] ?? null)}
                />
              </label>
              <label className="repcodes-upload-label">
                Match key:
                <select
                  value={matchKey}
                  onChange={(e) => setMatchKey(e.target.value as BulkMatchKey)}
                >
                  <option value="fidelity_g_number">Fidelity G #</option>
                  <option value="schwab_master_account">Schwab Master Acct</option>
                </select>
              </label>
              <button
                className="repcodes-btn secondary"
                type="button"
                onClick={handleDownloadTemplate}
              >
                Download template
              </button>
              <button
                className="repcodes-btn secondary"
                type="button"
                onClick={resetUpload}
              >
                Clear
              </button>
            </div>
            {parseError && <div className="repcodes-banner error">{parseError}</div>}
            {unknownHeaders.length > 0 && (
              <div className="repcodes-banner error">
                Unrecognized headers (ignored): {unknownHeaders.join(', ')}
              </div>
            )}
            {parsedRows.length > 0 && (
              <div className="repcodes-upload-summary">
                <div>
                  <strong>{uploadFileName}</strong> — parsed {parsedRows.length} data rows.
                </div>
                <div>
                  Matching on <code>{matchKey}</code>:{' '}
                  <strong>{uploadPreview.willUpdate}</strong> will UPDATE,{' '}
                  <strong>{uploadPreview.willInsert}</strong> will INSERT
                  {uploadPreview.missingKey > 0 && (
                    <> (including {uploadPreview.missingKey} with blank match key)</>
                  )}
                  .
                </div>
                <div className="repcodes-upload-actions">
                  <button
                    className="repcodes-btn"
                    type="button"
                    disabled={uploading}
                    onClick={() => void handleApplyUpload()}
                  >
                    {uploading ? 'Applying…' : `Apply (${parsedRows.length} rows)`}
                  </button>
                </div>
              </div>
            )}
            {uploadResult && (
              <div className="repcodes-banner success">
                Done: {uploadResult.inserted} inserted, {uploadResult.updated} updated,{' '}
                {uploadResult.errors.length} errors (of {uploadResult.total} total).
                {uploadResult.errors.length > 0 && (
                  <ul className="repcodes-upload-errors">
                    {uploadResult.errors.slice(0, 5).map((err) => (
                      <li key={err.row_index}>
                        Row {err.row_index}: {err.error}
                      </li>
                    ))}
                    {uploadResult.errors.length > 5 && (
                      <li>… and {uploadResult.errors.length - 5} more.</li>
                    )}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}

        {showFeed && (
          <div className="repcodes-feed-panel">
            <div className="repcodes-feed-head">
              <strong>Recent changes</strong>
              <button
                className="repcodes-btn secondary"
                type="button"
                onClick={() => void loadFeed()}
                disabled={feedLoading}
              >
                {feedLoading ? 'Loading…' : 'Refresh'}
              </button>
            </div>
            {!feedLoading && feedGroups.length === 0 && (
              <div className="repcodes-feed-empty">No changes recorded yet.</div>
            )}
            <ul className="repcodes-feed-list">
              {feedGroups.map((group) =>
                group.kind === 'batch' ? (
                  <li key={`batch-${group.batchId}`} className="repcodes-feed-item batch">
                    <div className="repcodes-feed-main">
                      <span className="repcodes-op-badge bulk">Bulk import</span>
                      <span className="repcodes-feed-summary">
                        {group.entries.length} row{group.entries.length === 1 ? '' : 's'} affected
                        {' · '}
                        {group.entries[0].changed_by ?? 'unknown'}
                        {' · '}
                        {fmtTimestamp(group.entries[0].changed_at)}
                      </span>
                    </div>
                    <button
                      className="repcodes-btn danger small"
                      type="button"
                      disabled={historyBusy}
                      onClick={() => void handleUndoBatch(group.batchId, group.entries.length)}
                    >
                      Undo import
                    </button>
                  </li>
                ) : (
                  <li key={group.entry.history_id} className="repcodes-feed-item">
                    <div className="repcodes-feed-main">
                      <span className={`repcodes-op-badge ${group.entry.operation.toLowerCase()}`}>
                        {OP_LABEL[group.entry.operation] ?? group.entry.operation}
                      </span>
                      <button
                        className="repcodes-link"
                        type="button"
                        onClick={() => openHistory(group.entry.repcode_id)}
                      >
                        #{group.entry.repcode_id}
                      </button>
                      <span className="repcodes-feed-summary">
                        {group.entry.fidelity_g_number ||
                          group.entry.schwab_master_account ||
                          group.entry.description ||
                          '(no label)'}
                        {' · '}
                        {group.entry.changed_by ?? 'unknown'}
                        {' · '}
                        {fmtTimestamp(group.entry.changed_at)}
                      </span>
                    </div>
                    {group.entry.operation !== 'BASELINE' && (
                      <button
                        className="repcodes-btn danger small"
                        type="button"
                        disabled={historyBusy}
                        onClick={() => void handleUndo(group.entry)}
                      >
                        Undo
                      </button>
                    )}
                  </li>
                )
              )}
            </ul>
          </div>
        )}

        <div className="repcodes-table-wrap" onScroll={handleTableScroll}>
          <table className="repcodes-table">
            <thead>
              <tr>
                <th className="repcodes-col-id">ID</th>
                {COLUMNS.map((c) => (
                  <th
                    key={c.key as string}
                    className="repcodes-col-min"
                    ref={(el) => {
                      if (el && c.width) {
                        el.style.setProperty('--col-min', `${c.width}px`);
                      }
                    }}
                  >
                    {c.label}
                  </th>
                ))}
                <th className="repcodes-col-modby">Modified By</th>
                <th className="repcodes-col-modat">Modified At</th>
                <th className="repcodes-col-actions" aria-label="Actions"></th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => {
                const saving = savingIds.has(row.repcode_id);
                const isNew = row.repcode_id < 0;
                return (
                  <tr key={row.repcode_id} className={saving ? 'dirty' : undefined}>
                    <td className="repcodes-cell readonly">
                      {isNew ? '(new)' : row.repcode_id}
                    </td>
                    {COLUMNS.map((c) => {
                      const isEditing =
                        editing?.id === row.repcode_id && editing.key === c.key;
                      const val = row[c.key];
                      if (c.type === 'bit') {
                        return (
                          <td key={c.key as string}>
                            <input
                              type="checkbox"
                              checked={Boolean(val)}
                              disabled={saving}
                              aria-label={`${c.label} for row ${row.repcode_id}`}
                              onChange={(e) =>
                                handleBitToggle(row.repcode_id, c.key, e.target.checked)
                              }
                            />
                          </td>
                        );
                      }
                      if (isEditing) {
                        return (
                          <td key={c.key as string}>
                            <div className="repcodes-cell">
                              <input
                                type="text"
                                autoFocus
                                aria-label={`Edit ${c.label} for row ${row.repcode_id}`}
                                value={draft}
                                onChange={(e) => setDraft(e.target.value)}
                                onBlur={() =>
                                  handleCellSave(row.repcode_id, c.key, draft)
                                }
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    e.currentTarget.blur();
                                  } else if (e.key === 'Escape') {
                                    setEditing(null);
                                  }
                                }}
                              />
                            </div>
                          </td>
                        );
                      }
                      return (
                        <td key={c.key as string}>
                          <div
                            className="repcodes-cell"
                            title={val == null ? '' : String(val)}
                            onClick={() => startEdit(row.repcode_id, c.key, val)}
                          >
                            {val == null || val === '' ? '\u00A0' : String(val)}
                          </div>
                        </td>
                      );
                    })}
                    <td className="repcodes-cell readonly" title={row.modified_by ?? ''}>
                      {row.modified_by ?? ''}
                    </td>
                    <td className="repcodes-cell readonly">
                      {row.modified_at ? row.modified_at.replace('T', ' ').slice(0, 16) : ''}
                    </td>
                    <td className="repcodes-actions">
                      {!isNew && (
                        <button
                          className="repcodes-btn secondary small"
                          type="button"
                          onClick={() => openHistory(row.repcode_id)}
                        >
                          History
                        </button>
                      )}
                      <button
                        className="repcodes-btn danger small"
                        type="button"
                        disabled={saving}
                        onClick={() => void handleDelete(row.repcode_id)}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
              {filteredRows.length === 0 && !loading && (
                <tr>
                  <td colSpan={COLUMNS.length + 4} className="repcodes-empty">
                    No rows match the current filter.
                  </td>
                </tr>
              )}
              {hasMore && (
                <tr>
                  <td colSpan={COLUMNS.length + 4} className="repcodes-more">
                    Loading more… ({visibleRows.length} of {filteredRows.length})
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      {historyRowId !== null && (
        <div className="repcodes-drawer-overlay" onClick={closeHistory}>
          <aside
            className="repcodes-drawer"
            role="dialog"
            aria-label={`Change history for row ${historyRowId}`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="repcodes-drawer-head">
              <div>
                <div className="repcodes-kicker">Change history</div>
                <h2 className="repcodes-drawer-title">Row #{historyRowId}</h2>
              </div>
              <button
                className="repcodes-btn secondary small"
                type="button"
                onClick={closeHistory}
              >
                Close
              </button>
            </div>

            {historyError && <div className="repcodes-banner error">{historyError}</div>}
            {historyLoading && <div className="repcodes-drawer-empty">Loading…</div>}
            {!historyLoading && !historyError && historyRows.length === 0 && (
              <div className="repcodes-drawer-empty">No history recorded for this row.</div>
            )}

            <ol className="repcodes-timeline">
              {historyRows.map((entry, idx) => {
                const older = historyRows[idx + 1];
                const changes = diffEntries(entry, older);
                const isCurrent = idx === 0;
                return (
                  <li key={entry.history_id} className="repcodes-timeline-item">
                    <div className="repcodes-timeline-head">
                      <span className={`repcodes-op-badge ${entry.operation.toLowerCase()}`}>
                        {OP_LABEL[entry.operation] ?? entry.operation}
                      </span>
                      {isCurrent && <span className="repcodes-current-tag">current</span>}
                      <span className="repcodes-timeline-meta">
                        {entry.changed_by ?? 'unknown'} · {fmtTimestamp(entry.changed_at)}
                        {entry.source === 'bulk' && ' · bulk import'}
                      </span>
                    </div>
                    {entry.operation === 'DELETE' ? (
                      <div className="repcodes-timeline-note">Row was deleted.</div>
                    ) : changes.length === 0 ? (
                      <div className="repcodes-timeline-note">No field changes.</div>
                    ) : (
                      <ul className="repcodes-change-list">
                        {changes.map((ch) => (
                          <li key={ch.label}>
                            <span className="repcodes-change-field">{ch.label}</span>
                            <span className="repcodes-change-from">{ch.from}</span>
                            <span className="repcodes-change-arrow">→</span>
                            <span className="repcodes-change-to">{ch.to}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    {!isCurrent && (
                      <button
                        className="repcodes-btn small"
                        type="button"
                        disabled={historyBusy}
                        onClick={() => void handleRestore(historyRowId, entry.history_id)}
                      >
                        Restore this version
                      </button>
                    )}
                  </li>
                );
              })}
            </ol>
          </aside>
        </div>
      )}
    </ToolPage>
  );
};

export default Repcodes;
