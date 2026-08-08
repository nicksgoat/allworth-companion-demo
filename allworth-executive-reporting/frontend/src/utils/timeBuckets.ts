import type { KpiEntry } from '../types/kpi';

// Time-bucket aggregation for the Performance by Channel page.
// The underlying dataset is monthly-grained (one entry per metric/channel/period,
// where `period` is a month label such as "Jan 2026"). These helpers roll those
// monthly entries up into Quarterly and Year-to-Date buckets on the client.

export type BucketMode = 'monthly' | 'quarterly' | 'ytd';

export type BucketDescriptor = {
  value: string;            // stable key used for selection (e.g. "2026-Q1")
  label: string;            // display label (e.g. "Q1 2026")
  memberPeriods: string[];  // original month period strings included in the bucket
  includesCurrentMonth: boolean;
};

// Numeric fields that are summed when rolling months up into a larger bucket.
const SUMMABLE_FIELDS = [
  'actual',
  'goal',
  'pyActual',
  'pyProrated',
  'goalProrated',
  'target',
  'budget',
] as const;

function currentMonthLabel(): string {
  return new Date().toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

type ParsedPeriod = { period: string; year: number; month: number; ts: number };

function parsePeriods(periods: string[]): ParsedPeriod[] {
  const now = new Date();
  const currentMonthStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime();

  return periods
    .map((period) => {
      const ts = Date.parse(period);
      if (Number.isNaN(ts)) return null;
      const d = new Date(ts);
      return { period, year: d.getFullYear(), month: d.getMonth(), ts };
    })
    .filter((item): item is ParsedPeriod => item !== null)
    // Drop any period more than a month into the future (guards against bad data).
    .filter((item) => item.ts <= currentMonthStart + 31 * 24 * 60 * 60 * 1000);
}

/**
 * Build the selectable bucket descriptors for the given periods and mode,
 * ordered most-recent first.
 */
export function buildBucketDescriptors(periods: string[], mode: BucketMode): BucketDescriptor[] {
  const parsed = parsePeriods(periods);
  const nowLabel = currentMonthLabel();

  if (mode === 'monthly') {
    // Show the current month plus the last 4 (5 most recent).
    return parsed
      .slice()
      .sort((a, b) => b.ts - a.ts)
      .slice(0, 5)
      .map((item) => ({
        value: item.period,
        label: item.period,
        memberPeriods: [item.period],
        includesCurrentMonth: item.period === nowLabel,
      }));
  }

  // Group parsed periods into quarterly or YTD buckets.
  type Group = { value: string; label: string; sortKey: number; items: ParsedPeriod[] };
  const groups = new Map<string, Group>();

  for (const item of parsed) {
    let value: string;
    let label: string;
    let sortKey: number;

    if (mode === 'quarterly') {
      const quarter = Math.floor(item.month / 3) + 1;
      value = `${item.year}-Q${quarter}`;
      label = `Q${quarter} ${item.year}`;
      sortKey = item.year * 10 + quarter;
    } else {
      // ytd — one bucket per year (Jan through the latest available month)
      value = `${item.year}-YTD`;
      label = `YTD ${item.year}`;
      sortKey = item.year;
    }

    const group = groups.get(value);
    if (group) {
      group.items.push(item);
    } else {
      groups.set(value, { value, label, sortKey, items: [item] });
    }
  }

  // Quarterly shows the current quarter plus the last 4 (5 most recent);
  // YTD keeps every available year.
  const ordered = Array.from(groups.values()).sort((a, b) => b.sortKey - a.sortKey);
  const limited = mode === 'quarterly' ? ordered.slice(0, 5) : ordered;

  return limited
    .map((group) => {
      const memberPeriods = group.items
        .slice()
        .sort((a, b) => a.ts - b.ts)
        .map((item) => item.period);
      return {
        value: group.value,
        label: group.label,
        memberPeriods,
        includesCurrentMonth: memberPeriods.includes(nowLabel),
      };
    });
}

/**
 * Roll a dataset's monthly entries up into a single bucket by summing the
 * numeric fields for each metric/channel/channelMiddle combination.
 * Entries outside `memberPeriods` are ignored. Returned entries carry
 * `period = bucketValue` so downstream lookups can key off the bucket.
 */
export function aggregateEntries(
  entries: KpiEntry[],
  memberPeriods: string[],
  bucketValue: string,
): KpiEntry[] {
  const members = new Set(memberPeriods);
  const grouped = new Map<string, KpiEntry>();

  for (const entry of entries) {
    if (!members.has(entry.period)) continue;

    const key = `${entry.metric}|${entry.channel}|${entry.channelMiddle ?? ''}`;
    const existing = grouped.get(key);

    if (!existing) {
      grouped.set(key, {
        ...entry,
        id: `${key}|${bucketValue}`,
        period: bucketValue,
        periodLabel: bucketValue,
      });
      continue;
    }

    for (const field of SUMMABLE_FIELDS) {
      const current = existing[field];
      const addition = entry[field];
      if (addition === undefined) continue;
      existing[field] = (current ?? 0) + addition;
    }
  }

  return Array.from(grouped.values());
}
