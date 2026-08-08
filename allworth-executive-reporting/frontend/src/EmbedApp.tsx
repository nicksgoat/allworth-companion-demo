import { useEffect, useMemo, useState } from 'react';
import './Reporting.css';
import type { KpiDataset } from './types/kpi';
import { KpiTile } from './components/KpiTile';
import { ExpandableRow } from './components/ExpandableRow';
import { fetchAllMetrics } from './services/api';

const METRICS = ['NCNM', 'Clients', 'Appointments', 'Leads'] as const;
const CHANNELS = ['Total', 'Advisor Enabled', 'CRP', 'Paid Leads', 'Media'] as const;
const NET_FLOW_METRICS = ['Net Flows', 'NCNM_NF', 'ECNM', 'Distributions', 'Attrition'] as const;

const NET_FLOW_DISPLAY_NAMES: Record<string, string> = {
  'Net Flows': 'Net Flows',
  'NCNM_NF': 'NCNM',
  'ECNM': 'ECNM',
  'Distributions': 'Distributions',
  'Attrition': 'Attrition'
};

const AUTO_REFRESH_INTERVAL = 5 * 60 * 1000; // 5 minutes
const DEFAULT_YELLOW_THRESHOLD = 80;

type EmbedAppProps = {
  metrics: KpiDataset;
  netFlowsMetrics: KpiDataset;
  detailedMetrics?: KpiDataset;
};

function EmbedApp({ metrics: initialMetrics, netFlowsMetrics: initialNetFlows, detailedMetrics: initialDetailed = [] }: EmbedAppProps) {
  const [metrics, setMetrics] = useState<KpiDataset>(initialMetrics);
  const [netFlowsMetrics, setNetFlowsMetrics] = useState<KpiDataset>(initialNetFlows);
  const [detailedMetrics, setDetailedMetrics] = useState<KpiDataset>(initialDetailed);

  // Auto-refresh on interval
  useEffect(() => {
    const refresh = async () => {
      try {
        const bundle = await fetchAllMetrics();
        if (bundle.kpiMetrics.length > 0) {
          setMetrics(bundle.kpiMetrics);
          setNetFlowsMetrics(bundle.netFlows);
          setDetailedMetrics(bundle.detailedMetrics);
        }
      } catch {
        // silent — don't break the embed on transient errors
      }
    };

    const id = setInterval(refresh, AUTO_REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, []);

  // Read period from query param or default to latest
  const periodFromUrl = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('period') ?? undefined;
  }, []);

  const selectedPeriod = useMemo(() => {
    if (periodFromUrl) return periodFromUrl;
    const uniquePeriods = Array.from(new Set(metrics.map((e) => e.period)));
    const now = new Date();
    const currentMonthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const ordered = uniquePeriods
      .map((p) => ({ period: p, ts: Date.parse(p) }))
      .filter((item) => !Number.isNaN(item.ts) && item.ts <= currentMonthStart.getTime() + 31 * 24 * 60 * 60 * 1000)
      .sort((a, b) => b.ts - a.ts);
    return ordered[0]?.period ?? uniquePeriods[0] ?? '';
  }, [metrics, periodFromUrl]);

  const isCurrentMonth = useMemo(() => {
    const now = new Date();
    const currentLabel = now.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
    return selectedPeriod === currentLabel;
  }, [selectedPeriod]);

  const periodMetrics = useMemo(() => {
    return metrics.filter((entry) => entry.period === selectedPeriod);
  }, [metrics, selectedPeriod]);

  const metricsMap = useMemo(() => {
    const map = new Map<string, typeof metrics[0]>();
    periodMetrics.forEach((entry) => {
      map.set(`${entry.metric}-${entry.channel}`, entry);
    });
    return map;
  }, [periodMetrics]);

  const netFlowsMap = useMemo(() => {
    const map = new Map<string, typeof netFlowsMetrics[0]>();
    netFlowsMetrics
      .filter((entry) => entry.period === selectedPeriod)
      .forEach((entry) => {
        map.set(entry.metric, entry);
      });
    return map;
  }, [netFlowsMetrics, selectedPeriod]);

  const detailedMetricsMap = useMemo(() => {
    const map = new Map<string, typeof detailedMetrics>();
    detailedMetrics
      .filter((entry) => entry.period === selectedPeriod)
      .forEach((entry) => {
        const key = `${entry.metric}-${entry.channel}`;
        if (!map.has(key)) {
          map.set(key, []);
        }
        map.get(key)!.push(entry);
      });
    return map;
  }, [detailedMetrics, selectedPeriod]);

  if (metrics.length === 0) {
    return (
      <div className="embed-shell">
        <section className="empty-state" style={{ margin: 0 }}>
          <h2>No KPI data yet</h2>
        </section>
      </div>
    );
  }

  return (
    <div className="embed-shell">
      <div className="kpi-matrix-container" style={{ padding: 0 }}>
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
                yellowThreshold={DEFAULT_YELLOW_THRESHOLD}
              />
            );
          })}
        </div>

        {/* Main Grid (right side) */}
        <div className="kpi-matrix">
          {CHANNELS.map((channel) => (
            <ExpandableRow
              key={channel}
              channel={channel}
              metrics={METRICS}
              metricsMap={metricsMap}
              detailedMetricsMap={detailedMetricsMap}
              yellowThreshold={DEFAULT_YELLOW_THRESHOLD}
            />
          ))}
        </div>
      </div>
      {isCurrentMonth && (
        <p className="prorated-note">* PY and Plan values are prorated to reflect the current day of the month.</p>
      )}
    </div>
  );
}

export default EmbedApp;
