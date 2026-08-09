import { useMemo } from 'react';
import { formatNumber } from './KpiTile';

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

      <div className="proj-pace__rows">
        {priced.map((r) => {
          const att = r.goal > 0 ? r.projection / r.goal : 0;
          const status = statusOf(att);
          const gap = r.projection - r.goal;
          const projPct = Math.max(0, Math.min(att, 1)) * 100;
          const bookedPct = r.goal > 0 ? Math.max(0, Math.min(r.actual / r.goal, 1)) * 100 : 0;
          const bookedPctOfProj = r.projection > 0 ? Math.round((r.actual / r.projection) * 100) : 0;
          const isTotal = r.channel === 'Total';

          const health =
            status === 'on'
              ? `On track — ${bookedPctOfProj}% of the projection already booked`
              : status === 'watch'
                ? `Watch — pacing to ${Math.round(att * 100)}% of plan, ${fmt(Math.abs(gap), r)} light`
                : `Behind — projecting ${fmt(Math.abs(gap), r)} under plan`;

          return (
            <div
              key={r.channel}
              className={`proj-pace__row proj-pace__row--${status}${isTotal ? ' proj-pace__row--total' : ''}`}
            >
              <div className="proj-pace__label">
                <span className="proj-pace__channel">{r.channel}</span>
                <span className={`proj-pace__status proj-pace__status--${status}`}>{STATUS_LABEL[status]}</span>
                <span className="proj-pace__health">{health}</span>
              </div>

              <div
                className="proj-pace__track"
                title={`Booked ${fmt(r.actual, r)} · projected ${fmt(r.projection, r)} · plan ${fmt(r.goal, r)}`}
              >
                <div className="proj-pace__fill" style={{ width: `${projPct}%` }} />
                <div className="proj-pace__booked" style={{ width: `${bookedPct}%` }}>
                  <span className="proj-pace__booked-val">{fmt(r.actual, r)}</span>
                </div>
                <span
                  className="proj-pace__fill-val"
                  style={{ left: `${Math.min(projPct, 100)}%` }}
                >
                  {fmt(r.projection, r)} proj
                </span>
                <div className="proj-pace__goal" />
              </div>

              <div className="proj-pace__figs">
                <span className="proj-pace__att">{Math.round(att * 100)}%</span>
                <span className={`proj-pace__gap proj-pace__gap--${gap >= 0 ? 'pos' : 'neg'}`}>
                  {gap >= 0 ? '+' : '−'}{fmt(Math.abs(gap), r)} vs plan
                </span>
              </div>
            </div>
          );
        })}
      </div>

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

          <div
            className="proj-pace__diag-bar"
            title="How the month-end projection is built from the model buckets, with actual-to-date and plan markers."
          >
            {(() => {
              const scale = Math.max(diagnosis.projection, diagnosis.plan, diagnosis.actual) || 1;
              const w = (v: number) => `${Math.max(0, (v / scale) * 100)}%`;
              const pos = (v: number) => `${Math.max(0, Math.min((v / scale) * 100, 100))}%`;
              return (
                <>
                  <div className="proj-pace__diag-track">
                    <div className="proj-pace__diag-seg proj-pace__diag-seg--tail" style={{ width: w(diagnosis.a) }} />
                    <div className="proj-pace__diag-seg proj-pace__diag-seg--closed" style={{ width: w(diagnosis.b) }} />
                    {diagnosis.recruiting > 0 && (
                      <div className="proj-pace__diag-seg proj-pace__diag-seg--recruiting" style={{ width: w(diagnosis.recruiting) }} />
                    )}
                    <div className="proj-pace__diag-seg proj-pace__diag-seg--pipeline" style={{ width: w(diagnosis.c) }} />
                  </div>
                  <div className="proj-pace__diag-marker proj-pace__diag-marker--plan" style={{ left: pos(diagnosis.plan) }}>
                    <span className="proj-pace__diag-marker-tag">Plan {fmt(diagnosis.plan, diagnosis.total)}</span>
                  </div>
                  <div className="proj-pace__diag-marker proj-pace__diag-marker--actual" style={{ left: pos(diagnosis.actual) }}>
                    <span className="proj-pace__diag-marker-tag">Actual {fmt(diagnosis.actual, diagnosis.total)}</span>
                  </div>
                </>
              );
            })()}
          </div>

          <div className="proj-pace__diag-legend">
            <span><i className="proj-pace__swatch proj-pace__swatch--tail" />Tail Funding {fmt(diagnosis.a, diagnosis.total)}</span>
            <span><i className="proj-pace__swatch proj-pace__swatch--closed" />Already Closed {fmt(diagnosis.b, diagnosis.total)}</span>
            {diagnosis.recruiting > 0 && (
              <span><i className="proj-pace__swatch proj-pace__swatch--recruiting" />Recruiting {fmt(diagnosis.recruiting, diagnosis.total)}</span>
            )}
            <span><i className="proj-pace__swatch proj-pace__swatch--pipeline" />Active Pipeline {fmt(diagnosis.c, diagnosis.total)}</span>
            <span className="proj-pace__legend-mark proj-pace__legend-mark--actual"><i className="proj-pace__swatch proj-pace__swatch--actual-mark" />Actual marker</span>
            <span className="proj-pace__legend-mark proj-pace__legend-mark--plan"><i className="proj-pace__swatch proj-pace__swatch--plan-mark" />Plan marker</span>
          </div>

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
