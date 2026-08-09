// Account-value reconciliation for a proposed adjustment.
//
// Proves the adjustment reclassifies a *real* flow and stays inside the
// account-value bridge — it must not invent movement the account never had:
//
//     Beginning Account Value + Net Flows + Market Change = Ending Account Value
//
// That identity closes regardless of any NFBC adjustment (an adjustment is a
// comp-attribution overlay, not a restatement of the account). The verdict
// flags when a proposed amount has no matching flow / account-value movement
// in its period (e.g. a broken-feed phantom outflow) vs. when it's backed by
// a real flow that genuinely moved the account.

import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, XAxis, YAxis } from 'recharts';
import { ChartContainer, ChartTooltip } from '../../components/ui/chart';
import { chartTheme } from '../../theme';
import type { NfbcRow, FlowPeriod } from '../types';

const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

const signed = (n: number | null | undefined) =>
  n == null
    ? '—'
    : (n >= 0 ? '+' : '−') +
      Math.abs(n).toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });

interface PeriodRecon {
  period: string;
  bop: number | null;
  inflows: number;
  outflows: number;
  net: number;
  market: number | null;
  eop: number | null;
}

// Each period's Ending Account Value is total_aum; Beginning is the prior
// period's Ending; Market Change is the balancing plug so the identity holds.
function buildSeries(flows: FlowPeriod[]): PeriodRecon[] {
  return flows.map((f, i) => {
    const eop = f.total_aum;
    const bop = i > 0 ? flows[i - 1].total_aum : null;
    const net = f.net_flows ?? 0;
    const market = bop != null && eop != null ? eop - bop - net : null;
    return { period: f.reportingperiod, bop, inflows: f.inflows ?? 0, outflows: f.outflows ?? 0, net, market, eop };
  });
}

type Verdict = { kind: 'ok' | 'warn' | 'info'; label: string; detail: string };

function assess(target: PeriodRecon, adj: number, existingInPeriod: number): Verdict {
  const gross = Math.abs(target.inflows) + Math.abs(target.outflows);
  const avChange = target.bop != null && target.eop != null ? target.eop - target.bop : null;
  const mag = Math.abs(adj);

  if (mag < 1) return { kind: 'info', label: 'No adjustment', detail: 'Nothing to reconcile.' };

  if (existingInPeriod !== 0 && Math.abs(existingInPeriod) >= mag * 0.5) {
    return {
      kind: 'warn',
      label: 'Possible double-count',
      detail: `${money(existingInPeriod)} of adjustments already exist in this period — writing ${signed(adj)} on top may double-count.`,
    };
  }

  // Backed: the flow being credited/reversed actually occurred in the period.
  if (gross >= mag * 0.9) {
    return {
      kind: 'ok',
      label: 'Backed by real flow',
      detail: `Period gross flow ${money(gross)} covers the ${signed(adj)} adjustment — it reclassifies a real movement, not a phantom one.`,
    };
  }

  // Phantom: no flow and no account-value movement to support it.
  if (avChange != null && Math.abs(avChange) < mag * 0.5) {
    return {
      kind: 'warn',
      label: 'Not backed by account movement',
      detail: `Period gross flow is only ${money(gross)} and account value moved ${signed(avChange)} — nothing supports a ${signed(adj)} adjustment. Verify before writing (likely a feed/reporting artifact).`,
    };
  }

  return {
    kind: 'warn',
    label: 'Partially backed — verify',
    detail: `Adjustment ${signed(adj)} exceeds the period's gross flow of ${money(gross)}. Confirm the amount.`,
  };
}

