# NFBC domain playbook & schema context

## Flow vocabulary (Household_Rollforward, per reporting period)
- **inflows** = cashdeposit + receiptsecurities (money/securities coming in).
- **outflows** = cashwithdrawal + withdrawalsecurities (money/securities going out).
- **net_flows (NCNM)** = Net Client New Money — the organic flow figure that drives
  the bonus calc. Negative = net money left.
- **total_aum** = household total account value at period end.
- TTM Net Flows = trailing-twelve-month net flow on Current_Household_Fact.

## Common ticket patterns
- **Transitioned advisor**: a household moved from a previous advisor to a current one
  (`previousadvisor` populated and ≠ `sfadvisor`). Flows around the transition often
  need an adjustment so the right advisor is credited.
- **Inflow credit**: ticket states an explicit dollar amount the advisor should be
  credited (e.g. "credit $556k for 2025"). The amount in the ticket is authoritative
  input; code will subtract any existing adjustments already recorded.
- **Anomalous outflow**: a period shows a large net outflow that is a data/processing
  artifact (e.g. account processing delay, estate transfer) rather than a real client
  decision. The adjustment offsets that anomalous net flow.

## Adjustment types (classify into one)
- `Net New` — generic net-new-money adjustment (default).
- `courtesy` — goodwill/courtesy credit.
- `RD Approval` — regional director approved adjustment.
- `Account Processing Delay` — flow timing/processing artifact.
- `Transition` — advisor-transition related.
- `Estate` — estate / death / transfer event.
- `Correction` — fixing an erroneous prior figure.

## How code computes the amount (so your rationale matches)
1. If the ticket names an explicit credit amount → amount = parsed_amount − existing adjustments.
2. Else if there are anomalous periods (net < −$10k) → amount offsets the total anomalous net.
3. Period selection: a year named in the ticket → last flow period in that year; else
   the last period with a positive inflow; else the most recent period.

Write your `rationale` and `draft_reply` consistent with the data you were given.
If the data does not support an amount, say so and flag for human review.
