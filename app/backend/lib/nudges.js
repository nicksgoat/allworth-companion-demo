// Rule-based nudge engine. Deterministic — no LLM involved.
import { seed, fmtUSD, spendingSummary, portfolioFor } from "./data.js";

export function nudgesFor(clientId) {
  const nudges = [];

  const s = spendingSummary(3);
  if (s.avg3mo > s.plan * 1.15) {
    nudges.push({
      id: "nudge_spending",
      type: "spending",
      title: "Spending is running above plan",
      headline: `${s.overPlanPct}% over plan`,
      body: `Your last three months averaged ${fmtUSD(s.avg3mo)}/mo against a ${fmtUSD(s.plan)}/mo plan — about ${s.overPlanPct}% over. Travel and Gifts/Family account for most of the difference. At this pace it's worth checking what it means for the lake house timeline.`,
      cta: "Ask me what this means",
      advisorCta: "Discuss with Dana",
      severity: "attention",
    });
  }

  const { positions } = portfolioFor();
  const byAccount = {};
  for (const p of positions) {
    (byAccount[p.accountId] ??= { total: 0, positions: [] });
    byAccount[p.accountId].total += p.value;
    byAccount[p.accountId].positions.push(p);
  }
  // Concentration rule targets single stocks; diversified funds don't count.
  const FUNDS = new Set(["VTI", "VXUS", "VTEB", "BND", "FXAIX", "FSPSX", "FXNAX", "SPAXX"]);
  for (const [accountId, { total, positions: ps }] of Object.entries(byAccount)) {
    for (const p of ps) {
      if (p.assetClass === "cash" || p.symbol === "CASH" || FUNDS.has(p.symbol)) continue;
      const weight = p.value / total;
      if (weight > 0.2) {
        const acct = seed.accounts.find((a) => a.id === accountId);
        const label = acct?.group === "outside" ? `your ${acct.institution} account` : (acct?.name ?? accountId);
        nudges.push({
          id: `nudge_conc_${accountId}_${p.symbol}`,
          type: "concentration",
          title: `${p.symbol} is a large share of ${label}`,
          headline: `${Math.round(weight * 100)}% of the account`,
          body: `${p.name} makes up about ${Math.round(weight * 100)}% of ${label} (${fmtUSD(p.value)}). Single positions this large can swing the whole account. There are ways to reduce concentration over time — some more tax-aware than others.`,
          cta: "Ask me about my options",
          advisorCta: "Discuss with Dana",
          severity: "info",
        });
      }
    }
  }

  return nudges;
}
