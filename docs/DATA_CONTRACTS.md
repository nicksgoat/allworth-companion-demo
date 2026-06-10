# Data Contracts

## Purpose

This document describes the payloads shared by the Expo mobile app and FastAPI backend.

Backend source of truth:

- [services/api/app/models.py](/home/stevenluong/MobileApp/services/api/app/models.py)

Frontend type mirror:

- [apps/mobile/src/api.ts](/home/stevenluong/MobileApp/apps/mobile/src/api.ts)

## Chat Message

```ts
type ChatMessage = {
  role: "user" | "assistant" | "system";
  content: string;
};
```

Notes:

- The frontend currently sends prior messages with every request.
- Production should add server-side conversation IDs and retention policy.
- System messages should be backend-controlled in production.

## Household Profile

```ts
type HouseholdProfile = {
  primary_age: number;
  spouse_age?: number | null;
  retirement_age: number;
  annual_income: number;
  annual_expenses: number;
  portfolio_value: number;
  annual_savings: number;
  filing_status: "single" | "married_filing_jointly";
  effective_tax_rate: number;
  risk_tolerance: "conservative" | "moderate" | "growth";
};
```

Validation rules are enforced by Pydantic in the backend.

Production guidance:

- Add field provenance.
- Add last-updated timestamps.
- Distinguish client-entered assumptions from system-of-record facts.
- Version household profile payloads before connecting live data.

## Portfolio Position

```ts
type PortfolioPosition = {
  symbol: string;
  name: string;
  asset_class: string;
  value: number;
  cost_basis: number;
  target_weight: number;
};
```

Production additions:

- Account ID.
- Custodian.
- Security ID.
- Tax lot IDs.
- Unrealized gain/loss.
- Qualified/non-qualified account type.
- Data freshness timestamp.

## Tool Result

```ts
type ToolResult = {
  tool: string;
  summary: string;
  cards: MetricCard[];
  actions: AdvisorAction[];
  data: Record<string, unknown>;
  disclaimers: string[];
};
```

Tool results are the structured bridge between calculations and chat explanations.

Rules:

- `summary` should be concise and human-readable.
- `cards` should contain display-ready metrics.
- `actions` should be advisor-prep next steps.
- `data` can contain richer machine-readable details.
- `disclaimers` should travel with tool results.

## Metric Card

```ts
type MetricCard = {
  label: string;
  value: string;
  tone: "good" | "warning" | "danger" | "neutral";
  detail?: string;
};
```

Display guidance:

- Keep `label` short.
- Keep `value` already formatted.
- Use `tone` for UI styling only.
- Do not infer legal, tax, or trading safety from `tone`.

## Advisor Action

```ts
type AdvisorAction = {
  title: string;
  priority: "high" | "medium" | "low";
  rationale: string;
};
```

Production additions:

- Action owner.
- Due date.
- CRM task ID.
- Approval status.
- Source tool/model trace.
- Client-visible vs advisor-only flag.

## Chat Response

```ts
type ChatResponse = {
  answer: string;
  intent: string;
  result: ToolResult;
  suggested_prompts: string[];
};
```

Future additions:

```ts
type FutureChatResponse = ChatResponse & {
  conversation_id: string;
  message_id: string;
  trace_id: string;
  sources: SourceReference[];
  safety: SafetyMetadata;
};
```

## Contract Versioning

Recommended approach:

- Add `contract_version` to API responses before production integrations.
- Version breaking changes through `/api/v1`.
- Keep frontend response parsing tolerant of added fields.
- Use backend tests to lock expected route behavior.

## Synthetic Data Labeling

Any synthetic value should be labeled in UI or response metadata before wider demo use.

Examples:

- Synthetic advisor profile.
- Synthetic Robinhood/NVDA concentration insight.
- Demo household assumptions.
- Demo portfolio holdings.
