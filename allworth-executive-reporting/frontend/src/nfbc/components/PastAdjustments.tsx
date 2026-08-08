// Always-visible panel of every NFBC adjustment already written to Synapse,
// so past adjustments sit in the same view as the live queue. Loads on mount
// and refreshes after each confirm. Rows made through this tool carry full
// detail (ticket, flows, rationale, posted reply, process-step flow) and are
// clickable to expand it; rows written outside the tool show flat.

import { useMemo, useState } from 'react';
import type { AuditResponse, NfbcRow } from '../types';

type AdjRow = AuditResponse['db_adjustments'][number];

interface Props {
  rows: AdjRow[];
  confirmed: NfbcRow[];
  selectedKey: string | null;
  loading: boolean;
  onRefresh: () => void;
  onSelect: (row: AdjRow, proposal: NfbcRow | null) => void;
}

const money = (v: unknown) => {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? ''));
  return Number.isFinite(n)
    ? n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
    : String(v ?? '');
};

// Match a Synapse row to its full-detail proposal by household + period + amount.
const keyOf = (avhhid: unknown, period: unknown, amount: unknown) =>
  `${String(avhhid ?? '').trim()}|${String(period ?? '').slice(0, 10)}|${Math.round(Number(amount) || 0)}`;

export function PastAdjustments({ rows, confirmed, selectedKey, loading, onRefresh, onSelect }: Props) {
  const [q, setQ] = useState('');

  const byKey = useMemo(() => {
    const m = new Map<string, NfbcRow>();
    for (const p of confirmed) m.set(keyOf(p.avhhid, p.period, p.amount), p);
    return m;
  }, [confirmed]);

  const filtered = useMemo(() => {
    const term = q.trim().toLowerCase();
    if (!term) return rows;
    return rows.filter((r) =>
      [r.avhhid, r.sfhhname, r.sfadvisor, r.reportingperiod, r.adjustment_type]
        .some((v) => String(v ?? '').toLowerCase().includes(term)),
    );
  }, [rows, q]);

  const total = useMemo(
    () => filtered.reduce((s, r) => {
      const n = typeof r.flow_adjustment === 'number'
        ? r.flow_adjustment : parseFloat(String(r.flow_adjustment ?? ''));
      return s + (Number.isFinite(n) ? n : 0);
    }, 0),
    [filtered],
  );

  return (
    <section className="nfbc-past">
      <div className="nfbc-past-head">
        <h3>
          Past adjustments in Synapse
          <span className="nfbc-past-count">{filtered.length}{q ? ` / ${rows.length}` : ''}</span>
        </h3>
        <div className="nfbc-past-tools">
          <input
            className="nfbc-past-search"
            value={q}
            placeholder="Filter household, advisor, period, type…"
            onChange={(e) => setQ(e.target.value)}
          />
          <span className="nfbc-past-total" title="Net of filtered rows">
            net {money(total)}
          </span>
          <button className="nfbc-ghost" onClick={onRefresh} disabled={loading}>
            {loading ? 'Loading…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      <div className="nfbc-past-scroll">
        <table className="nfbc-mini nfbc-past-table">
          <thead>
            <tr>
              <th></th><th>avhhid</th><th>Household</th><th>Advisor</th><th>Period</th>
              <th className="num">Amount</th><th className="num">×</th><th>Type</th><th>Ticket</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a, i) => {
              const prop = byKey.get(keyOf(a.avhhid, a.reportingperiod, a.flow_adjustment)) ?? null;
              const rowKey = keyOf(a.avhhid, a.reportingperiod, a.flow_adjustment);
              const isSel = rowKey === selectedKey;
              return (
                <tr
                  key={`${a.avhhid}-${a.reportingperiod}-${a.flow_adjustment}-${i}`}
                  className={['nfbc-past-clickable', isSel ? 'selected' : ''].join(' ')}
                  onClick={() => onSelect(a, prop)}
                  title="View full detail: flows, existing adjustments, account-value reconciliation"
                >
                  <td className="nfbc-past-chev">{isSel ? '▾' : '▸'}</td>
                  <td className="mono">{String(a.avhhid ?? '')}</td>
                  <td>{String(a.sfhhname ?? '')}</td>
                  <td>{String(a.sfadvisor ?? '')}</td>
                  <td>{String(a.reportingperiod ?? '')}</td>
                  <td className={`num${Number(a.flow_adjustment) < 0 ? ' neg' : ''}`}>{money(a.flow_adjustment)}</td>
                  <td className="num">{String(a.multiplier ?? '')}</td>
                  <td>{String(a.adjustment_type ?? '')}</td>
                  <td className="mono">{prop ? prop.ticket_key : ''}</td>
                </tr>
              );
            })}
            {!loading && filtered.length === 0 && (
              <tr><td colSpan={9} className="nfbc-empty">
                {rows.length === 0 ? 'No adjustments written yet.' : 'No rows match the filter.'}
              </td></tr>
            )}
            {loading && rows.length === 0 && (
              <tr><td colSpan={9} className="nfbc-empty">Loading past adjustments…</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
