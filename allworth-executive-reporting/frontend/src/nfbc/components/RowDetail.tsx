// Focused 3-pane live view for the selected row: Ticket | Adjustment | Reply.

import { useEffect, useState } from 'react';
import type { NfbcRow } from '../types';
import { Reconciliation } from './Reconciliation';
import { isJiraKey, jiraTicketUrl } from '../jira';

interface Props {
  row: NfbcRow;
  busy: boolean;
  onEditReply: (rowId: string, draft_reply: string) => void;
  onConfirm: (rowId: string) => void;
}

const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

const DETAIL_STATUS: Record<string, string> = {
  proposed: 'Proposed',
  needs_review: 'Needs review',
  written_pending_jira: 'Written · Jira pending',
  confirmed: 'Resolved',
  error: 'Error',
};

// The confirm pipeline, in execution order, mapped to human labels.
const FLOW_STEPS: { key: string; label: string }[] = [
  { key: 'insert', label: 'Written to Synapse' },
  { key: 'jira_comment', label: 'Reply posted to Jira' },
  { key: 'jira_transition', label: 'Ticket moved to Done' },
];

function ProcessFlow({ row }: { row: NfbcRow }) {
  const steps = row.confirm_result?.steps;
  if (!steps) return null;
  return (
    <section className="nfbc-pane nfbc-flow-pane">
      <h3>🔄 Process flow</h3>
      <ol className="nfbc-flow">
        {FLOW_STEPS.map(({ key, label }) => {
          const s = steps[key];
          const state = !s ? 'pending' : s.error ? 'error' : s.done ? 'done' : 'pending';
          const icon = state === 'done' ? '✓' : state === 'error' ? '✕' : '○';
          const extra = s?.already_present
            ? ' (already present)'
            : typeof s?.rows_affected === 'number'
              ? ` (${s.rows_affected} row${s.rows_affected === 1 ? '' : 's'})`
              : '';
          return (
            <li key={key} className={`nfbc-flow-step ${state}`}>
              <span className="nfbc-flow-icon">{icon}</span>
              <span className="nfbc-flow-label">{label}{extra}</span>
              {s?.error ? <span className="nfbc-flow-err">{s.error}</span> : null}
            </li>
          );
        })}
      </ol>
      {(row.confirmed_by || row.confirmed_at) && (
        <p className="nfbc-flow-by">
          Confirmed{row.confirmed_by ? ` by ${row.confirmed_by}` : ''}
          {row.confirmed_at ? ` · ${new Date(row.confirmed_at).toLocaleString()}` : ''}
        </p>
      )}
    </section>
  );
}

