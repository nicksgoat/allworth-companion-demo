import { useMemo } from 'react';
import { Bar, BarChart, CartesianGrid, ReferenceLine, XAxis, YAxis } from 'recharts';
import { ChartContainer, ChartLegend, ChartTooltip } from './ui/chart';
import { formatNumber } from './KpiTile';
import { chartPalette, chartTheme } from '../theme';

// One channel's current-month pacing plus its model-bucket composition.
export type ChannelPacing = {
  channel: string;
  actual: number;      // booked month-to-date
  projection: number;  // model EoM projection
  low?: number;        // p25 confidence
  high?: number;       // p75 confidence
  goal: number;        // full-month plan
  // Model-bucket composition of the projection (millions):
  a: number;           // Tail Funding
  b: number;           // Unfunded Closes
  c: number;           // Active Pipeline
  recruiting: number;  // Advisor Recruiting (booked, outside the A/B/C model)
  currency?: string;
  unit?: string;
};

type Props = {
  rows: ChannelPacing[];
  yellowThreshold?: number;   // % of plan below which a channel is "behind"
  asOfLabel?: string;         // e.g. "Jul 2026"
};

type Status = 'on' | 'watch' | 'behind';

const STATUS_LABEL: Record<Status, string> = {
  on: 'On track',
  watch: 'Watch',
  behind: 'Behind',
};

