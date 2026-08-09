import { useEffect } from 'react';
import {
  CartesianGrid,
  Line,
  LineChart,
  XAxis,
  YAxis,
} from 'recharts';
import { ChartContainer, ChartLegend, ChartTooltip } from './ui/chart';
import type { TrendPoint, TrendTarget } from '../types/kpi';
import { formatNumber } from './KpiTile';
import { chartTheme } from '../theme';

type Props = {
  target: TrendTarget;
  data: TrendPoint[];
  onClose: () => void;
};

// Short month label for the X axis (e.g. "Jan 2026" -> "Jan '26")
const shortPeriod = (period: string) => {
  const parts = period.split(' ');
  if (parts.length === 2 && parts[1].length === 4) {
    return `${parts[0]} '${parts[1].slice(2)}`;
  }
  return period;
};

export function TrendlineModal({ target, data, onClose }: Props) {
  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const format = (value: number) => formatNumber(value, target.currency, target.unit);

  return (
    <div className="trend-modal__overlay" onClick={onClose} role="presentation">
      <div
        className="trend-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`${target.label} trend`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="trend-modal__header">
          <div>
            <div className="trend-modal__kicker">Trendline · last 12 months</div>
            <h2 className="trend-modal__title">{target.label}</h2>
          </div>
          <button type="button" className="trend-modal__close" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        <div className="trend-modal__chart">
          {data.length === 0 ? (
            <p className="trend-modal__empty">No history available for this metric.</p>
          ) : (
            <ChartContainer width="100%" height={340}>
              <LineChart data={data} margin={{ top: 12, right: 24, bottom: 8, left: 8 }}>
                <CartesianGrid stroke={chartTheme.grid} vertical={false} />
                <XAxis
                  dataKey="period"
                  tickFormatter={shortPeriod}
                  tick={{ fontSize: 12 }}
                  stroke={chartTheme.axis}
                />
                <YAxis
                  tickFormatter={(v: number) => format(v)}
                  tick={{ fontSize: 12 }}
                  width={72}
                  stroke={chartTheme.axis}
                />
                <ChartTooltip
                  formatter={(value) => {
                    const num = typeof value === 'number' ? value : Number(value);
                    return Number.isFinite(num) ? format(num) : String(value);
                  }}
                  labelStyle={{ fontWeight: 600 }}
                  contentStyle={chartTheme.tooltip}
                />
                <ChartLegend />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="Actual"
                  stroke={chartTheme.actual}
                  strokeWidth={2.5}
                  dot={{ r: 3 }}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="plan"
                  name="Goal"
                  stroke={chartTheme.neutral}
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="py"
                  name="Prior Year"
                  stroke={chartTheme.positive}
                  strokeWidth={2}
                  dot={{ r: 2.5 }}
                  connectNulls
                />
              </LineChart>
            </ChartContainer>
          )}
        </div>
      </div>
    </div>
  );
}
