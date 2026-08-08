export type KpiEntry = {
  id: string;
  metric: string;
  channel: string;
  channelMiddle?: string;   // Granular channel (e.g., 'Referral', 'Promoter' within 'Advisor Enabled')
  period: string;
  actual: number;
  goal: number;
  pyActual?: number;        // Previous Year actual (full month)
  pyProrated?: number;      // Previous Year actual (prorated for current month)
  goalProrated?: number;    // Goal prorated for current month
  target?: number;
  budget?: number;
  currency?: string;
  unit?: string;
  periodLabel?: string;
};

export type KpiDataset = KpiEntry[];

// Identifies a single metric/channel series for the trendline popup
export type TrendTarget = {
  metric: string;
  channel: string;
  channelMiddle?: string;
  label: string;
  currency?: string;
  unit?: string;
};

// A single month's point on the trendline chart
export type TrendPoint = {
  period: string;
  actual: number;
  plan: number | null;
  py: number | null;
};

// Detailed metrics with channel_middle granularity
export type DetailedKpiEntry = KpiEntry & {
  channelMiddle: string;
};