export function Reconciliation({ row }: { row: NfbcRow }) {
  const flows = row.flows ?? [];

  if (flows.length < 2) {
    return (
      <section className="nfbc-pane nfbc-recon">
        <h3>📊 Account-value reconciliation</h3>
        <p className="nfbc-recon-empty">
          Not enough flow history to reconcile (need at least two periods of account value).
        </p>
      </section>
    );
  }

  const series = buildSeries(flows);
  // Match the adjustment period to its flow row by MONTH, not exact date: NFBC
  // adjustment periods are always month-end (e.g. 2026-07-31), but the current
  // open-month rollforward snapshot is dated mid-month (e.g. 2026-07-24) until
  // month-end close. If the adjustment month isn't loaded yet at all (a future /
  // just-closed month not in the rollforward), reconcile against the most recent
  // available period so there's always a bridge — flagged clearly below.
  const targetMonth = row.period ? row.period.slice(0, 7) : null;
  let idx = targetMonth ? series.findIndex((s) => (s.period || '').slice(0, 7) === targetMonth) : -1;
  const exactMonth = idx >= 0;
  if (idx < 0 && targetMonth && series.length) idx = series.length - 1;
  const target = idx >= 0 ? series[idx] : null;
  const adj = row.amount ?? 0;
  const existingInPeriod = (row.existing_adjustments ?? [])
    .filter((a) => (a.reportingperiod || '').slice(0, 7) === (row.period || '').slice(0, 7))
    .reduce((s, a) => s + (a.flow_adjustment ?? 0), 0);

  const verdict = target ? assess(target, adj, existingInPeriod) : null;
  const adjustedNet = target ? target.net + adj : null;
  const avChange = target && target.bop != null && target.eop != null ? target.eop - target.bop : null;
  const bridge = target ? [
    { label: 'Beginning account value', value: target.bop ?? 0, fill: chartTheme.actual },
    { label: 'Net flows (blanket)', value: target.net, fill: target.net >= 0 ? chartTheme.positive : chartTheme.warning },
    { label: 'Market change', value: target.market ?? 0, fill: (target.market ?? 0) >= 0 ? chartTheme.positive : chartTheme.warning },
    { label: 'Ending account value', value: target.eop ?? 0, fill: chartTheme.actual },
  ] : [];

  return (
    <section className="nfbc-pane nfbc-recon">
      <h3>📊 Account-value reconciliation</h3>

      {!target ? (
        <p className="nfbc-recon-empty">
          {row.period
            ? <>Period <b>{row.period}</b> can't be reconciled — no account-value history for this household yet.</>
            : <>No adjustment period set — pick a period to reconcile.</>}
        </p>
      ) : (
        <>
          {verdict && (
            <div className={`nfbc-recon-verdict v-${verdict.kind}`}>
              <span className="nfbc-recon-chip">{verdict.kind === 'ok' ? '✓' : verdict.kind === 'warn' ? '⚠' : 'ℹ'} {verdict.label}</span>
              <span className="nfbc-recon-verdict-detail">{verdict.detail}</span>
            </div>
          )}

          {/* Bridge for the adjustment period: BoP → Net Flows → Market → EoP */}
          <div className="nfbc-recon-sub">
            Bridge for {row.period}
            {exactMonth && target.period !== row.period && (
              <span className="nfbc-recon-note"> · open-month snapshot as of {target.period} (not yet closed)</span>
            )}
            {!exactMonth && (
              <span className="nfbc-recon-note"> · {row.period} not yet in the rollforward — reconciled against latest available {target.period}</span>
            )}
          </div>
          <ChartContainer className="nfbc-recon-bridge-chart" height={210}>
            <BarChart data={bridge} layout="vertical" margin={{ top: 8, right: 88, bottom: 4, left: 8 }}>
              <CartesianGrid horizontal={false} />
              <XAxis type="number" tickFormatter={(value) => money(Number(value))} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="label" width={148} tickLine={false} axisLine={false} />
              <ReferenceLine x={0} stroke={chartTheme.axis} />
              <ChartTooltip formatter={(value) => [signed(Number(value)), 'Value']} />
              <Bar dataKey="value" name="Value" radius={[0, 4, 4, 0]} minPointSize={2} isAnimationActive={false}>
                {bridge.map((step) => <Cell key={step.label} fill={step.fill} />)}
                <LabelList dataKey="value" position="right" formatter={(value) => signed(Number(value))} fill={chartTheme.axis} fontSize={11} />
              </Bar>
            </BarChart>
          </ChartContainer>

          {/* Comp overlay — adjusted net flows vs. what actually moved the account */}
          <div className="nfbc-recon-overlay">
            <div className="nfbc-kv"><span>Blanket net flows</span><b>{signed(target.net)}</b></div>
            <div className="nfbc-kv"><span>Proposed adjustment ({row.adjustment_type})</span><b>{signed(adj)}</b></div>
            <div className="nfbc-kv"><span>Adjusted net flows (for comp)</span><b>{signed(adjustedNet)}</b></div>
            <div className="nfbc-kv"><span>Account-value change (EoP − BoP)</span><b>{signed(avChange)}</b></div>
            {existingInPeriod !== 0 && (
              <div className="nfbc-kv"><span>Existing adjustments this period</span><b>{signed(existingInPeriod)}</b></div>
            )}
          </div>

          {/* Full window — each month's identity holds, independent of the overlay */}
          <div className="nfbc-recon-sub">Per-period bridge (net flows never override account-value change)</div>
          <div className="nfbc-recon-table-wrap">
            <table className="nfbc-mini nfbc-recon-table">
              <thead>
                <tr>
                  <th>Period</th>
                  <th className="num">Begin AV</th>
                  <th className="num">Net flows</th>
                  <th className="num">Market</th>
                  <th className="num">End AV</th>
                </tr>
              </thead>
              <tbody>
                {series.map((s) => (
                  <tr key={s.period} className={s.period === target.period ? 'nfbc-recon-hl' : undefined}>
                    <td>{s.period}</td>
                    <td className="num">{money(s.bop)}</td>
                    <td className="num">{signed(s.net)}</td>
                    <td className="num">{signed(s.market)}</td>
                    <td className="num">{money(s.eop)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
