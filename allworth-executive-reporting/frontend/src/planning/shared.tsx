export const money = (value: unknown, compact = false) => new Intl.NumberFormat('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0, notation: compact ? 'compact' : 'standard',
}).format(Number(value || 0));

export const pct = (value: unknown, digits = 0) => `${(Number(value || 0) * 100).toFixed(digits)}%`;

export function Kpi({ label, value, tone }: { label: string; value: string; tone?: 'gain' | 'loss' }) {
  return <div className="plan-kpi"><p className="plan-kpi__label">{label}</p>
    <p className={`plan-kpi__value${tone ? ` plan-kpi__value--${tone}` : ''}`}>{value}</p></div>;
}

/* Brand chart palette (theme.ts chartPalette) */
export const chartColors = {
  nightBlue: colors.chartNightBlue,
  sky: colors.chartSky,
  evergreen: colors.chartEvergreen,
  gold: colors.chartGold,
  pumpkin: colors.chartPumpkin,
  lightGray: colors.chartLightGray,
};
import { colors } from '../theme';