export function ProjectionPanel({ rows, yellowThreshold = 80, asOfLabel }: Props) {
  const priced = useMemo(() => rows.filter((r) => r.goal > 0), [rows]);

  const statusOf = (att: number): Status => {
    if (att >= 1) return 'on';
    if (att >= yellowThreshold / 100) return 'watch';
    return 'behind';
  };

  // Firm-level model-bucket diagnosis. Breaks the projection into the three
  // model buckets (Tail Funding, Already Closed, Active Pipeline) plus booked
  // Recruiting, and compares actual-to-date and projection against plan.
  // Tail Funding + Already Closed + Recruiting are committed; Active Pipeline is
  // the flex bucket, so any shortfall to plan lands there.
  const diagnosis = useMemo(() => {
    const total = priced.find((r) => r.channel === 'Total');
    const channels = priced.filter((r) => r.channel !== 'Total');
    if (!total) return null;

    const a = total.a;                                // Tail Funding
    const b = total.b;                                // Already Closed
    const c = total.c;                                // Active Pipeline
    const recruiting = total.recruiting;              // booked, outside A/B/C
    const actual = total.actual;                      // booked month-to-date
    const projection = total.projection;              // model EoM
    const plan = total.goal;

    const committed = a + b + recruiting;             // locked in
    const gap = projection - plan;                    // negative = short of plan
    const pipelineNeeded = Math.max(0, plan - committed);
    const pipelineGap = c - pipelineNeeded;           // negative = pipeline can't cover
    const actualPct = plan > 0 ? Math.round((actual / plan) * 100) : 0;

    const drags = channels
      .map((r) => ({ channel: r.channel, gap: r.projection - r.goal }))
      .filter((d) => d.gap < 0)
      .sort((x, y) => x.gap - y.gap)
      .slice(0, 2);

    return {
      total, a, b, c, recruiting, actual, projection, plan,
      committed, gap, pipelineNeeded, pipelineGap, actualPct, drags,
    };
  }, [priced]);

  if (priced.length === 0) return null;

  const fmt = (v: number, r: ChannelPacing) => formatNumber(v, r.currency, r.unit);

  return (
    <section className="proj-pace" aria-label="Projected end-of-month attainment by channel">
      <div className="proj-pace__header">
        <div>
          <h2 className="proj-pace__title">Projected End-of-Month Attainment by Channel</h2>
          <p className="proj-pace__subtitle">
            Where the NCNM model expects each channel to finish {asOfLabel ? `${asOfLabel} ` : ''}versus plan.
            The filled bar is the projected end-of-month total; the darker segment is already booked.
          </p>
        </div>
      </div>

      <ChartContainer className="proj-pace__chart" height={Math.max(280, priced.length * 58)}>
        <BarChart data={priced} layout="vertical" margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid horizontal={false} />
          <XAxis type="number" domain={[0, 'dataMax']} tickFormatter={(value) => fmt(Number(value), priced[0])} tickLine={false} axisLine={false} />
          <YAxis type="category" dataKey="channel" width={116} tickLine={false} axisLine={false} />
          <ChartTooltip
            labelFormatter={(label) => {
              const row = priced.find((item) => item.channel === label);
              if (!row) return String(label);
              const attainment = row.goal > 0 ? row.projection / row.goal : 0;
              return `${String(label)} · ${STATUS_LABEL[statusOf(attainment)]} · ${Math.round(attainment * 100)}%`;
            }}
            formatter={(value, name) => [fmt(Number(value), priced[0]), String(name)]}
          />
          <ChartLegend />
          <Bar dataKey="actual" name="Actual booked" fill={chartTheme.actual} radius={[0, 3, 3, 0]} isAnimationActive={false} />
          <Bar dataKey="projection" name="Projected EoM" fill={chartTheme.comparison} radius={[0, 3, 3, 0]} isAnimationActive={false} />
          <Bar dataKey="goal" name="Plan" fill={chartTheme.prior} radius={[0, 3, 3, 0]} isAnimationActive={false} />
        </BarChart>
      </ChartContainer>

      {diagnosis && (
        <div className="proj-pace__diagnosis">
          <div className="proj-pace__diag-head">
            <span className="proj-pace__diag-kicker">Diagnosis</span>
            <span className={`proj-pace__diag-verdict proj-pace__diag-verdict--${diagnosis.gap >= 0 ? 'pos' : 'neg'}`}>
              {diagnosis.gap >= 0
                ? `On track — projected ${fmt(diagnosis.gap, diagnosis.total)} above plan`
                : `Off track — projected ${fmt(Math.abs(diagnosis.gap), diagnosis.total)} short of plan`}
            </span>
          </div>

          <div className="proj-pace__diag-stats">
            <div className="proj-pace__diag-stat">
              <span className="proj-pace__diag-stat-label">Actual to date</span>
              <span className="proj-pace__diag-stat-value">{fmt(diagnosis.actual, diagnosis.total)}</span>
              <span className="proj-pace__diag-stat-sub">{diagnosis.actualPct}% of plan</span>
            </div>
            <div className="proj-pace__diag-stat">
              <span className="proj-pace__diag-stat-label">Projected EoM</span>
              <span className="proj-pace__diag-stat-value">{fmt(diagnosis.projection, diagnosis.total)}</span>
              <span className={`proj-pace__diag-stat-sub proj-pace__diag-stat-sub--${diagnosis.gap >= 0 ? 'pos' : 'neg'}`}>
                {diagnosis.gap >= 0 ? '+' : '−'}{fmt(Math.abs(diagnosis.gap), diagnosis.total)} vs plan
              </span>
            </div>
            <div className="proj-pace__diag-stat">
              <span className="proj-pace__diag-stat-label">Plan</span>
              <span className="proj-pace__diag-stat-value">{fmt(diagnosis.plan, diagnosis.total)}</span>
              <span className="proj-pace__diag-stat-sub">target</span>
            </div>
          </div>

          <ChartContainer className="proj-pace__diagnosis-chart" height={120}>
            <BarChart
              data={[{
                label: 'Projected EoM',
                tail: diagnosis.a,
                closed: diagnosis.b,
                recruiting: diagnosis.recruiting,
                pipeline: diagnosis.c,
              }]}
              layout="vertical"
              margin={{ top: 22, right: 20, bottom: 8, left: 8 }}
            >
              <XAxis type="number" domain={[0, 'dataMax']} tickFormatter={(value) => fmt(Number(value), diagnosis.total)} tickLine={false} axisLine={false} />
              <YAxis type="category" dataKey="label" width={108} tickLine={false} axisLine={false} />
              <ChartTooltip formatter={(value, name) => [fmt(Number(value), diagnosis.total), String(name)]} />
              <ChartLegend />
              <ReferenceLine x={diagnosis.plan} stroke={chartTheme.warning} strokeDasharray="4 3" label={{ value: 'Plan', fill: chartTheme.warning, fontSize: 11 }} />
              <ReferenceLine x={diagnosis.actual} stroke={chartTheme.actual} strokeDasharray="2 2" label={{ value: 'Actual', fill: chartTheme.actual, fontSize: 11 }} />
              <Bar dataKey="tail" name="Tail Funding" stackId="projection" fill={chartPalette[0]} isAnimationActive={false} />
              <Bar dataKey="closed" name="Already Closed" stackId="projection" fill={chartPalette[1]} isAnimationActive={false} />
              {diagnosis.recruiting > 0 && <Bar dataKey="recruiting" name="Recruiting" stackId="projection" fill={chartPalette[2]} isAnimationActive={false} />}
              <Bar dataKey="pipeline" name="Active Pipeline" stackId="projection" fill={chartPalette[3]} radius={[0, 4, 4, 0]} isAnimationActive={false} />
            </BarChart>
          </ChartContainer>

          <p className="proj-pace__diag-text">
            {diagnosis.gap >= 0 ? (
              <>
                Actual booked to date is <strong>{fmt(diagnosis.actual, diagnosis.total)}</strong> ({diagnosis.actualPct}% of plan).
                The model projects <strong>{fmt(diagnosis.projection, diagnosis.total)}</strong> by month-end,{' '}
                <strong>{fmt(diagnosis.gap, diagnosis.total)}</strong> above the {fmt(diagnosis.plan, diagnosis.total)} plan.
                Committed buckets — Tail Funding ({fmt(diagnosis.a, diagnosis.total)}) and Already Closed ({fmt(diagnosis.b, diagnosis.total)})
                {diagnosis.recruiting > 0 ? ` plus Recruiting (${fmt(diagnosis.recruiting, diagnosis.total)})` : ''} — supply{' '}
                <strong>{fmt(diagnosis.committed, diagnosis.total)}</strong>, and Active Pipeline is expected to add{' '}
                <strong>{fmt(diagnosis.c, diagnosis.total)}</strong>. All three buckets are pacing to clear plan.
              </>
            ) : (
              <>
                Actual booked to date is <strong>{fmt(diagnosis.actual, diagnosis.total)}</strong> ({diagnosis.actualPct}% of plan).
                The model projects <strong>{fmt(diagnosis.projection, diagnosis.total)}</strong> by month-end,{' '}
                <strong>{fmt(Math.abs(diagnosis.gap), diagnosis.total)}</strong> short of the {fmt(diagnosis.plan, diagnosis.total)} plan.
                Tail Funding ({fmt(diagnosis.a, diagnosis.total)}) and Already Closed ({fmt(diagnosis.b, diagnosis.total)})
                {diagnosis.recruiting > 0 ? ` plus Recruiting (${fmt(diagnosis.recruiting, diagnosis.total)})` : ''} are committed and total{' '}
                <strong>{fmt(diagnosis.committed, diagnosis.total)}</strong>, so <strong>{fmt(diagnosis.pipelineNeeded, diagnosis.total)}</strong>{' '}
                must come from <strong>Active Pipeline</strong> to reach plan. Active Pipeline only projects{' '}
                <strong>{fmt(diagnosis.c, diagnosis.total)}</strong> — a <strong>{fmt(Math.abs(diagnosis.pipelineGap), diagnosis.total)}</strong> shortfall —
                so it is the bucket holding the firm back: more late-stage conversion is needed this month.
                {diagnosis.drags.length > 0 && (
                  <> Biggest channel drags: {diagnosis.drags.map((d) => `${d.channel} (${fmt(d.gap, diagnosis.total)})`).join(', ')}.</>
                )}
              </>
            )}
          </p>

          <div
            className="proj-pace__diag-channels"
            style={{ ['--proj-chan-cols' as string]: diagnosis.recruiting > 0 ? 5 : 4 }}
          >
            <div className="proj-pace__diag-chan-head">
              <span>Channel</span>
              <span>Tail Funding</span>
              <span>Already Closed</span>
              {diagnosis.recruiting > 0 && <span>Recruiting</span>}
              <span>Active Pipeline</span>
              <span>Proj vs plan</span>
            </div>
            {priced.filter((r) => r.channel !== 'Total').map((r) => {
              const att = r.goal > 0 ? r.projection / r.goal : 0;
              const cs = statusOf(att);
              const cgap = r.projection - r.goal;
              return (
                <div key={r.channel} className={`proj-pace__diag-chan-row proj-pace__diag-chan-row--${cs}`}>
                  <span className="proj-pace__diag-chan-name">
                    <i className={`proj-pace__dot proj-pace__dot--${cs}`} />{r.channel}
                  </span>
                  <span>{fmt(r.a, r)}</span>
                  <span>{fmt(r.b, r)}</span>
                  {diagnosis.recruiting > 0 && <span>{r.recruiting > 0 ? fmt(r.recruiting, r) : '—'}</span>}
                  <span>{fmt(r.c, r)}</span>
                  <span className={`proj-pace__diag-chan-gap proj-pace__diag-chan-gap--${cgap >= 0 ? 'pos' : 'neg'}`}>
                    {cgap >= 0 ? '+' : '−'}{fmt(Math.abs(cgap), r)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
