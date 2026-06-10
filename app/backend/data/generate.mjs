// Deterministic synthetic seed data generator. ALL DATA IS FABRICATED.
// Run: npm run seed  (writes seed.json next to this file)
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "seed.json");

// Mulberry32 seeded PRNG — same output every run.
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = rng(20260622);
const jitter = (base, pct) => base * (1 + (rand() * 2 - 1) * pct);
const r0 = (n) => Math.round(n);

// ---- Months: 12 monthly points ending 2026-06 ----
const months = [];
{
  let y = 2025, m = 7; // 2025-07 .. 2026-06
  for (let i = 0; i < 12; i++) {
    months.push(`${y}-${String(m).padStart(2, "0")}`);
    m++; if (m > 12) { m = 1; y++; }
  }
}

// ---- Accounts (current balances per handoff §6) ----
const accounts = [
  { id: "acct_trust",  name: "Trust Brokerage",     institution: "Allworth (Schwab)", group: "allworth", type: "taxable",   balance: 1420000 },
  { id: "acct_ira",    name: "Rollover IRA",         institution: "Allworth (Schwab)", group: "allworth", type: "ira",       balance: 880000 },
  { id: "acct_roth",   name: "Roth IRA",             institution: "Allworth (Schwab)", group: "allworth", type: "roth",      balance: 145000 },
  { id: "acct_401k",   name: "401(k) — Former Employer", institution: "Fidelity",      group: "outside",  type: "401k",      balance: 385000 },
  { id: "acct_rh",     name: "Brokerage",            institution: "Robinhood",         group: "outside",  type: "taxable",   balance: 96000 },
  { id: "acct_chk",    name: "Checking",             institution: "Chase",             group: "outside",  type: "cash",      balance: 28000 },
  { id: "acct_sav",    name: "Savings",              institution: "Chase",             group: "outside",  type: "cash",      balance: 102000 },
  { id: "acct_mtg",    name: "Mortgage",             institution: "Chase",             group: "outside",  type: "liability", balance: -310000 },
];

// ---- Per-account 12-month balance history (ends exactly at current balance) ----
// Market-ish path: growth assets wiggle, cash drifts, mortgage amortizes.
const marketPath = (() => {
  // shared monthly return series so accounts correlate like real markets
  const rets = [];
  for (let i = 0; i < 11; i++) rets.push(0.007 + (rand() * 2 - 1) * 0.028); // ~0.7%/mo ± noise
  rets[3] = -0.034; // one visible drawdown month so the sparkline isn't a ramp
  rets[7] = -0.012;
  return rets;
})();

function historyFor(acct) {
  const out = [];
  if (acct.type === "liability") {
    let b = acct.balance - 11 * 1450; // amortizing toward current
    for (let i = 0; i < 12; i++) { out.push(r0(b)); b += 1450; }
    out[11] = acct.balance;
    return out;
  }
  if (acct.type === "cash") {
    let b = acct.balance;
    const path = [b];
    for (let i = 0; i < 11; i++) { b = b * (1 + (rand() * 2 - 1) * 0.06) + (rand() - 0.55) * 3000; path.unshift(r0(Math.max(b, acct.balance * 0.6))); }
    path[11] = acct.balance;
    return path;
  }
  // growth: walk backwards through shared return series, account-level noise
  let b = acct.balance;
  const path = [r0(b)];
  for (let i = 10; i >= 0; i--) {
    const drag = acct.id === "acct_trust" ? 9000 : 0; // monthly income withdrawals from trust
    b = (b + drag) / (1 + marketPath[i] + (rand() * 2 - 1) * 0.006);
    path.unshift(r0(b));
  }
  return path;
}
for (const a of accounts) a.history = historyFor(a);

const netWorthHistory = months.map((month, i) => ({
  month,
  value: accounts.reduce((s, a) => s + a.history[i], 0),
}));

