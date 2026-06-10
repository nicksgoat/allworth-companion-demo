import test from "node:test";
import assert from "node:assert/strict";

import {
  defaultHousehold,
  defaultPortfolio,
  formatCurrency,
  largestDrift,
  portfolioTotal,
  updateHouseholdField
} from "../src/lib/planningLogic.mjs";

test("formats currency for planning cards", () => {
  assert.equal(formatCurrency(1250000), "$1,250,000");
});

test("computes portfolio total", () => {
  assert.equal(portfolioTotal(defaultPortfolio), 1100000);
});

test("computes largest drift as a stable positive decimal", () => {
  const drift = largestDrift(defaultPortfolio);
  assert.ok(drift > 0);
  assert.ok(drift < 0.1);
});

test("updates numeric household fields as numbers", () => {
  const next = updateHouseholdField(defaultHousehold, "retirement_age", "62");
  assert.equal(next.retirement_age, 62);
});

