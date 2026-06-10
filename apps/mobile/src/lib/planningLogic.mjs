export const defaultHousehold = {
  primary_age: 45,
  spouse_age: 43,
  retirement_age: 65,
  annual_income: 225000,
  annual_expenses: 145000,
  portfolio_value: 1250000,
  annual_savings: 45000,
  filing_status: "married_filing_jointly",
  effective_tax_rate: 0.28,
  risk_tolerance: "moderate"
};

export const defaultPortfolio = [
  { symbol: "VTI", name: "US Total Market", asset_class: "US Equity", value: 520000, cost_basis: 430000, target_weight: 0.45 },
  { symbol: "VXUS", name: "International Equity", asset_class: "International Equity", value: 210000, cost_basis: 235000, target_weight: 0.20 },
  { symbol: "BND", name: "Core Bonds", asset_class: "Fixed Income", value: 310000, cost_basis: 315000, target_weight: 0.30 },
  { symbol: "CASH", name: "Cash", asset_class: "Cash", value: 60000, cost_basis: 60000, target_weight: 0.05 }
];

export function formatCurrency(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0
  }).format(Number(value || 0));
}

export function portfolioTotal(positions) {
  return positions.reduce((sum, item) => sum + Number(item.value || 0), 0);
}

export function largestDrift(positions) {
  const total = portfolioTotal(positions);
  if (!total) return 0;
  return positions.reduce((max, item) => {
    const actual = Number(item.value || 0) / total;
    return Math.max(max, Math.abs(actual - Number(item.target_weight || 0)));
  }, 0);
}

export function updateHouseholdField(profile, key, value) {
  const numeric = new Set([
    "primary_age",
    "spouse_age",
    "retirement_age",
    "annual_income",
    "annual_expenses",
    "portfolio_value",
    "annual_savings",
    "effective_tax_rate"
  ]);
  return {
    ...profile,
    [key]: numeric.has(key) ? Number(value || 0) : value
  };
}

