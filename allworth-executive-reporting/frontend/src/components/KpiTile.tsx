import type { KpiEntry, TrendTarget } from '../types/kpi';

export const formatNumber = (value: number, currency?: string, unit?: string) => {
  if (Number.isNaN(value)) return '—';
  
  // Helper to format with 1 decimal or none if whole
  const formatWithOptionalDecimal = (num: number) => {
    const hasDecimal = num % 1 !== 0;
    return new Intl.NumberFormat(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: hasDecimal ? 1 : 0
    }).format(num);
  };
  
  if (unit === 'percent') {
    const hasDecimal = value % 1 !== 0;
    return `${hasDecimal ? value.toFixed(1) : Math.round(value)}%`;
  }
  if (unit === 'millions') {
    const prefix = currency === 'USD' ? '$' : '';
    return `${prefix}${formatWithOptionalDecimal(value)}m`;
  }
  if (currency) {
    const hasDecimal = value % 1 !== 0;
    const formatter = new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      minimumFractionDigits: 0,
      maximumFractionDigits: hasDecimal ? 1 : 0
    });
    return formatter.format(value);
  }
  return formatWithOptionalDecimal(value);
};

type Props = {
  entry?: KpiEntry;
  isTotal?: boolean;
  title?: string;
  compact?: boolean;
  yellowThreshold?: number;
  onShowTrendline?: (target: TrendTarget, anchor: { x: number; y: number }) => void;
  // Current-month EoM projection (same unit/currency as the tile). When set, a
  // "Proj" figure renders to the right of the actual. Tile coloring is unchanged.
  projection?: number;
  projectionLow?: number;
  projectionHigh?: number;
};

export function KpiTile({ entry, isTotal = false, title, compact = false, yellowThreshold = 80, onShowTrendline, projection, projectionLow, projectionHigh }: Props) {
  if (!entry) {
    return (
      <div className={`kpi-tile kpi-tile--empty ${isTotal ? 'kpi-tile--total' : ''} ${compact ? 'kpi-tile--compact' : ''}`}>
        {title && <div className="kpi-tile__title">{title}</div>}
        <span className="kpi-tile__no-data">—</span>
      </div>
    );
  }

  const handleContextMenu = onShowTrendline
    ? (e: React.MouseEvent) => {
        e.preventDefault();
        onShowTrendline(
          {
            metric: entry.metric,
            channel: entry.channel,
            channelMiddle: entry.channelMiddle,
            label: entry.channelMiddle
              ? `${entry.metric} · ${entry.channelMiddle}`
              : title ?? `${entry.metric} · ${entry.channel}`,
            currency: entry.currency,
            unit: entry.unit,
          },
          { x: e.clientX, y: e.clientY },
        );
      }
    : undefined;

  const unit = entry.unit ?? (entry.metric.toLowerCase().includes('rate') ? 'percent' : undefined);
  
  // Use prorated values for current month, full values otherwise
  const pyValue = entry.pyProrated ?? entry.pyActual ?? 0;
  const planValue = entry.goalProrated ?? entry.goal ?? 0;
  
  // Metrics where negative values closer to zero are better (less outflow = good)
  const isNegativeMetric = ['Distributions', 'Attrition'].includes(entry.metric);
  
  // Determine status based on comparison to plan
  const getStatusClass = () => {
    if (planValue === 0) return ''; // No goal to compare against
    
    if (isNegativeMetric) {
      // For negative metrics (Distributions, Attrition): closer to zero is better
      // Green: actual >= plan (less negative, closer to zero)
      // Yellow: actual is within threshold% of plan
      // Red: actual is more negative than threshold% of plan
      const actualAbs = Math.abs(entry.actual);
      const planAbs = Math.abs(planValue);
      
      if (actualAbs <= planAbs) return 'kpi-tile--on-track'; // Green: less outflow than planned
      const percentage = (planAbs / actualAbs) * 100;
      if (percentage >= yellowThreshold) return 'kpi-tile--near-goal'; // Yellow: within threshold
      return 'kpi-tile--off-track'; // Red: significantly more outflow than planned
    }
    
    // For positive metrics: higher is better
    // Green: >= goal, Yellow: >= threshold% of goal, Red: below threshold%
    const percentage = (entry.actual / planValue) * 100;
    if (percentage >= 100) return 'kpi-tile--on-track'; // Green: >= 100%
    if (percentage >= yellowThreshold) return 'kpi-tile--near-goal'; // Yellow: >= threshold%
    return 'kpi-tile--off-track'; // Red: < threshold%
  };

  // Projection status is judged against the FULL-month plan (a full-month
  // projection vs the prorated plan would be apples-to-oranges), matching the
  // projection panel below the matrix so both visuals tell the same story.
  const fullPlan = entry.goal ?? 0;
  const getProjStatusClass = () => {
    if (projection === undefined || fullPlan === 0) return '';
    if (isNegativeMetric) {
      const projAbs = Math.abs(projection);
      const planAbs = Math.abs(fullPlan);
      if (projAbs <= planAbs) return 'kpi-tile__proj--on-track';
      const pct = (planAbs / projAbs) * 100;
      return pct >= yellowThreshold ? 'kpi-tile__proj--near-goal' : 'kpi-tile__proj--off-track';
    }
    const pct = (projection / fullPlan) * 100;
    if (pct >= 100) return 'kpi-tile__proj--on-track';
    if (pct >= yellowThreshold) return 'kpi-tile__proj--near-goal';
    return 'kpi-tile__proj--off-track';
  };

  return (
    <div
      className={`kpi-tile ${isTotal ? 'kpi-tile--total' : ''} ${compact ? 'kpi-tile--compact' : ''} ${getStatusClass()}`}
      onContextMenu={handleContextMenu}
    >
      {title && !compact && <div className="kpi-tile__title">{title}</div>}
      <div className="kpi-tile__actual-row">
        <div className="kpi-tile__actual">
          {formatNumber(entry.actual, entry.currency, unit)}
        </div>
      </div>
      <div className="kpi-tile__comparisons">
        <span className="kpi-tile__py">
          <span className="kpi-tile__label">PY</span>
          <span className="kpi-tile__value">{formatNumber(pyValue, entry.currency, unit)}</span>
        </span>
        <span className="kpi-tile__plan">
          <span className="kpi-tile__label">Plan</span>
          <span className="kpi-tile__value">{formatNumber(planValue, entry.currency, unit)}</span>
        </span>
        {projection !== undefined && (
          <span
            className={`kpi-tile__proj ${getProjStatusClass()}`}
            title={
              (projectionLow !== undefined && projectionHigh !== undefined
                ? `Projected end-of-month: ${formatNumber(projection, entry.currency, unit)} (range ${formatNumber(projectionLow, entry.currency, unit)} – ${formatNumber(projectionHigh, entry.currency, unit)})`
                : `Projected end-of-month: ${formatNumber(projection, entry.currency, unit)}`)
              + (fullPlan ? ` · vs full-month plan ${formatNumber(fullPlan, entry.currency, unit)}` : '')
            }
          >
            <span className="kpi-tile__label">Proj</span>
            <span className="kpi-tile__value">{formatNumber(projection, entry.currency, unit)}</span>
          </span>
        )}
      </div>
    </div>
  );
}
