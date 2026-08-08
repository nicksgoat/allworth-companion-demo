// KPI summary band — turns the queue from a bare table into a scannable
// dashboard: open items, proposed value, and a status breakdown at a glance.

import type { NfbcRow } from '../types';

function compactMoney(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(n / 1_000_000).toFixed(abs >= 10_000_000 ? 0 : 1)}M`;
  if (abs >= 1_000) return `$${Math.round(n / 1_000)}K`;
  return `$${Math.round(n)}`;
}

interface Stat {
  label: string;
  value: string;
  tone: 'navy' | 'green' | 'amber' | 'red';
  hint?: string;
}

export function QueueSummary({ rows }: { rows: NfbcRow[] }) {
  if (!rows.length) return null;

  const open = rows.filter((r) => r.status !== 'confirmed').length;
  const ready = rows.filter(
    (r) => r.status === 'proposed' && r.avhhid != null && r.amount != null && !!r.period,
  ).length;
  const review = rows.filter(
    (r) => r.status === 'needs_review' || (r.needs_human_flags?.length ?? 0) > 0,
  ).length;
  const resolved = rows.filter((r) => r.status === 'confirmed').length;
  const proposedValue = rows
    .filter((r) => r.status !== 'confirmed' && typeof r.amount === 'number')
    .reduce((sum, r) => sum + (r.amount ?? 0), 0);

  const stats: Stat[] = [
    { label: 'Open items', value: String(open), tone: 'navy' },
    { label: 'Proposed value', value: compactMoney(proposedValue), tone: 'navy' },
    { label: 'Ready to post', value: String(ready), tone: 'green', hint: 'household · amount · period set' },
    { label: 'Needs review', value: String(review), tone: 'amber', hint: 'unresolved or flagged' },
    { label: 'Resolved', value: String(resolved), tone: 'green' },
  ];

  return (
    <div className="nfbc-summary" role="group" aria-label="Queue summary">
      {stats.map((s) => (
        <div key={s.label} className={`nfbc-stat tone-${s.tone}`} title={s.hint}>
          <div className="nfbc-stat-value">{s.value}</div>
          <div className="nfbc-stat-label">{s.label}</div>
        </div>
      ))}
    </div>
  );
}
