export type ThoughtSpotCell = { formattedValue?: string; value?: unknown } | string | number | null | undefined;

export type ThoughtSpotRenderContext = {
  data?: ThoughtSpotCell[][];
};
