// The 8 demo tools: Anthropic tool definitions + local implementations over seed data.
import { seed, fmtUSD, accountsFor, spendingSummary, portfolioFor } from "./data.js";
import { activeFacts, addFacts, profileAsContext } from "./memory.js";
import { nudgesFor } from "./nudges.js";

// Labels drive the tool chips in the iOS chat UI.
export const TOOL_LABELS = {
  get_accounts: "Reading your accounts…",
  get_portfolio: "Reading your portfolio…",
  get_financial_plan: "Reviewing your plan…",
  get_spending: "Analyzing spending…",
  get_client_profile: "Recalling what I know…",
  update_client_profile: "Remembering that…",
  simulate_tax_impact: "Estimating taxes…",
  get_advisor_brief: "Preparing advisor brief…",
};

export const toolDefinitions = [
  {
    name: "get_accounts",
    description:
      "All of the client's accounts — Allworth-managed and outside (held-away) — with balances, 12-month history, and net worth totals.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_portfolio",
    description:
      "Holdings across all accounts: positions with quantities, prices, values, asset classes, plus tax lots with cost basis and holding term.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_financial_plan",
    description:
      "The client's financial plan: spending assumption, income plan, tax profile, and goals (lake house, 529s, retirement income).",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "get_spending",
    description:
      "Monthly spending by category vs. plan, including the recent 3-month average and how far it runs over plan.",
    input_schema: {
      type: "object",
      properties: {
        months: { type: "integer", description: "How many recent months to summarize (default 3)" },
      },
      required: [],
    },
  },
  {
    name: "get_client_profile",
    description:
      "What the assistant has learned about this client over time: goals, preferences, concerns, liquidity events — each with provenance.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
  {
    name: "update_client_profile",
    description:
      "Save a newly learned fact about the client (goal, preference, concern, liquidity event, or outside asset mentioned).",
    input_schema: {
      type: "object",
      properties: {
        fact: { type: "string", description: "The fact, stated plainly" },
        category: {
          type: "string",
          enum: ["goals", "preferences", "concerns", "liquidity_events", "outside_assets_mentioned", "life_events"],
        },
        source_quote: { type: "string", description: "Short verbatim quote from the client that supports the fact" },
      },
      required: ["fact", "category"],
    },
  },
  {
    name: "simulate_tax_impact",
    description:
      "Estimate capital-gains tax for raising a dollar amount by selling from a given account, using real tax lots (highest-basis-first). Returns proceeds, realized gain, estimated tax, and effective drag.",
    input_schema: {
      type: "object",
      properties: {
        amount: { type: "number", description: "Dollar amount to raise" },
        accountId: {
          type: "string",
          description: "Account to sell from: acct_trust (taxable trust) or acct_rh (Robinhood). Cash accounts need no simulation.",
        },
        symbol: { type: "string", description: "Optional: restrict the sale to one holding (e.g. AAPL)" },
      },
      required: ["amount", "accountId"],
    },
  },
  {
    name: "get_advisor_brief",
    description:
      "Advisor-facing brief for a client: held-away assets detected, open nudges, learned profile, and suggested talking points.",
    input_schema: { type: "object", properties: {}, required: [] },
  },
];

export function runTool(name, input, clientId) {
  switch (name) {
    case "get_accounts": {
      const a = accountsFor();
      return {
        netWorth: a.netWorth,
        allworthManagedTotal: a.allworthTotal,
        heldAwayTotal: a.heldAwayTotal,
        liabilitiesTotal: a.liabilitiesTotal,
        accounts: seed.accounts.map(({ history, ...acct }) => acct),
        netWorthHistory: seed.netWorthHistory,
      };
    }
    case "get_portfolio": {
      const p = portfolioFor();
      const trustValue = p.positions.filter((x) => x.accountId === "acct_trust").reduce((s, x) => s + x.value, 0);
      const aapl = p.positions.find((x) => x.accountId === "acct_trust" && x.symbol === "AAPL");
      return {
        positions: p.positions,
        taxLots: p.taxLots,
        concentrationNote: aapl
          ? `AAPL is ${((aapl.value / trustValue) * 100).toFixed(1)}% of the trust account.`
          : null,
      };
    }
    case "get_financial_plan":
      return { plan: seed.plan, liquidityEvent: seed.liquidityEvent };
    case "get_spending": {
      const s = spendingSummary(input?.months ?? 3);
      return {
        recentMonths: s.months,
        avg3mo: s.avg3mo,
        plannedMonthly: s.plan,
        overPlanPct: s.overPlanPct,
        note: `Spending is averaging ${fmtUSD(s.avg3mo)}/mo against a ${fmtUSD(s.plan)}/mo plan (${s.overPlanPct}% over). Travel and Gifts/Family drive most of the difference.`,
      };
    }
    case "get_client_profile":
      return { clientId, facts: activeFacts(clientId), summary: profileAsContext(clientId) };
    case "update_client_profile": {
      const added = addFacts(clientId, [input], null);
      return added.length
        ? { saved: true, fact: added[0] }
        : { saved: false, reason: "Similar fact already on file." };
    }
    case "simulate_tax_impact":
      return simulateTaxImpact(input);
    case "get_advisor_brief": {
      const a = accountsFor();
      return {
        client: seed.personas.clients.find((c) => c.id === clientId) ?? null,
        managedTotal: a.allworthTotal,
        heldAwayDetected: a.heldAwayTotal,
        heldAwayAccounts: a.outside.filter((x) => x.type !== "liability").map(({ history, ...acct }) => acct),
        liabilities: a.outside.filter((x) => x.type === "liability").map(({ history, ...acct }) => acct),
        openNudges: nudgesFor(clientId),
        profile: activeFacts(clientId),
        liquidityEvent: seed.liquidityEvent,
      };
    }
    default:
      return { error: `Unknown tool: ${name}` };
  }
}

const LT_RATE = 0.15 + 0.038; // cap gains + NIIT
const ST_RATE = 0.24 + 0.038; // ordinary bracket + NIIT

function simulateTaxImpact({ amount, accountId, symbol }) {
  const prices = Object.fromEntries(seed.positions.map((p) => [`${p.accountId}:${p.symbol}`, p.price]));
  let lots = seed.taxLots.filter((l) => l.accountId === accountId);
  if (symbol) lots = lots.filter((l) => l.symbol === symbol.toUpperCase());
  if (!lots.length)
    return { error: `No tax lots found for ${accountId}${symbol ? ` / ${symbol}` : ""}. Cash accounts can be drawn with no capital-gains tax.` };

  // Sell highest basis first (most tax-efficient ordering).
  const ordered = [...lots].sort((a, b) => b.costPerShare - a.costPerShare);
  let remaining = amount;
  let proceeds = 0, ltGain = 0, stGain = 0;
  const sales = [];
  for (const lot of ordered) {
    if (remaining <= 0) break;
    const price = prices[`${lot.accountId}:${lot.symbol}`];
    if (!price) continue;
    const lotValue = lot.qty * price;
    const sellValue = Math.min(remaining, lotValue);
    const sellQty = sellValue / price;
    const gain = sellQty * (price - lot.costPerShare);
    if (lot.term === "short") stGain += gain;
    else ltGain += gain;
    proceeds += sellValue;
    remaining -= sellValue;
    sales.push({
      lotId: lot.id,
      symbol: lot.symbol,
      qtySold: Math.round(sellQty * 100) / 100,
      costPerShare: lot.costPerShare,
      price,
      proceeds: Math.round(sellValue),
      gain: Math.round(gain),
      term: lot.term,
      acquired: lot.acquired,
    });
  }
  const estTax = Math.round(ltGain * LT_RATE + stGain * ST_RATE);
  return {
    requested: amount,
    proceedsAvailable: Math.round(proceeds),
    shortfall: remaining > 0 ? Math.round(remaining) : 0,
    realizedGainLongTerm: Math.round(ltGain),
    realizedGainShortTerm: Math.round(stGain),
    estimatedTax: estTax,
    effectiveTaxDragPct: proceeds > 0 ? Math.round((estTax / proceeds) * 1000) / 10 : 0,
    assumptions: `Long-term gains at ${(LT_RATE * 100).toFixed(1)}% (15% cap gains + 3.8% NIIT), short-term at ${(ST_RATE * 100).toFixed(1)}%. Lots sold highest-basis-first. Estimates only — Dana can run exact numbers.`,
    sales,
  };
}
