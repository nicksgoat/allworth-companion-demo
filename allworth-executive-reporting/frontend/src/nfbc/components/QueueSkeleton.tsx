// Loading state for the NFBC queue: a determinate progress bar driven by the
// backend's async build progress, over ghost (skeleton) rows so the grid shape
// is visible while Jira + Claude + Synapse analysis runs per ticket.

import type { BuildProgress } from '../types';

interface Props {
  progress: BuildProgress | null | undefined;
  rowCount?: number;
}

const GHOST_COLS = ['ticket', 'hh', 'adv', 'period', 'amount', 'type', 'conf', 'status', 'action'];

export function QueueSkeleton({ progress, rowCount = 6 }: Props) {
  const total = progress?.total ?? 0;
  const done = progress?.done ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : null;
  const ghostRows = Math.max(rowCount, total || 0, 4);

  return (
    <div className="nfbc-skeleton" role="status" aria-live="polite">
      <div className="nfbc-progress">
        <div className="nfbc-progress-head">
          <span className="nfbc-progress-label">
            {total > 0
              ? <>Analyzing ticket <b>{done}</b> of <b>{total}</b>
                  {progress?.current ? <> — <span className="mono">{progress.current}</span></> : null}</>
              : 'Fetching open NFBC tickets from Jira…'}
          </span>
          {pct != null && <span className="nfbc-progress-pct">{pct}%</span>}
        </div>
        <div className="nfbc-progress-track">
          <div
            className={`nfbc-progress-fill${pct == null ? ' indeterminate' : ''}`}
            style={pct == null ? undefined : { width: `${pct}%` }}
          />
        </div>
        <p className="nfbc-progress-hint">
          Each ticket runs Jira lookup, Claude analysis, and Synapse flow checks —
          this can take a moment on a cold start. Results stream in as they finish.
        </p>
      </div>

      <div className="nfbc-grid-wrap" aria-hidden="true">
        <table className="nfbc-grid nfbc-grid-ghost">
          <thead>
            <tr>
              <th>Ticket</th><th>Household</th><th>Advisor</th><th>Period</th>
              <th className="num">Amount</th><th>Type</th><th>Conf.</th><th>Status</th><th></th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: ghostRows }).map((_, i) => (
              <tr key={i} className="nfbc-ghost-row">
                {GHOST_COLS.map((c) => (
                  <td key={c} className={c === 'amount' || c === 'conf' ? 'num' : ''}>
                    <span className={`nfbc-ghost-bar ghost-${c}`} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
