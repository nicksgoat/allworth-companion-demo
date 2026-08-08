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
  // True when `actual` holds the model's projected EoM value for the current
  // (partial) month rather than the booked-so-far actual.
  projected?: boolean;
};

// Detailed metrics with channel_middle granularity
export type DetailedKpiEntry = KpiEntry & {
  channelMiddle: string;
};

// A single current-month EoM prediction (millions), with an optional band.
export type ChannelProjection = {
  projection: number;
  low?: number;
  high?: number;
};

// Model-bucket composition of a channel's projection (millions):
// a = Tail Funding, b = Unfunded Closes, c = Active Pipeline, recruiting =
// Advisor Recruiting NCNM booked (outside the A/B/C model, counted as committed).
export type ChannelComponents = {
  a: number;
  b: number;
  c: number;
  recruiting: number;
};

// Current-month predictions payload from /api/all-metrics ("predictions" key).
// grid_ncnm is keyed by display channel (Total, Advisor Enabled, CRP, Paid
// Leads, Media); net_flows is keyed by net-flow metric (Net Flows, NCNM_NF,
// ECNM, Distributions, Attrition).
export type PredictionsPayload = {
  success?: boolean;
  as_of_period?: string;
  current_month_label?: string;
  grid_ncnm?: Record<string, ChannelProjection>;
  grid_components?: Record<string, ChannelComponents>;
  net_flows?: Record<string, ChannelProjection>;
};
