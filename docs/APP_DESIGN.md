# Mobile App Design

This document describes the current Allworth mobile planning app: product intent, file ownership, screen design, data contracts, local development, and the build plan from prototype to full application.

## Product Intent

The app is a mobile-first financial planning assistant. The main interface is chat, supported by planning views that help users understand goals, portfolio risk, and advisor next steps.

The experience should feel closer to a modern robo-advisor app than a tool catalog:

- Chat is the default home screen.
- Financial insights are presented as plain-language briefs.
- Structured cards summarize goals, portfolio health, and advisor actions.
- The app prepares the user for an advisor conversation rather than placing trades or giving final tax/legal advice.

## Current App Shape

The current frontend is implemented in [apps/mobile/App.tsx](/home/stevenluong/MobileApp/apps/mobile/App.tsx).

Primary tabs:

- **Chat**: main interface, account snapshot, concentration insight, guided prompts, chat thread, composer.
- **Goals**: retirement readiness, goal progress cards, editable household assumptions.
- **Portfolio**: portfolio value, allocation rows, drift, tax/rebalance recommendations.
- **Advisor**: advisor profile, message/schedule actions, advisor brief items.

The app currently uses synthetic demo data and deterministic backend tools. It is ready to be upgraded to an LLM-backed chat layer without rewriting the frontend.

## User Experience Principles

- Start with the user's question, not internal tools.
- Surface the most important planning issue first.
- Keep numbers paired with explanations.
- Use advisor-prep language, not trade instructions.
- Make recommendations actionable, but defer final execution to advisor review.
- Keep dense financial data scannable on a phone.

## Frontend File Map

| File | Responsibility |
| --- | --- |
| [apps/mobile/App.tsx](/home/stevenluong/MobileApp/apps/mobile/App.tsx) | Main React Native app shell, screens, local UI state, chat submission flow, styles. |
| [apps/mobile/index.js](/home/stevenluong/MobileApp/apps/mobile/index.js) | Expo entrypoint that registers the root app component. |
| [apps/mobile/src/api.ts](/home/stevenluong/MobileApp/apps/mobile/src/api.ts) | Frontend API client, TypeScript response types, `/api/chat` and portfolio request helpers. |
| [apps/mobile/src/lib/planningLogic.mjs](/home/stevenluong/MobileApp/apps/mobile/src/lib/planningLogic.mjs) | Local demo defaults and formatting helpers used by the UI and tests. |
| [apps/mobile/tests/planningLogic.test.mjs](/home/stevenluong/MobileApp/apps/mobile/tests/planningLogic.test.mjs) | Unit tests for currency formatting, portfolio totals, drift, and household updates. |
| [apps/mobile/app.json](/home/stevenluong/MobileApp/apps/mobile/app.json) | Expo app metadata and platform config. |
| [apps/mobile/package.json](/home/stevenluong/MobileApp/apps/mobile/package.json) | Mobile workspace dependencies and Expo scripts. |
| [apps/mobile/tsconfig.json](/home/stevenluong/MobileApp/apps/mobile/tsconfig.json) | TypeScript settings for the Expo app. |

## Backend File Map

| File | Responsibility |
| --- | --- |
| [services/api/app/main.py](/home/stevenluong/MobileApp/services/api/app/main.py) | FastAPI app, CORS, health endpoint, chat endpoint, tool endpoints. |
| [services/api/app/models.py](/home/stevenluong/MobileApp/services/api/app/models.py) | Pydantic request/response schemas shared by chat and tool routes. |
| [services/api/app/orchestrator.py](/home/stevenluong/MobileApp/services/api/app/orchestrator.py) | Chat intent classification and response assembly. This is the best place to add LLM orchestration. |
| [services/api/app/tool_adapter.py](/home/stevenluong/MobileApp/services/api/app/tool_adapter.py) | Boundary between product API and planning engines. Supports demo mode and future plugin mode. |
| [services/api/app/demo_tools.py](/home/stevenluong/MobileApp/services/api/app/demo_tools.py) | Deterministic demo engines for retirement, Roth conversion, Social Security, tax optimization, portfolio review, tax-loss harvesting, and wash-sale reminders. |
| [services/api/tests/test_api.py](/home/stevenluong/MobileApp/services/api/tests/test_api.py) | API tests for health, chat routing, portfolio tools, and validation. |
| [services/api/requirements.txt](/home/stevenluong/MobileApp/services/api/requirements.txt) | Python backend dependencies. |

## Root File Map