export function RowDetail({ row, busy, onEditReply, onConfirm }: Props) {
  const [reply, setReply] = useState(row.draft_reply);
  useEffect(() => setReply(row.draft_reply), [row.row_id, row.draft_reply]);

  const locked = row.status === 'confirmed';
  const cvc = row.computed_vs_claude;

  return (
    <div className="nfbc-detail-wrap">
      <div className="nfbc-detail-head">
        <div className="nfbc-detail-head-main">
          <div className="nfbc-detail-hh">
            {row.household ?? <span className="muted">— unresolved —</span>}
          </div>
          <div className="nfbc-detail-sub">
            {row.advisor || 'No advisor'}{row.avhhid ? ` · #${row.avhhid}` : ''}
          </div>
        </div>
        <div className="nfbc-detail-metrics">
          <div className="nfbc-detail-metric">
            <span>Amount</span><b>{money(row.amount)}</b>
          </div>
          <div className="nfbc-detail-metric">
            <span>Period</span><b>{row.period ?? '—'}</b>
          </div>
          <div className="nfbc-detail-metric">
            <span>Type</span><b>{row.adjustment_type}</b>
          </div>
          <span className={`nfbc-badge st-${row.status}`}>
            {DETAIL_STATUS[row.status] ?? row.status}
          </span>
        </div>
      </div>

      <div className="nfbc-detail">
      {/* Pane 1 — Ticket */}
      <section className="nfbc-pane">
        <h3>🎫 {isJiraKey(row.ticket_key) ? (
          <a href={jiraTicketUrl(row.ticket_key)} target="_blank" rel="noopener noreferrer"
             className="nfbc-ticket-link" title={`Open ${row.ticket_key} in Jira`}>{row.ticket_key}</a>
        ) : row.ticket_key}</h3>
        <p className="nfbc-summary">{row.ticket_summary}</p>
        <div className="nfbc-kv"><span>Household</span><b>{row.household ?? '—'}</b></div>
        <div className="nfbc-kv"><span>avhhid</span><b className="mono">{row.avhhid ?? '—'}</b></div>
        <div className="nfbc-kv"><span>Advisor</span><b>{row.advisor ?? '—'}</b></div>
        {!!row.flows?.length && (
          <>
            <h4>Recent flows</h4>
            <table className="nfbc-mini">
              <thead><tr><th>Period</th><th className="num">In</th><th className="num">Out</th><th className="num">Net</th></tr></thead>
              <tbody>
                {row.flows.slice(-6).map((f) => (
                  <tr key={f.reportingperiod}>
                    <td>{f.reportingperiod}</td>
                    <td className="num">{money(f.inflows)}</td>
                    <td className="num">{money(f.outflows)}</td>
                    <td className="num">{money(f.net_flows)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>

      {/* Pane 2 — Adjustment */}
      <section className="nfbc-pane">
        <h3>🧮 Adjustment</h3>
        <div className="nfbc-kv"><span>Amount</span><b>{money(row.amount)}</b></div>
        <div className="nfbc-kv"><span>Period</span><b>{row.period ?? '—'}</b></div>
        <div className="nfbc-kv"><span>Type</span><b>{row.adjustment_type}</b></div>
        {cvc && cvc.claude_amount != null && (
          <div className="nfbc-note">
            Claude read {money(cvc.claude_amount)}; code computed {money(cvc.code_amount)}.
          </div>
        )}
        {!!row.needs_human_flags?.length && (
          <div className="nfbc-flags">
            {row.needs_human_flags.map((f, i) => <div key={i} className="nfbc-flag">⚠ {f}</div>)}
          </div>
        )}
        {!!row.existing_adjustments?.length && (
          <div className="nfbc-note">
            {row.existing_adjustments.length} existing adjustment(s) on this household.
          </div>
        )}
        {!!row.findings?.length && (
          <ul className="nfbc-findings">
            {row.findings.map((f, i) => (
              <li key={i} className={`fnd-${f.type}`}><b>{f.title}</b> — {f.detail}</li>
            ))}
          </ul>
        )}
        {row.rationale && <p className="nfbc-rationale">{row.rationale}</p>}
      </section>

      {/* Reconciliation — does the adjustment fit the account-value bridge? */}
      <Reconciliation row={row} />

      {/* Pane 3 — Reply */}
      <section className="nfbc-pane">
        <h3>✉️ Jira reply</h3>
        <textarea
          className="nfbc-reply"
          value={reply}
          disabled={locked || busy}
          onChange={(e) => setReply(e.target.value)}
          onBlur={() => { if (reply !== row.draft_reply) onEditReply(row.row_id, reply); }}
          placeholder="Reply that will be posted on the ticket when you confirm…"
        />
        <button
          className="nfbc-confirm-btn lg"
          disabled={locked || busy || !row.avhhid || row.amount == null}
          onClick={() => onConfirm(row.row_id)}
        >
          {locked
            ? '✓ Resolved'
            : busy
              ? 'Working…'
              : row.status === 'written_pending_jira'
                ? 'Resume Jira steps'
                : 'Confirm · write + reply + resolve'}
        </button>
        {row.status === 'confirmed' && (
          <p className="nfbc-done">Adjustment written, reply posted, ticket moved to Done.</p>
        )}
      </section>

      <ProcessFlow row={row} />
    </div>
    </div>
  );
}
