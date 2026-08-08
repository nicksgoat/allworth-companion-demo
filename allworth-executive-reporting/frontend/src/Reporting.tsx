import { useEffect, useMemo, useState } from 'react';
import './Tamarac2.css';
import './Reporting.css';
import type { KpiDataset, TrendPoint, TrendTarget } from './types/kpi';
import { KpiTile } from './components/KpiTile';
import { ExpandableRow } from './components/ExpandableRow';
import { TrendlineModal } from './components/TrendlineModal';
import {
  buildBucketDescriptors,
  aggregateEntries,
  type BucketMode,
} from './utils/timeBuckets';

// Time-bucket toggle options
const BUCKET_MODES: { value: BucketMode; label: string }[] = [
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'ytd', label: 'YTD' },
];

// Define the fixed order for metrics and channels
const METRICS = ['NCNM', 'Clients', 'Appointments', 'Leads'] as const;
const CHANNELS = ['Total', 'Advisor Enabled', 'CRP', 'Paid Leads', 'Media'] as const;

// Net Flows metrics (shown in the left column)
const NET_FLOW_METRICS = ['Net Flows', 'NCNM_NF', 'ECNM', 'Distributions', 'Attrition'] as const;

// Display names for Net Flow metrics
const NET_FLOW_DISPLAY_NAMES: Record<string, string> = {
  'Net Flows': 'Net Flows',
  'NCNM_NF': 'NCNM',
  'ECNM': 'ECNM',
  'Distributions': 'Distributions',
  'Attrition': 'Attrition'
};

type ReportingProps = {
  metrics: KpiDataset;
  netFlowsMetrics: KpiDataset;
  detailedMetrics?: KpiDataset;
  // While true, the page shell renders immediately and only the KPI matrix
  // shows a loading placeholder (data is still being fetched).
  isLoading?: boolean;
};