// ---- Portfolio positions ----
const positions = [
  // Trust brokerage (~60/40, AAPL ~12% of trust)
  { accountId: "acct_trust", symbol: "AAPL", name: "Apple Inc.",                       qty: 800,  price: 213.00, assetClass: "us_equity" },
  { accountId: "acct_trust", symbol: "VTI",  name: "Vanguard Total Stock Market ETF",  qty: 1640, price: 295.00, assetClass: "us_equity" },
  { accountId: "acct_trust", symbol: "VXUS", name: "Vanguard Total Intl Stock ETF",    qty: 2520, price: 64.50,  assetClass: "intl_equity" },
  { accountId: "acct_trust", symbol: "VTEB", name: "Vanguard Tax-Exempt Bond ETF",     qty: 6470, price: 51.20,  assetClass: "muni_bond" },
  { accountId: "acct_trust", symbol: "BND",  name: "Vanguard Total Bond Market ETF",   qty: 2280, price: 73.40,  assetClass: "bond" },
  { accountId: "acct_trust", symbol: "CASH", name: "Money Market Sweep",               qty: 1,    price: 104644, assetClass: "cash" },
  // Rollover IRA
  { accountId: "acct_ira", symbol: "VTI",  name: "Vanguard Total Stock Market ETF",    qty: 1490, price: 295.00, assetClass: "us_equity" },
  { accountId: "acct_ira", symbol: "BND",  name: "Vanguard Total Bond Market ETF",     qty: 4720, price: 73.40,  assetClass: "bond" },
  { accountId: "acct_ira", symbol: "VXUS", name: "Vanguard Total Intl Stock ETF",      qty: 1450, price: 64.50,  assetClass: "intl_equity" },
  // Roth IRA
  { accountId: "acct_roth", symbol: "VTI", name: "Vanguard Total Stock Market ETF",    qty: 491,  price: 295.00, assetClass: "us_equity" },
  // Fidelity 401(k)
  { accountId: "acct_401k", symbol: "FXAIX", name: "Fidelity 500 Index Fund",          qty: 1530, price: 215.00, assetClass: "us_equity" },
  { accountId: "acct_401k", symbol: "FXNAX", name: "Fidelity US Bond Index Fund",      qty: 5310, price: 10.55,  assetClass: "bond" },
  // Robinhood (concentrated tech, low basis)
  { accountId: "acct_rh", symbol: "NVDA", name: "NVIDIA Corp.",                        qty: 310,  price: 168.00, assetClass: "us_equity" },
  { accountId: "acct_rh", symbol: "TSLA", name: "Tesla Inc.",                          qty: 95,   price: 262.00, assetClass: "us_equity" },
  { accountId: "acct_rh", symbol: "PLTR", name: "Palantir Technologies",               qty: 152,  price: 124.00, assetClass: "us_equity" },
  { accountId: "acct_rh", symbol: "CASH", name: "Cash",                                qty: 1,    price: 182,    assetClass: "cash" },
];
for (const p of positions) p.value = r0(p.qty * p.price);

