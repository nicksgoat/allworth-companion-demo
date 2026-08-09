import type { ComponentProps, CSSProperties, ReactElement } from 'react';
import { createContext, useContext, useId } from 'react';
import {
  Legend as RechartsLegend,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  type LegendProps,
  type TooltipProps,
} from 'recharts';
import { allworthChartConfig, type ChartConfig } from './chart-config';
import './chart.css';

export type { ChartConfig } from './chart-config';

const ChartContext = createContext<{ config: ChartConfig }>({ config: allworthChartConfig });

export function useChartConfig() {
  return useContext(ChartContext).config;
}

type ResponsiveProps = ComponentProps<typeof ResponsiveContainer>;

interface ChartContainerProps extends Omit<ResponsiveProps, 'children' | 'width' | 'height'> {
  children: ReactElement;
  className?: string;
  config?: ChartConfig;
  height?: number | `${number}%`;
  width?: number | `${number}%`;
}

/**
 * Allworth's shadcn-style chart boundary. Recharts remains fully composable,
 * while sizing, palette variables, typography, grid treatment, and motion are
 * owned in one place for every tool.
 */
export function ChartContainer({
  children,
  className = '',
  config = allworthChartConfig,
  height = 240,
  initialDimension,
  width = '100%',
  ...props
}: ChartContainerProps) {
  const generatedId = useId().replace(/:/g, '');
  const colorVariables = Object.fromEntries(
    Object.entries(config)
      .filter(([, item]) => item.color)
      .map(([key, item]) => [`--color-${key}`, item.color]),
  ) as CSSProperties;
  const stableInitialDimension = initialDimension ?? {
    width: typeof width === 'number' ? width : 1,
    height: typeof height === 'number' ? height : 1,
  };

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        className={`aw-chart ${className}`.trim()}
        data-chart={generatedId}
        style={{ ...colorVariables, width, height }}
      >
        <ResponsiveContainer
          width="100%"
          height="100%"
          minWidth={0}
          minHeight={0}
          initialDimension={stableInitialDimension}
          {...props}
        >
          {children}
        </ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  );
}

/** Shadcn-style shared tooltip with stable Allworth styling and no partial animation. */
export function ChartTooltip({
  contentStyle,
  itemStyle,
  labelStyle,
  wrapperStyle,
  cursor,
  ...props
}: TooltipProps) {
  return (
    <RechartsTooltip
      {...props}
      isAnimationActive={false}
      cursor={cursor ?? { fill: 'rgba(23, 61, 103, 0.045)' }}
      contentStyle={{
        padding: '9px 11px',
        border: '1px solid rgba(23, 61, 103, 0.16)',
        borderRadius: 6,
        background: 'rgba(255, 255, 255, 0.98)',
        boxShadow: '0 8px 20px rgba(12, 46, 78, 0.10)',
        fontFamily: "'Lato', sans-serif",
        fontSize: 11,
        ...contentStyle,
      }}
      itemStyle={{ padding: '2px 0', color: '#595959', ...itemStyle }}
      labelStyle={{ marginBottom: 5, color: '#0C2E4E', fontWeight: 700, ...labelStyle }}
      wrapperStyle={{ outline: 'none', zIndex: 20, ...wrapperStyle }}
    />
  );
}

/** Shared compact legend matching shadcn's low-chrome dashboard treatment. */
export function ChartLegend({ wrapperStyle, ...props }: LegendProps) {
  return (
    <RechartsLegend
      {...props}
      iconType={props.iconType ?? 'square'}
      iconSize={props.iconSize ?? 8}
      wrapperStyle={{
        color: '#595959',
        fontFamily: "'Lato', sans-serif",
        fontSize: 10,
        lineHeight: '20px',
        ...wrapperStyle,
      }}
    />
  );
}
