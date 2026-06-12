import type { AssetClass, MonthValue, Position } from "./types";

// The backend exposes no per-position price history or dividend data, so the
// performance views derive both deterministically from the live payload:
// same seed (account + symbol) → same series on every render and demo run.
// Everything here is clearly labeled illustrative in the UI.

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number): () => number {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const CLASS_WALK: Record<AssetClass, { vol: number; drift: number }> = {
  us_equity: { vol: 0.04, drift: 0.008 },
  intl_equity: { vol: 0.035, drift: 0.005 },
  bond: { vol: 0.012, drift: 0.002 },
  muni_bond: { vol: 0.01, drift: 0.002 },
  cash: { vol: 0.001, drift: 0.003 },
};

// Single names move differently than the broad-market funds in their class
const SYMBOL_WALK: Record<string, { vol: number; drift: number }> = {
  AAPL: { vol: 0.07, drift: 0.012 },
  NVDA: { vol: 0.13, drift: 0.03 },
  TSLA: { vol: 0.15, drift: 0.008 },
  PLTR: { vol: 0.14, drift: 0.025 },
};

export function lastMonths(n: number): string[] {
  const now = new Date();
  const out: string[] = [];
  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }
  return out;
}

// Random walk backward from the position's live value, so the series always
// ends exactly at what the holdings list shows.
export function positionHistory(position: Position, n = 12): MonthValue[] {
  const rand = mulberry32(hash(`${position.accountId}:${position.symbol}`));
  const { vol, drift } = SYMBOL_WALK[position.symbol] ?? CLASS_WALK[position.assetClass];
  const values: number[] = new Array(n);
  values[n - 1] = position.value;
  for (let i = n - 2; i >= 0; i--) {
    const monthly = 1 + drift + vol * (rand() * 2 - 1);
    values[i] = Math.max(position.value * 0.05, values[i + 1] / monthly);
  }
  return lastMonths(n).map((month, i) => ({ month, value: Math.round(values[i]) }));
}

const CLASS_YIELD: Record<AssetClass, number> = {
  us_equity: 0.013,
  intl_equity: 0.029,
  bond: 0.038,
  muni_bond: 0.031,
  cash: 0.042,
};

// Single names that pay little or no dividend
const SYMBOL_YIELD: Record<string, number> = { AAPL: 0.004, NVDA: 0.0003, TSLA: 0, PLTR: 0 };

export function estimatedAnnualIncome(position: Position): number {
  const y = SYMBOL_YIELD[position.symbol] ?? CLASS_YIELD[position.assetClass];
  return position.value * y;
}

export function ytdFraction(): number {
  const now = new Date();
  const start = new Date(now.getFullYear(), 0, 1);
  return (now.getTime() - start.getTime()) / (365 * 24 * 3600 * 1000);
}