// ---- Tax lots (granular enough that funding options produce different estimates) ----
const taxLots = [
  // AAPL in trust: three very different basis profiles
  { id: "lot_aapl_a", accountId: "acct_trust", symbol: "AAPL", qty: 400, costPerShare: 27.40,  acquired: "2015-03-12", term: "long" },
  { id: "lot_aapl_b", accountId: "acct_trust", symbol: "AAPL", qty: 250, costPerShare: 132.05, acquired: "2021-09-08", term: "long" },
  { id: "lot_aapl_c", accountId: "acct_trust", symbol: "AAPL", qty: 150, costPerShare: 187.90, acquired: "2024-11-21", term: "long" },
  // Trust ETFs (modest gains)
  { id: "lot_vti_t1", accountId: "acct_trust", symbol: "VTI",  qty: 1100, costPerShare: 201.30, acquired: "2019-06-14", term: "long" },
  { id: "lot_vti_t2", accountId: "acct_trust", symbol: "VTI",  qty: 540,  costPerShare: 262.75, acquired: "2024-02-09", term: "long" },
  { id: "lot_vxus_t", accountId: "acct_trust", symbol: "VXUS", qty: 2520, costPerShare: 55.10,  acquired: "2020-10-02", term: "long" },
  { id: "lot_vteb_t", accountId: "acct_trust", symbol: "VTEB", qty: 6470, costPerShare: 49.85,  acquired: "2021-04-16", term: "long" },
  { id: "lot_bnd_t",  accountId: "acct_trust", symbol: "BND",  qty: 2280, costPerShare: 74.95,  acquired: "2022-01-20", term: "long" }, // small loss
  // Robinhood: very low basis, one short-term lot
  { id: "lot_nvda_1", accountId: "acct_rh", symbol: "NVDA", qty: 240, costPerShare: 21.60,  acquired: "2019-08-05", term: "long" },
  { id: "lot_nvda_2", accountId: "acct_rh", symbol: "NVDA", qty: 70,  costPerShare: 118.40, acquired: "2025-10-12", term: "short" },
  { id: "lot_tsla_1", accountId: "acct_rh", symbol: "TSLA", qty: 95,  costPerShare: 58.20,  acquired: "2019-12-18", term: "long" },
  { id: "lot_pltr_1", accountId: "acct_rh", symbol: "PLTR", qty: 152, costPerShare: 9.85,   acquired: "2020-10-01", term: "long" },
];

// ---- Financial plan ----
const plan = {
  clientId: "maya",
  riskTarget: "60/40 growth & income",
  spendingAssumptionMonthly: 14000,
  portfolioIncomeMonthly: 9000,
  otherIncomeMonthly: 4500, // part-time consulting
  filingStatus: "single",
  state: "TX",
  estFederalBracket: 0.24,
  capGainsRate: 0.15,
  niitApplies: true,
  goals: [
    { id: "goal_lake",  label: "Lake house",        target: 350000, horizonYears: 4, funded: 0.32 },
    { id: "goal_529",   label: "Grandkids' 529s",   target: 120000, horizonYears: 10, funded: 0.18 },
    { id: "goal_income", label: "Retirement income", target: null,  detail: "$9,000/mo from portfolio through age 95" },
  ],
};

// ---- Spending: 12 months vs $14k plan; last 3 months avg ≈ $16.5k (≈18% over) ----
const spendCats = ["Housing", "Travel", "Dining", "Health", "Auto", "Gifts/Family", "Everything else"];
const spendBase = { Housing: 3900, Travel: 1400, Dining: 1150, Health: 950, Auto: 800, "Gifts/Family": 900, "Everything else": 4600 };
const spending = months.map((month, i) => {
  const late = i >= 9; // last 3 months run hot
  const factor = late ? [1.16, 1.21, 1.17][i - 9] : jitter(0.975, 0.045);
  const cats = {};
  let total = 0;
  for (const c of spendCats) {
    let v = jitter(spendBase[c] * factor, 0.10);
    if (late && c === "Travel") v *= 1.85;       // Portugal trip + lake house scouting
    if (late && c === "Gifts/Family") v *= 1.4;  // grandkid camp tuition
    cats[c] = r0(v);
    total += cats[c];
  }
  // normalize late months to land avg ≈ 16.5k
  const target = late ? [16100, 16900, 16500][i - 9] : null;
  if (target) {
    const k = target / total;
    total = 0;
    for (const c of spendCats) { cats[c] = r0(cats[c] * k); total += cats[c]; }
  }
  return { month, total, planned: plan.spendingAssumptionMonthly, categories: cats };
});

