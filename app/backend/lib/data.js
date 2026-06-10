import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

export const BACKEND_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
export const seed = JSON.parse(readFileSync(join(BACKEND_DIR, "data", "seed.json"), "utf8"));

export const fmtUSD = (n) =>
  (n < 0 ? "-$" : "$") + Math.abs(Math.round(n)).toLocaleString("en-US");

export function accountsFor() {
  const allworth = seed.accounts.filter((a) => a.group === "allworth");
  const outside = seed.accounts.filter((a) => a.group === "outside");
  const sum = (xs) => xs.reduce((s, a) => s + a.balance, 0);
  return {
    allworth,
    outside,
    allworthTotal: sum(allworth),
    heldAwayTotal: sum(outside.filter((a) => a.type !== "liability")),
    liabilitiesTotal: sum(outside.filter((a) => a.type === "liability")),
    netWorth: sum(seed.accounts),
  };
}

export function spendingSummary(months = 3) {
  const recent = seed.spending.slice(-months);
  const avg = recent.reduce((s, m) => s + m.total, 0) / recent.length;
  const plan = seed.plan.spendingAssumptionMonthly;
  return {
    months: recent,
    all: seed.spending,
    avg3mo: Math.round(avg),
    plan,
    overPlanPct: Math.round(((avg - plan) / plan) * 100),
  };
}

export function portfolioFor() {
  const byAccount = {};
  for (const p of seed.positions) (byAccount[p.accountId] ??= []).push(p);
  return { positions: seed.positions, byAccount, taxLots: seed.taxLots };
}
