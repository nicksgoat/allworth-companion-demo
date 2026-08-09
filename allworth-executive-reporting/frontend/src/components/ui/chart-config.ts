import type { ReactNode } from 'react';

export type ChartConfig = Record<
  string,
  {
    label?: ReactNode;
    color?: string;
  }
>;

export const allworthChartConfig = {
  actual: { label: 'Actual', color: '#0C2E4E' },
  comparison: { label: 'Comparison', color: '#289FDA' },
  positive: { label: 'Positive', color: '#436434' },
  neutral: { label: 'Neutral', color: '#A99C6C' },
  negative: { label: 'Negative', color: '#D26D37' },
  prior: { label: 'Prior period', color: '#BEBEBE' },
} satisfies ChartConfig;
