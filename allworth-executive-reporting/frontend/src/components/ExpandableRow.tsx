import { useState } from 'react';
import type { KpiEntry, TrendTarget } from '../types/kpi';
import { KpiTile } from './KpiTile';

type ExpandableRowProps = {
  channel: string;
  metrics: readonly string[];
  metricsMap: Map<string, KpiEntry | undefined>;
  detailedMetricsMap: Map<string, KpiEntry[]>;
  yellowThreshold?: number;
  onShowTrendline?: (target: TrendTarget, anchor: { x: number; y: number }) => void;
};

export function ExpandableRow({ channel, metrics, metricsMap, detailedMetricsMap, yellowThreshold = 80, onShowTrendline }: ExpandableRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Check if there are any child entries for this channel
  const hasChildEntries = metrics.some((metric) => {
    const children = detailedMetricsMap.get(`${metric}-${channel}`);
    return children && children.length > 0;
  });

  // Get all unique channel_middle values for this channel across all metrics
  const channelMiddleValues = new Set<string>();
  metrics.forEach((metric) => {
    const children = detailedMetricsMap.get(`${metric}-${channel}`) || [];
    children.forEach((child) => {
      if (child.channelMiddle) {
        channelMiddleValues.add(child.channelMiddle);
      }
    });
  });
  const sortedChannelMiddles = Array.from(channelMiddleValues).sort();

  return (
    <div className="expandable-row-container">
      <div className={`matrix-row ${channel === 'Total' ? 'matrix-row--total' : ''}`}>
        {/* Expand toggle button - only for non-Total rows with child data */}
        {channel !== 'Total' && hasChildEntries && (
          <button
            type="button"
            className={`row-expand-toggle ${isExpanded ? 'is-expanded' : ''}`}
            onClick={() => setIsExpanded(!isExpanded)}
            aria-expanded={isExpanded}
            aria-label={isExpanded ? 'Collapse channel breakdown' : 'Expand channel breakdown'}
          >
            <span className="expand-icon">{isExpanded ? '−' : '+'}</span>
          </button>
        )}
        
        {/* Placeholder for alignment when no toggle */}
        {(channel === 'Total' || !hasChildEntries) && (
          <div className="row-expand-placeholder" />
        )}

        {/* Metric tiles */}
        {metrics.map((metric) => {
          const entry = metricsMap.get(`${metric}-${channel}`);
          const tileTitle = channel === 'Total' ? metric : channel;
          
          return (
            <KpiTile 
              key={`${metric}-${channel}`} 
              entry={entry}
              isTotal={channel === 'Total'}
              title={tileTitle}
              yellowThreshold={yellowThreshold}
              onShowTrendline={onShowTrendline}
            />
          );
        })}
      </div>

      {/* Expanded channel_middle breakdown */}
      {isExpanded && hasChildEntries && (
        <div className="channel-middle-breakdown">
          {sortedChannelMiddles.map((channelMiddle) => (
            <div key={channelMiddle} className="channel-middle-row">
              <div className="channel-middle-label">{channelMiddle}</div>
              <div className="channel-middle-tiles">
                {metrics.map((metric) => {
                  const children = detailedMetricsMap.get(`${metric}-${channel}`) || [];
                  const childEntry = children.find((c) => c.channelMiddle === channelMiddle);
                  
                  return (
                    <KpiTile
                      key={`${metric}-${channel}-${channelMiddle}`}
                      entry={childEntry}
                      isTotal={false}
                      title={channelMiddle}
                      compact
                      yellowThreshold={yellowThreshold}
                      onShowTrendline={onShowTrendline}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
