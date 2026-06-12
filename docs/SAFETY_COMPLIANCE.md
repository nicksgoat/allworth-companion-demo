# Safety And Compliance

## Core Rule

The app can educate, prepare, and summarize. It should not execute financial decisions or present final tax, legal, or investment advice without advisor review.

## Current Safety Posture

The prototype:

- Uses synthetic data.
- Runs deterministic demo calculations.
- Includes educational disclaimers in tool results.
- Does not persist client memory.
- Does not place trades or modify accounts.

## Prohibited Actions

The app should not:

- Place trades.
- Transfer money.
- Open accounts.
- Submit tax forms.
- Provide final legal advice.
- Make guarantees about performance.
- Invent missing financial data.

## High-Risk Topics

Use extra caution for:

- Roth conversions.
- Tax-loss harvesting.
- Social Security claiming.
- Withdrawal strategy.
- Concentrated stock sales.
- Estate planning.
- Insurance changes.
- Any recommendation that triggers tax or legal consequences.

## Required Disclosures

Responses involving planning outputs should communicate:

- Outputs are estimates.
- Live data may be incomplete.
- Tax/legal/investment decisions require qualified review.
- Assumptions affect results.

## LLM Safety Requirements

When LLM mode is added:

- Deterministic tools remain source of calculations.
- Model cannot override tool outputs.
- Model cannot claim live data access unless source confirms it.
- Model must distinguish "consider" from "do."
- Safety layer should detect prohibited action requests.
- Audit log should capture prompt version and tool calls.

## Advisor Review Workflow

High-impact recommendations should create:

- Advisor brief.
- Client-friendly explanation.
- Action rationale.
- Open assumptions.
- Suggested meeting agenda.

They should not directly create:

- Trade order.
- Tax instruction.
- Binding recommendation.

## Audit Trail

Production logs should include:

- User ID and household ID.
- Request timestamp.
- Input message.
- Tool called.
- Tool inputs and outputs.
- LLM provider/model.
- Prompt version.
- Safety decision.
- Response ID.
- Advisor action ID if created.

## Data Governance

If client intelligence is persisted, every fact needs:

- Source.
- Timestamp.
- Confidence.
- Status.
- Owner.
- Retention rule.
- Deletion/supersession path.

## Demo Hygiene

All demos should label:

- Synthetic data.
- Redacted real-data examples.
- Read-only connector runs.
- Non-production persistence.

Do not include raw client identity in docs, screenshots, test fixtures, or prompt examples.
