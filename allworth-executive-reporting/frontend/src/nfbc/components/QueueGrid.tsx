// Spreadsheet-style queue: one editable row per proposed adjustment.

import type { NfbcRow, EditPatch } from '../types';
import { MoneyCell, TextCell, SelectCell } from './cells';
import { isJiraKey, jiraTicketUrl } from '../jira';

interface Props {
  rows: NfbcRow[];
  selectedRowId: string | null;
  busyRowId: string | null;
  adjustmentTypes: string[];
  onSelect: (rowId: string) => void;
  onEdit: (rowId: string, patch: EditPatch) => void;
  onConfirm: (rowId: string) => void;
}

const statusLabel: Record<string, string> = {
  proposed: 'Proposed',
  needs_review: 'Needs review',
  written_pending_jira: 'Written · Jira pending',
  confirmed: 'Resolved',
  error: 'Error',
};

export function QueueGrid({
  rows, selectedRowId, busyRowId, adjustmentTypes, onSelect, onEdit, onConfirm,
}: Props) {
  return (
    <div className="nfbc-grid-wrap">
      <table className="nfbc-grid">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Household</th>
            <th>Advisor</th>
            <th>Period</th>
            <th className="num">Amount</th>
            <th>Type</th>
            <th>Conf.</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const locked = row.status === 'confirmed';
            const busy = busyRowId === row.row_id;
            const flagged = (row.needs_human_flags?.length ?? 0) > 0;
            // Readiness ("performance") check: a row is pushable only when it has a
            // resolved household, an amount, and a period. Surface WHY it's blocked.
            const missing: string[] = [];
            if (!row.avhhid) missing.push('household');
            if (row.amount == null) missing.push('amount');
            if (!row.period) missing.push('period');
            const ready = missing.length === 0;
            const checkTitle = locked
              ? 'Already resolved'
              : !ready
                ? `Not ready — missing ${missing.join(', ')}`
                : row.status === 'written_pending_jira'
                  ? 'Resume: finish Jira reply + resolve'
                  : `Push adjustment: write ${row.household ?? row.avhhid}, run rollforward, reply on ${row.ticket_key}`;
            return (
              <tr
                key={row.row_id}
                className={[
                  'nfbc-row',
                  `st-${row.status}`,
                  selectedRowId === row.row_id ? 'selected' : '',
                  flagged ? 'flagged' : '',
                ].join(' ')}
                onClick={() => onSelect(row.row_id)}
              >
                <td className="mono" title={row.ticket_summary}>
                  {isJiraKey(row.ticket_key) ? (
                    <a
                      href={jiraTicketUrl(row.ticket_key)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="nfbc-ticket-link"
                      title={`Open ${row.ticket_key} in Jira`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {row.ticket_key}
                    </a>
                  ) : (
                    row.ticket_key
                  )}
                </td>
                <td title={row.rationale || undefined}>{row.household ?? <span className="muted">— unresolved —</span>}</td>
                <td>{row.advisor ?? ''}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <TextCell
                    value={row.period}
                    disabled={locked || busy}
                    placeholder="YYYY-MM-DD"
                    onCommit={(period) => onEdit(row.row_id, { period })}
                  />
                </td>
                <td className="num" onClick={(e) => e.stopPropagation()}>
                  <MoneyCell
                    value={row.amount}
                    disabled={locked || busy}
                    onCommit={(amount) => onEdit(row.row_id, { amount })}
                  />
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <SelectCell
                    value={row.adjustment_type}
                    options={adjustmentTypes}
                    disabled={locked || busy}
                    onCommit={(adjustment_type) => onEdit(row.row_id, { adjustment_type })}
                  />
                </td>
                <td className="num">
                  {row.confidence == null ? (
                    <span className="muted">—</span>
                  ) : (
                    <span
                      className={`nfbc-conf ${row.confidence >= 0.8 ? 'hi' : row.confidence >= 0.5 ? 'mid' : 'lo'}`}
                      title="Model confidence in the household match"
                    >
                      {Math.round(row.confidence * 100)}%
                    </span>
                  )}
                </td>
                <td>
                  <span className={`nfbc-badge st-${row.status}`}>
                    {flagged && row.status !== 'confirmed' ? '⚠ ' : ''}
                    {statusLabel[row.status] ?? row.status}
                  </span>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button
                    className={[
                      'nfbc-check',
                      locked ? 'done' : '',
                      !ready && !locked ? 'blocked' : '',
                      row.status === 'written_pending_jira' ? 'resume' : '',
                    ].join(' ')}
                    disabled={locked || busy || !ready}
                    title={checkTitle}
                    aria-label={checkTitle}
                    onClick={() => onConfirm(row.row_id)}
                  >
                    {busy
                      ? <span className="nfbc-check-spin" />
                      : locked
                        ? '✓'
                        : row.status === 'written_pending_jira'
                          ? '↻'
                          : '✓'}
                  </button>
                </td>
              </tr>
            );
          })}
          {rows.length === 0 && (
            <tr><td colSpan={9} className="nfbc-empty">No open NFBC tickets in the queue.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