function Reporting({ metrics = [], netFlowsMetrics = [], detailedMetrics = [], isLoading = false }: ReportingProps) {
  const [lastRefresh] = useState<Date>(new Date());
  const [yellowThreshold, setYellowThreshold] = useState(80);
  const [bucketMode, setBucketMode] = useState<BucketMode>('monthly');

  // Distinct month periods present in the dataset
  const uniquePeriods = useMemo(
    () => Array.from(new Set(metrics.map((entry) => entry.period))),
    [metrics],
  );

  // Selectable buckets (months / quarters / YTD years) for the active mode
  const bucketDescriptors = useMemo(
    () => buildBucketDescriptors(uniquePeriods, bucketMode),
    [uniquePeriods, bucketMode],
  );

  const bucketOptions = useMemo(
    () => bucketDescriptors.map((descriptor) => descriptor.value),
    [bucketDescriptors],
  );

  const [selectedBucket, setSelectedBucket] = useState<string>(bucketOptions[0] ?? '');

  useEffect(() => {
    if (bucketOptions.length === 0) {
      setSelectedBucket('');
      return;
    }
    if (!bucketOptions.includes(selectedBucket)) {
      setSelectedBucket(bucketOptions[0]);
    }
  }, [bucketOptions, selectedBucket]);

  // Descriptor for the currently selected bucket
  const activeBucket = useMemo(
    () => bucketDescriptors.find((descriptor) => descriptor.value === selectedBucket) ?? bucketDescriptors[0],
    [bucketDescriptors, selectedBucket],
  );

  const memberPeriods = activeBucket?.memberPeriods ?? [];
  const bucketKey = activeBucket?.value ?? '';

  // Whether the active bucket includes the (prorated) current month
  const isCurrentMonth = activeBucket?.includesCurrentMonth ?? false;

  // Aggregate the monthly-grained datasets into the active bucket
  const bucketMetrics = useMemo(
    () => aggregateEntries(metrics, memberPeriods, bucketKey),
    [metrics, memberPeriods, bucketKey],
  );

  const bucketNetFlows = useMemo(
    () => aggregateEntries(netFlowsMetrics, memberPeriods, bucketKey),
    [netFlowsMetrics, memberPeriods, bucketKey],
  );

  const bucketDetailed = useMemo(
    () => aggregateEntries(detailedMetrics, memberPeriods, bucketKey),
    [detailedMetrics, memberPeriods, bucketKey],
  );

  // Create a lookup map for quick access
  const metricsMap = useMemo(() => {
    const map = new Map<string, typeof metrics[0]>();
    bucketMetrics.forEach((entry) => {
      const key = `${entry.metric}-${entry.channel}`;
      map.set(key, entry);
    });
    return map;
  }, [bucketMetrics]);

  // Create a lookup map for Net Flows metrics
  const netFlowsMap = useMemo(() => {
    const map = new Map<string, typeof netFlowsMetrics[0]>();
    bucketNetFlows.forEach((entry) => {
      map.set(entry.metric, entry);
    });
    return map;
  }, [bucketNetFlows]);

  // Create a lookup for detailed (channel_middle) metrics grouped by metric+channel
  const detailedMetricsMap = useMemo(() => {
    const map = new Map<string, typeof detailedMetrics>();
    bucketDetailed.forEach((entry) => {
      const key = `${entry.metric}-${entry.channel}`;
      if (!map.has(key)) {
        map.set(key, []);
      }
      map.get(key)!.push(entry);
    });
    return map;
  }, [bucketDetailed]);

  // --- Trendline (right-click a tile -> "Show Trendline") ---
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; target: TrendTarget } | null>(null);
  const [trendTarget, setTrendTarget] = useState<TrendTarget | null>(null);

  const handleShowTrendline = (target: TrendTarget, anchor: { x: number; y: number }) => {
    setContextMenu({ x: anchor.x, y: anchor.y, target });
  };

  // Dismiss the context menu on any outside click, scroll, or Escape
  useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setContextMenu(null);
    };
    window.addEventListener('click', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('click', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('keydown', onKey);
    };
  }, [contextMenu]);

  // Build the last-12-months series for the active trend target across all datasets
  const trendData = useMemo<TrendPoint[]>(() => {
    if (!trendTarget) return [];
    const pool = [...metrics, ...netFlowsMetrics, ...detailedMetrics];
    const byPeriod = new Map<string, TrendPoint>();
    pool.forEach((entry) => {
      if (
        entry.metric !== trendTarget.metric ||
        entry.channel !== trendTarget.channel ||
        (entry.channelMiddle ?? '') !== (trendTarget.channelMiddle ?? '')
      ) {
        return;
      }
      if (Number.isNaN(Date.parse(entry.period))) return;
      byPeriod.set(entry.period, {
        period: entry.period,
        actual: entry.actual,
        plan: entry.goal ?? null,
        py: entry.pyActual ?? null,
      });
    });
    return Array.from(byPeriod.values())
      .sort((a, b) => Date.parse(a.period) - Date.parse(b.period))
      .slice(-12);
  }, [trendTarget, metrics, netFlowsMetrics, detailedMetrics]);

  return (
    <div className="t2-page">
      <div className="t2-bg" aria-hidden="true">
        <div className="t2-orb t2-orb-1" />
        <div className="t2-orb t2-orb-2" />
        <div className="t2-orb t2-orb-3" />
        <div className="t2-orb t2-orb-4" />
        <div className="t2-orb t2-orb-5" />
      </div>

      <div className="t2-shell perf-console">
        <header className="perf-hero">
          <div className="perf-hero-left">
            <div className="perf-kicker-row">
              <a className="perf-home" href="/">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>
                Back to hub
              </a>
              <span className="perf-kicker">Dashboard</span>
            </div>
            <div className="perf-title"><h1>Performance by Channel</h1></div>
            <p className="perf-tagline">
              KPI matrix for NCNM, Clients, Appointments and Leads across every
              acquisition channel — with plan, prior-year and prorated current-month values.
            </p>
          </div>
        <div className="header-controls perf-hero-right">
          <div className="threshold-control">
            <button
              type="button"
              className="threshold-arrow"
              onClick={() => setYellowThreshold((prev) => Math.max(0, prev - 5))}
              aria-label="Decrease threshold by 5"
            >
              ▼
            </button>
            <input
              type="number"
              className="threshold-input"
              value={yellowThreshold}
              onChange={(e) => setYellowThreshold(Math.max(0, Math.min(100, Number(e.target.value) || 0)))}
              min={0}
              max={100}
              aria-label="Yellow threshold percentage"
            />
            <span className="threshold-percent">%</span>
            <button
              type="button"
              className="threshold-arrow"
              onClick={() => setYellowThreshold((prev) => Math.min(100, prev + 5))}
              aria-label="Increase threshold by 5"
            >
              ▲
            </button>
          </div>
          <div className="last-updated">
            Last updated: {lastRefresh.toLocaleTimeString()}
          </div>
          <div className="comparison-toggle" role="group" aria-label="Time bucket">
            {BUCKET_MODES.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                className={`comparison-toggle__button${bucketMode === value ? ' is-active' : ''}`}
                onClick={() => setBucketMode(value)}
              >
                {label}
              </button>
            ))}
          </div>
          {bucketDescriptors.length > 0 && (
            <div className="comparison-toggle" role="group" aria-label="Period selector">
              {bucketDescriptors.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  className={`comparison-toggle__button${selectedBucket === value ? ' is-active' : ''}`}
                  onClick={() => setSelectedBucket(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        </div>
      </header>

      <main>
        {isLoading ? (
          <section className="reporting-loading" aria-busy="true" aria-live="polite">
            <div className="reporting-loading__spinner" aria-hidden="true" />
            <p className="reporting-loading__text">Loading metrics…</p>
          </section>
        ) : metrics.length === 0 ? (
          <section className="empty-state">
            <h2>No KPI data yet</h2>
            <p>
              Once the data source is configured, metrics will appear here.
            </p>
          </section>
        ) : (
          <div className="kpi-matrix-container">
            {/* Net Flows Column (left side) */}
            <div className="net-flows-column">
              {NET_FLOW_METRICS.map((metric, index) => {
                const entry = netFlowsMap.get(metric);
                const displayName = NET_FLOW_DISPLAY_NAMES[metric] || metric;
                return (
                  <KpiTile 
                    key={metric}
                    entry={entry}
                    isTotal={index === 0}
                    title={displayName}
                    yellowThreshold={yellowThreshold}
                    onShowTrendline={handleShowTrendline}
                  />
                );
              })}
            </div>

            {/* Main Grid (right side) */}
            <div className="kpi-matrix">
              {/* Rows for each channel */}
              {CHANNELS.map((channel) => (
                <ExpandableRow
                  key={channel}
                  channel={channel}
                  metrics={METRICS}
                  metricsMap={metricsMap}
                  detailedMetricsMap={detailedMetricsMap}
                  yellowThreshold={yellowThreshold}
                  onShowTrendline={handleShowTrendline}
                />
              ))}
            </div>
          </div>
        )}
        {isCurrentMonth && (
          <p className="prorated-note">* PY and Plan values are prorated to reflect the current day of the month.</p>
        )}
      </main>

      {contextMenu && (
        <div
          className="tile-context-menu"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
          role="menu"
        >
          <button
            type="button"
            className="tile-context-menu__item"
            role="menuitem"
            onClick={() => {
              setTrendTarget(contextMenu.target);
              setContextMenu(null);
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18" /><path d="m19 9-5 5-4-4-3 3" /></svg>
            Show Trendline
          </button>
        </div>
      )}

      {trendTarget && (
        <TrendlineModal target={trendTarget} data={trendData} onClose={() => setTrendTarget(null)} />
      )}
      </div>
    </div>
  );
}

export default Reporting;