| File | Responsibility |
| --- | --- |
| [README.md](/home/stevenluong/MobileApp/README.md) | Project overview and quick start. |
| [docs/ARCHITECTURE.md](/home/stevenluong/MobileApp/docs/ARCHITECTURE.md) | High-level architecture sketch. |
| [docs/APP_DESIGN.md](/home/stevenluong/MobileApp/docs/APP_DESIGN.md) | This app-focused design and planning document. |
| [package.json](/home/stevenluong/MobileApp/package.json) | Root workspace scripts. |
| [package-lock.json](/home/stevenluong/MobileApp/package-lock.json) | Locked Node dependency graph. |
| [scripts/setup.sh](/home/stevenluong/MobileApp/scripts/setup.sh) | Project setup script. |
| [scripts/test.sh](/home/stevenluong/MobileApp/scripts/test.sh) | Combined test script. |
| [scripts/dev-api.sh](/home/stevenluong/MobileApp/scripts/dev-api.sh) | Starts the FastAPI backend. |
| [scripts/dev-mobile.sh](/home/stevenluong/MobileApp/scripts/dev-mobile.sh) | Starts the Expo mobile app. |

## Data Flow

```text
User types in mobile chat
  -> apps/mobile/App.tsx submitPrompt()
  -> apps/mobile/src/api.ts sendChat()
  -> POST /api/chat
  -> services/api/app/orchestrator.py answer_chat()
  -> services/api/app/tool_adapter.py
  -> services/api/app/demo_tools.py or future production/plugin/LLM mode
  -> ChatResponse
  -> mobile chat thread + result cards
```

## Chat Contract

Frontend request shape:

```ts
{
  messages: ChatMessage[];
  household: HouseholdProfile;
  portfolio: PortfolioPosition[];
}
```

Backend response shape:

```ts
{
  answer: string;
  intent: string;
  result: {
    tool: string;
    summary: string;
    cards: MetricCard[];
    actions: AdvisorAction[];
    data: Record<string, unknown>;
    disclaimers: string[];
  };
  suggested_prompts: string[];
}
```

This contract lets the app render both natural-language responses and structured financial cards.

## Current Demo Data

The current app includes:

- Household profile: age, retirement age, income, expenses, portfolio value, savings, tax rate, risk tolerance.
- Portfolio: VTI, VXUS, BND, CASH with values, cost basis, target weights.
- Concentration insight: synthetic NVDA position in Robinhood.
- Advisor profile: synthetic advisor Dana Williams.

These are placeholders for product testing. They should eventually come from authenticated customer profile, account aggregation, CRM, custodian, and planning systems.

## Backend Modes

Current:

- `MOBILEAPP_TOOL_MODE=demo`
- Deterministic Python demo tools return stable cards/actions.

Planned:

- `MOBILEAPP_TOOL_MODE=plugin`
- Adapter delegates to the Allworth plugin facade once the production API contract is finalized.

Recommended LLM mode:

- `MOBILEAPP_CHAT_MODE=llm`
- Deterministic tools compute financial outputs.
- LLM explains those outputs conversationally, asks follow-up questions, and prepares advisor-ready summaries.

## LLM Integration Plan

The safest architecture is hybrid:

1. Use deterministic tools for calculations.
2. Use the LLM for intent handling, explanation, follow-up questions, and summarization.
3. Return structured cards from tools, not from freeform model text alone.
4. Persist audit metadata for every tool call and model response.
5. Block trading, tax filing, and legal instructions without advisor review.

Suggested backend additions:

- `services/api/app/llm_client.py`: provider wrapper for OpenAI, Azure OpenAI, or local model.
- `services/api/app/prompts.py`: system/developer prompts and response style rules.
- `services/api/app/safety.py`: safety checks, disclaimer policy, blocked action detection.
- `services/api/app/audit.py`: trace IDs, tool call logs, model metadata, source references.

## Frontend Design System

Current visual direction:

- Warm off-white background.
- Deep green primary color.
- White utility cards with subtle borders.
- Compact 8px card radius.
- Bottom navigation for core product areas.
- Chat composer fixed above bottom navigation.
- Progress bars for goals and allocations.
- Ionicons for navigation and action affordances.

Important constraints:

- Keep financial cards compact and scan-friendly.
- Avoid marketing-style hero pages.
- Use structured card rows for repeat workflows.
- Keep chat primary, not hidden behind a dashboard.

## Screen Requirements

### Chat

Must support:

- Account snapshot.
- Priority insight.
- Suggested prompts.
- Message history.
- Loading and error states.
- Structured result cards.
- Composer.

Next additions:

- Suggested follow-up prompts from backend response.
- Message timestamps.
- Source/tool trace disclosure.
- Reset conversation.
- Save advisor brief.

### Goals

Must support:

- Retirement readiness.
- Multiple financial goals.
- Progress visualization.
- Editable household assumptions.

