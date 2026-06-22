import { usd } from "./theme";
import type { CashFlow, MonthValue } from "./types";

export type PerformanceResult = {
  method: "modified_dietz";
  return: number;
  ratio: number;
  return_pct: number;
  gain_loss: number;
  inflow: number;
  outflow: number;
  net_cash_flow: number;
  weighted_cash_flow: number;
};

export function modifiedDietzReturn({
  beginningValue,
  endingValue,
  cashFlows = [],
  startDate,
  endDate,
}: {
  beginningValue: number;
  endingValue: number;
  cashFlows?: CashFlow[];
  startDate?: string;
  endDate?: string;
}): PerformanceResult {
  void startDate;
  void endDate;
  let inflow = 0;
  let outflow = 0;
  for (const flow of cashFlows) {
    if (flow.amount >= 0) {
      inflow += flow.amount;
    } else {
      outflow += Math.abs(flow.amount);
    }
  }

  const adjustedEndingValue = endingValue - outflow;
  const adjustedBeginningValue = beginningValue + inflow;
  const ratio =
    Math.abs(adjustedBeginningValue) > 0.005 ? adjustedEndingValue / adjustedBeginningValue : 1;
  const rate = ratio - 1;
  const gainLoss = adjustedEndingValue - adjustedBeginningValue;
  return {
    method: "modified_dietz",
    return: rate,
    ratio,
    return_pct: rate * 100,
    gain_loss: gainLoss,
    inflow,
    outflow,
    net_cash_flow: inflow - outflow,
    weighted_cash_flow: 0,
  };
}

export function performanceFromSeries(points: MonthValue[], cashFlows: CashFlow[] = []) {
  if (points.length < 2) return undefined;
  const first = points[0];
  const last = points[points.length - 1];
  const flowsInRange = cashFlows.filter((flow) => {
    const month = flow.month ?? flow.date.slice(0, 7);
    return month >= first.month && month <= last.month;
  });
  return modifiedDietzReturn({
    beginningValue: first.value,
    endingValue: last.value,
    cashFlows: flowsInRange,
    startDate: first.month,
    endDate: last.month,
  });
}

export function performanceDeltaLabel(
  points: MonthValue[],
  suffix: string,
  cashFlows: CashFlow[] = [],
) {
  const result = performanceFromSeries(points, cashFlows);
  if (!result) return undefined;
  const sign = result.gain_loss >= 0 ? "+" : "−";
  return {
    text: `${sign}${usd(Math.abs(result.gain_loss))} (${sign}${Math.abs(result.return_pct).toFixed(1)}%) ${suffix}`,
    positive: result.gain_loss >= 0,
    method: result.method,
  };
}