// ---- Transactions (recent, plausible; charts & lists look real) ----
const txTemplates = [
  ["acct_chk", "Whole Foods Market", "Groceries", -180, 14],
  ["acct_chk", "Shell Oil", "Auto", -62, 6],
  ["acct_chk", "Legacy Med Group", "Health", -240, 2],
  ["acct_chk", "AT&T", "Utilities", -145, 1],
  ["acct_chk", "City of Plano Utilities", "Utilities", -310, 1],
  ["acct_chk", "Sixty Vines Plano", "Dining", -120, 3],
  ["acct_chk", "Delta Air Lines", "Travel", -640, 1],
  ["acct_chk", "Mortgage Payment — Chase", "Housing", -2870, 1],
  ["acct_chk", "Consulting Income — Meridian Health", "Income", 4500, 1],
  ["acct_trust", "Monthly distribution to checking", "Transfer", -9000, 1],
  ["acct_chk", "Transfer from Allworth Trust", "Transfer", 9000, 1],
];
const transactions = [];
let txId = 1000;
for (let mi = 8; mi < 12; mi++) {
  const [y, m] = months[mi].split("-").map(Number);
  for (const [acct, merchant, cat, amt, perMonth] of txTemplates) {
    for (let k = 0; k < perMonth; k++) {
      const day = 1 + Math.floor(rand() * 27);
      transactions.push({
        id: `tx_${txId++}`,
        accountId: acct,
        date: `${y}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
        merchant, category: cat,
        amount: r0(jitter(amt, Math.abs(amt) > 2000 ? 0 : 0.18)),
      });
    }
  }
}
transactions.push(
  { id: `tx_${txId++}`, accountId: "acct_trust", date: "2026-06-10", merchant: "Quarterly dividend distribution", category: "Income", amount: 12400 },
  { id: `tx_${txId++}`, accountId: "acct_sav", date: "2026-06-04", merchant: "Lake Cities Realty — earnest deposit refund", category: "Housing", amount: 5000 },
);
transactions.sort((a, b) => b.date.localeCompare(a.date));

// ---- Personas ----
const personas = {
  clients: [{
    id: "maya",
    name: "Maya Tran",
    age: 58,
    city: "Plano, TX",
    advisorId: "dana",
    bio: "Recently semi-retired consultant; lives partly off portfolio income.",
    avatarInitials: "MT",
  }],
  advisors: [{
    id: "dana",
    name: "Dana Whitfield",
    title: "Senior Financial Advisor, CFP®",
    avatarInitials: "DW",
  }],
};

// ---- Dana's book (Maya + 4 lightweight synthetic households) ----
const book = [
  { clientId: "maya", name: "Maya Tran", managedAssets: 2445000, heldAwayDetected: 611000, openNudges: 1, lastContact: "2026-05-21", highlight: true },
  { clientId: "hh_castillo", name: "Robert & Elaine Castillo", managedAssets: 3120000, heldAwayDetected: 188000, openNudges: 0, lastContact: "2026-06-02" },
  { clientId: "hh_raman", name: "Priya Raman", managedAssets: 1870000, heldAwayDetected: 0, openNudges: 1, lastContact: "2026-05-28" },
  { clientId: "hh_beckett", name: "Tom Beckett", managedAssets: 2410000, heldAwayDetected: 452000, openNudges: 0, lastContact: "2026-04-30" },
  { clientId: "hh_lindqvist", name: "Susan & Gary Lindqvist", managedAssets: 5230000, heldAwayDetected: 74000, openNudges: 0, lastContact: "2026-06-05" },
];

const seed = {
  generatedAt: "deterministic",
  disclaimer: "SYNTHETIC DATA — Allworth Financial demo. All personas, accounts, balances and transactions are fabricated.",
  months, personas, accounts, netWorthHistory, positions, taxLots, plan, spending, transactions, book,
  liquidityEvent: {
    label: "SpaceX IPO allocation",
    amount: 200000,
    deadline: "2026-06-15",
    note: "Maya was offered access to a SpaceX IPO allocation through a former client; deciding whether to fund $200K.",
  },
};

writeFileSync(OUT, JSON.stringify(seed, null, 2));
const nw = netWorthHistory[11].value;
const heldAway = accounts.filter(a => a.group === "outside" && a.type !== "liability").reduce((s, a) => s + a.balance, 0);
const last3 = spending.slice(9).reduce((s, m) => s + m.total, 0) / 3;
console.log(`seed.json written. Net worth: $${nw.toLocaleString()} | Held-away: $${heldAway.toLocaleString()} | Last-3-mo spend avg: $${r0(last3).toLocaleString()} (plan $14,000)`);