Next additions:

- Goal creation.
- Contribution recommendations.
- Scenario comparison.
- Spending and savings sensitivity.

### Portfolio

Must support:

- Total portfolio value.
- Allocation list.
- Drift estimate.
- Recommendation cards.

Next additions:

- Account-level grouping.
- Tax lot details.
- Concentration analysis.
- Risk score.
- Tax-loss harvesting workflow.

### Advisor

Must support:

- Advisor profile.
- Message action.
- Schedule action.
- Advisor brief cards.

Next additions:

- Draft message generation.
- Calendar integration.
- CRM task creation.
- Advisor-visible summary export.

## Safety And Compliance

The app should not:

- Place trades.
- Recommend final tax or legal action as definitive advice.
- Hide uncertainty or assumptions.
- Treat synthetic demo data as live financial data.

The app should:

- Label educational output clearly.
- Show assumptions when a recommendation depends on them.
- Keep deterministic calculation outputs separate from model prose.
- Log model/tool inputs and outputs in production.
- Support deletion, retention, supervision, and access controls for persisted user memory.

## Local Development

Install dependencies:

```bash
cd /home/stevenluong/MobileApp
./scripts/setup.sh
```

Start API:

```bash
cd /home/stevenluong/MobileApp
./scripts/dev-api.sh
```

Start Expo mobile:

```bash
cd /home/stevenluong/MobileApp
./scripts/dev-mobile.sh
```

Start Expo Web preview:

```bash
cd /home/stevenluong/MobileApp/apps/mobile
npx expo start --web --port 8082
```

Run tests:

```bash
cd /home/stevenluong/MobileApp
npm test
npx tsc --noEmit -p apps/mobile/tsconfig.json
./scripts/test.sh
```

## Environment Variables

| Variable | Used By | Purpose |
| --- | --- | --- |
| `EXPO_PUBLIC_API_URL` | Mobile app | Overrides API base URL. Useful for physical devices. |
| `MOBILEAPP_TOOL_MODE` | Backend | Selects demo or future plugin mode. Defaults to `demo`. |
| `ALLWORTH_PLUGIN_ROOT` | Backend | Path to future Allworth plugin integration. |
| `MOBILEAPP_CHAT_MODE` | Backend, planned | Future switch between deterministic chat and LLM-backed chat. |
| `OPENAI_API_KEY` | Backend, planned | Future LLM provider credential if using OpenAI. |

## Testing Plan

Current coverage:

- Planning logic unit tests.
- FastAPI endpoint tests.
- TypeScript compile check.

Recommended next tests:

- Component smoke tests for the four app tabs.
- API contract tests for `/api/chat`.
- LLM prompt snapshot tests once model mode is added.
- Safety tests for blocked trading/tax/legal commands.
- Mobile layout screenshots for small and large phone viewports.

## Production Build Plan

### Phase 1: Demo App Hardening

- Split `App.tsx` into screen and component files.
- Add reusable design tokens.
- Add loading, empty, and error states for each screen.
- Add structured mock data fixtures.
- Add screenshot-based UI checks.

### Phase 2: Real LLM Chat

- Add LLM client behind backend feature flag.
- Keep deterministic tools as source of financial calculations.
- Use LLM for conversational explanation and follow-up questions.
- Add audit logging and prompt/version metadata.
- Add safety filters for prohibited actions.

### Phase 3: Client Data Integration

- Authenticate user sessions.
- Replace synthetic household and portfolio data with real profile/account APIs.
- Add account aggregation and CRM/advisor context.
- Track provenance for every user-visible fact.

### Phase 4: Advisor Workflow

- Generate advisor briefs.
- Create advisor tasks.
- Draft client messages.
- Add schedule integration.
- Add review/approval flow before any outbound recommendation.

### Phase 5: Governed Memory

- Add append-only episode records.
- Extract fact atoms with provenance and confidence.
- Maintain active/superseded/deleted fact states.
- Generate client, advisor, and compliance views from the same governed memory.

## Open Decisions

- Which LLM provider should power test mode: OpenAI, Azure OpenAI, or local Ollama?
- Should chat history persist locally, server-side, or not at all for demo?
- What authentication method will be used for production?
- Which system owns household assumptions?
- Which system owns advisor task creation?
- What compliance review is required before storing client intelligence facts?

## Near-Term Checklist

- Add `MOBILEAPP_CHAT_MODE=llm` backend mode.
- Create `llm_client.py`.
- Update `/api/chat` to use deterministic tools plus LLM explanation.
- Split frontend screens out of `App.tsx`.
- Add prompt chips from backend `suggested_prompts`.
- Add advisor brief generation endpoint.
- Add production-grade audit trail design.
