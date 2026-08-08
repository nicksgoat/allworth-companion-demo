import { useEffect } from 'react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TrendPoint, TrendTarget } from '../types/kpi';
import { formatNumber } from './KpiTile';

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

// Custom dot for the Actual line. The current (partial) month renders the
// model's projected EoM value, so its dot is a distinct amber ring with a
// "Projected" label instead of the usual small blue dot.
const renderActualDot = (props: {
  cx?: number;
  cy?: number;
  index?: number;
  payload?: TrendPoint;
}) => {
  const { cx, cy, index, payload } = props;
  if (cx == null || cy == null) return <g key={`ad-${index}`} />;
  if (payload?.projected) {
    return (
      <g key={`ad-${index}`}>
        <circle cx={cx} cy={cy} r={10} fill="#f59e0b" fillOpacity={0.16} />
        <circle cx={cx} cy={cy} r={5.5} fill="#ffffff" stroke="#f59e0b" strokeWidth={2.5} />
        <circle cx={cx} cy={cy} r={2} fill="#b45309" />
        <text
          x={cx}
          y={cy - 14}
          textAnchor="middle"
          fontSize={11}
          fontWeight={700}
          fill="#b45309"
        >
          Projected
        </text>
      </g>
    );
  }
  return <circle key={`ad-${index}`} cx={cx} cy={cy} r={3} fill="#2563eb" />;
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
            <ResponsiveContainer width="100%" height={340}>
              <LineChart data={data} margin={{ top: 12, right: 24, bottom: 8, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--ts-border, #e5e7eb)" vertical={false} />
                <XAxis
                  dataKey="period"
                  tickFormatter={shortPeriod}
                  tick={{ fontSize: 12 }}
                  stroke="var(--ts-text-secondary, #6b7280)"
                />
                <YAxis
                  tickFormatter={(v: number) => format(v)}
                  tick={{ fontSize: 12 }}
                  width={72}
                  stroke="var(--ts-text-secondary, #6b7280)"
                />
                <Tooltip
                  formatter={(value, name, item) => {
                    const num = typeof value === 'number' ? value : Number(value);
                    const formatted = Number.isFinite(num) ? format(num) : String(value);
                    const projected = (item?.payload as TrendPoint | undefined)?.projected;
                    const label = projected && name === 'Actual' ? 'Projected (EoM)' : name;
                    return [formatted, label];
                  }}
                  labelStyle={{ fontWeight: 600 }}
                  contentStyle={{ borderRadius: 8, fontSize: 13 }}
                />
                <Legend />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="Actual"
                  stroke="#2563eb"
                  strokeWidth={2.5}
                  dot={renderActualDot}
                  activeDot={{ r: 5 }}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="plan"
                  name="Goal"
                  stroke="#9ca3af"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  connectNulls
                />
                <Line
                  type="monotone"
                  dataKey="py"
                  name="Prior Year"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={{ r: 2.5 }}
                  connectNulls
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    </div>
  );
}
