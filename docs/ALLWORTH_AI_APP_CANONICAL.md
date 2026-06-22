# Allworth AI App Canonical Specification

## Summary

This is the consolidated source of truth for the Allworth AI mobile planning
application. It pulls together the product vision, current backend architecture,
frontend contract, financial tooling, memory design, safety posture, operations,
and roadmap that were previously spread across the docs folder.

The original product vision has been merged here: give each Allworth client the
feeling of a brilliant, always-available financial advisor who knows their
goals, portfolio, constraints, and concerns, while still keeping real financial
decisions under advisor review.

The current implementation uses a React Native / Expo frontend, a FastAPI
backend, deterministic financial tools, seeded and Synapse-shaped data, Redis
short-term chat memory, and an LLM provider layer. For now, the target LLM is
ChatGPT through Azure OpenAI GPT-4o. The backend should remain provider-neutral
so the app can later run on Azure OpenAI, OpenAI, Anthropic, local models, or an
AI gateway without changing frontend contracts or financial tool schemas.

## Product Vision

Most wealth applications are dashboards. This app should be a conversational
planning companion.

A client should be able to ask:

```text
Can I retire in 2027?
```

and receive a personalized answer based on household profile, portfolio state,
goals, plan documents, model allocations, and Monte Carlo projections. The
answer should use plain English, show uncertainty, cite the tools or data that
grounded it, and open a natural next step such as:

```text
Want me to show what changes if you retire one year later?
```

The app should not feel like a catalog of tools. The tools exist behind the
conversation so the client can move smoothly between:

- "What should I understand?"
- "Show me the numbers."
- "What should I ask my advisor?"
- "What changed since last time?"

## Product Principles

- Chat first, dashboard second.
- Calculations come from deterministic tools, not freeform model text.
- Insights are written like advisor preparation, not trade instructions.
- Every important number has context and provenance.
- The client can tell when data is synthetic, stale, cached, or live.
- High-impact recommendations route to advisor review.
- Memory improves continuity, but governed long-term memory must have consent,
  provenance, retention, deletion, and review controls.
- The app remains useful when one dependency is degraded, but production live
  data should not silently fall back to seed data unless an explicit emergency
  fallback is enabled.

## Current User Surfaces

The application has four major client-facing surfaces:

- **Chat**: primary interface for planning questions, model explanations,
  projections, rebalancing analysis, follow-ups, and advisor-prep language.
- **Goals**: retirement and household goals, progress, confidence, and scenario
  framing.
- **Portfolio**: allocation, drift, model comparison, concentration,
  unrealized gains, rebalancing, and tax-aware implications.
- **Advisor**: advisor profile, meeting preparation, suggested questions,
  action summaries, and future advisor brief workflows.

The frontend should not know about LLM provider details, Synapse queries, MCP
transport, Redis, or tool routing internals. It talks to the backend through
stable API contracts.

## Runtime Architecture

```text
React Native / Expo
  -> FastAPI backend
  -> provider-neutral LLM interface
       -> Azure OpenAI GPT-4o today
       -> OpenAI / Anthropic / local / gateway providers later
  -> tool router
       -> canonical Allworth tools
       -> financial tools: simulate and rebalance
       -> read-only MCP surface where appropriate
  -> data adapters
       -> seed data for local development and CI
       -> Synapse-shaped warehouse adapters for production data
  -> Redis
       -> short-term conversation memory
  -> logs / audit / feedback
```

The backend is intentionally stateless across application instances. Signed
tokens, request-scoped context, Redis-backed short-term memory, external data
stores, and stdout/audit logging allow the app to scale horizontally without
process-local sessions.

## Current Repository Map

Current backend implementation:

```text
backend/allworth_api/app.py
backend/allworth_api/config.py
backend/allworth_api/routes/
backend/allworth_api/core/chat_service.py
backend/allworth_api/core/tool_runner.py
backend/allworth_api/core/tool_defs.py
backend/allworth_api/core/vision_tools.py
backend/allworth_api/core/conversation_memory.py
backend/allworth_api/core/feedback.py
backend/allworth_api/core/rate_limit.py
backend/allworth_api/core/observability.py
backend/allworth_api/data/llm.py
backend/allworth_api/data/seed.py
backend/allworth_api/data/synapse.py
backend/allworth_api/data/redis_client.py
backend/allworth_api/financial_tools/tools.py
backend/allworth_api/financial_tools/compute.py
backend/allworth_api/financial_tools/data.py
backend/allworth_api/financial_tools/router.py
backend/allworth_api/mcp.py
```

Current frontend implementation:

```text
frontend/App.tsx
frontend/src/api.ts
frontend/src/types.ts
frontend/src/components/
frontend/src/screens/
```

Some older docs still mention an earlier `services/api` and `apps/mobile`
prototype. Treat those as historical references unless this canonical document
or current source code points there explicitly.

## LLM Strategy

The near-term model path is:

```text
LLM_PROVIDER=azure_openai
LLM_CHAT_MODEL=<Azure OpenAI deployment name for GPT-4o>
LLM_EXTRACT_MODEL=<Azure OpenAI deployment name for GPT-4o or smaller extractor>
```

Important Azure OpenAI detail: the model value sent to Azure is the deployment
name, which may or may not equal `gpt-4o`.

The model is responsible for:

- understanding the user's question,
- selecting the right tool,
- explaining tool outputs clearly,
- asking follow-up questions,
- summarizing advisor-ready next steps,
- being honest about assumptions and uncertainty.

The model is not responsible for:

- inventing portfolio values,
- overriding deterministic calculations,
- placing trades,
- making tax or legal determinations,
- claiming live data access without a confirmed live source,
- fabricating model names or allocation weights.

## Provider-Neutral LLM Boundary

The app should remain LLM-agnostic through a single provider interface. Provider
implementations can format messages, tool schemas, tool results, streaming
events, retries, timeouts, and token estimates differently, but the rest of the
backend should see the same internal events.

Provider-neutral requirements:

- Keep provider credentials only on the backend.
- Keep frontend APIs unchanged when switching model vendors.
- Keep tool schemas independent of provider-specific JSON formats.
- Normalize streaming events into shared backend events.
- Log provider, model or deployment name, latency, estimated token use, tool
  calls, tool errors, and final sources.
- Validate model or deployment names clearly during readiness checks.

Longer term, Azure API Management or another AI gateway can sit in front of the
LLM provider for quotas, routing, safety policies, cost attribution, semantic
caching, and centralized governance.

## Canonical Tool Suite

The product vision describes five canonical tools. In the current backend these
are implemented as facade tools over more focused data and financial services:

- `get_client_context`
- `get_portfolio_analytics`
- `run_monte_carlo`
- `run_mock_rebalance`
- `get_document`

These tools create the product-level assistant experience:

- context: "Who is this client and what matters to them?"
- analytics: "Where is the portfolio today?"
- simulation: "What might happen under different futures?"
- rebalance: "What would need to change to move toward target?"
- documents: "What qualitative intent or plan context should shape the answer?"

## Financial Tool Surface

The production-facing financial tool surface stays intentionally small:

- `simulate`: deterministic-seed Monte Carlo simulator.
- `rebalance`: deterministic mock model rebalancer with tax-aware sell limits.

This narrow surface is a feature, not a limitation. It keeps the LLM/tooling path
fast, auditable, repeatable, and easy to test.

Use `simulate` for projection, affordability, retirement, savings, withdrawal,
and scenario questions.

Use `rebalance` for allocation drift, model comparisons, tax-aware rebalancing,
realized gains budgets, tax budgets, and exact target model retrieval.

The rebalancer should use model names and weights from data shaped after:

| Purpose | Source |
| --- | --- |
| Model metadata | `tho.model_list` |
| Security-level target weights | `tho.Asset_Allocation_Security_Weights` |

The seeded local data currently includes AWF Core-Satellite models for local
development and CI. Model names returned to users must come from tool output,
for example:

```text
AWF - Core-Satellite - 60/40
```

The assistant should not substitute generic labels such as "60/40
growth-and-income model" when a precise model name exists in the data.

## Why A Deterministic Rebalancer

A simple deterministic rebalancer is the right current design because the
business need is speed, reproducibility, and explainability.

The rebalancer:

1. Reads the target allocation from explicit input or the selected model.
2. Normalizes weights when needed.
3. Computes current value by ticker.
4. Computes target value by ticker.
5. Finds overweight securities to sell.
6. Sells lots in a deterministic tax-aware order.
7. Respects long-term and short-term realized gain budgets.
8. Respects optional tax budgets using configured rates.
9. Allocates allowed proceeds to underweight securities.
10. Returns residual drift so the advisor can see what the budget prevented.

An optimizer can come later if the product needs account-location rules,
transaction costs, min-trade sizes, cash minimums, wash-sale windows, risk-factor
constraints, or multi-objective tax-loss harvesting. It is not required for the
current product.

## Monte Carlo In Plain English

The Monte Carlo simulator answers: "If markets have many possible futures, how
often does this plan still work?"

It takes a starting portfolio, annual contributions or withdrawals, expected
return, volatility, number of years, and a goal amount. It then runs many
deterministic-seed scenarios and summarizes the distribution:

- low-end outcome,
- middle outcome,
- high-end outcome,
- chance of reaching the goal,
- chance of depleting the portfolio or missing the goal.

The exact result is educational planning analysis. It is not a guarantee.

## Rebalancer Tax Calculation In Plain English

For each sell lot, the rebalancer estimates realized gain and taxes by
proportion:

```text
gain ratio = max(lot value - lot cost basis, 0) / lot value
realized gain = actual sell amount * gain ratio
cost basis sold = actual sell amount - realized gain
estimated tax = realized gain * tax rate
```

Long-term and short-term gains are tracked separately. If a realized gains
budget or tax budget is supplied, the tool stops selling before crossing that
budget. This can leave residual drift, which is important because the advisor
needs to know what the tax constraint prevented.

## Data Modes

The backend supports seeded data for local development and CI and Synapse-shaped
data for live integrations.

Rules:

- Seed data is allowed in local development, demos, tests, and CI.
- `DATA_MODE=live` should be strict in production.
- Live mode should not silently fall back to seed data unless an explicit
  emergency or development fallback flag is enabled.
- Synthetic values should be labeled in UI or response metadata.
- Data returned to the LLM should include provenance where possible.

## Memory Strategy

There are two different kinds of memory.

Short-term conversation memory:

- implemented with Redis,
- keyed by `conversationId`,
- stores recent user and assistant turns,
- has a TTL,
- keeps the backend stateless across instances,
- helps the LLM answer follow-up questions naturally.

Long-term governed client memory:

- not the same as Redis chat history,
- should live in a durable store,
- should be built from episodes and fact atoms,
- requires consent, retention, deletion, provenance, and review controls,
- should support client transparency, advisor briefs, product nudges, and
  compliance audit views.

Redis should not become the permanent client intelligence database. It is the
short-term conversational scratchpad.

## Client Intelligence Layer

The future intelligence layer should improve through external data structures,
not by retraining the model on client data.

Recommended learning loops:

- per-client learning: facts and preferences improve that client's experience;
- cross-client learning: anonymized patterns improve rules and briefs;
- outcome learning: nudges and advisor actions are measured by downstream
  outcomes.

Recommended storage layers:

- episode store for conversations, notes, transactions, and approved transcripts;
- fact atoms with source, confidence, status, timestamps, and supersession;
- graph edges linking facts to accounts, goals, people, advisors, tax topics,
  preferences, and life events;
- generated views for clients, advisors, compliance, and product operations.

## Frontend Contract

The frontend should treat the backend as the source of truth for:

- authentication and household scoping,
- system prompts,
- tool execution,
- LLM provider choice,
- memory retrieval and persistence,
- safety labels,
- source metadata,
- suggested follow-ups.

Important payload concepts:

- `conversationId`: identifies the Redis short-term memory thread.
- `message`: the user's current message.
- `clientId` or household identity: scoped by auth and backend authorization.
- streamed events: text deltas, tool start/end, errors, done metadata.
- `suggested_prompts`: contextual follow-up chips.
- sources and tool metadata: visible enough for trust and debugging.

The frontend may keep local UI state for responsiveness, but durable session
state belongs behind authenticated backend APIs.

## Backend API Principles

Keep public interfaces stable unless a safety issue requires change.

Operational endpoints:

```text
GET /api/health/live
GET /api/health/ready
```

Financial tool endpoints:

```text
POST /tools/simulate
POST /tools/rebalance
```

Chat endpoint:

```text
POST /api/chat
```

Feedback endpoint:

```text
POST /api/chat/feedback
```

Admin, demo, and seed-login routes should be hidden or disabled in production.

MCP should remain a backend capability layer. Do not put MCP credentials,
connector names, or transport concerns in the mobile app. Keep MCP read-only for
now and do not expose profile writes or mutation tools through MCP.

## Authentication And Household Scoping

Current local/demo behavior uses stateless signed tokens and controlled demo
paths. Production should move to Entra ID or another enterprise identity track
before exposing real client data.

Production rules:

- Disable demo passcode login.
- Disable seed email auth.
- Disable `X-Household-Id` fallback.
- Scope dashboard, portfolio, spending, profile, chat, and advisor routes to
  the authenticated household.
- Keep tokens stateless and short-lived.
- Keep secrets out of frontend build-time config.

## Safety And Compliance

Core rule:

```text
The app can educate, prepare, and summarize. It should not execute financial
decisions or present final tax, legal, or investment advice without advisor
review.
```

The app must not for now:

- place trades,
- transfer money,
- open accounts,
- submit tax forms,
- provide final legal advice,
- make guarantees about performance,
- invent missing financial data.

Responses involving planning outputs should disclose:

- outputs are estimates,
- assumptions matter,
- live data may be incomplete,
- tax/legal/investment decisions require qualified review.

Audit records should capture request id, household id hash, timestamp, route,
tool calls, tool inputs and outputs where appropriate, provider, model or
deployment, prompt version, safety decisions, sources, and error class.

## Observability

Use structured JSON logs. Minimum useful fields:

- request id,
- endpoint,
- status,
- latency,
- household id hash,
- LLM provider,
- model or deployment,
- tool calls,
- tool errors,
- estimated token use,
- source list,
- error class.

Metrics to add or track:

- request latency,
- error rate,
- active chat streams,
- LLM latency,
- LLM failures,
- tool latency,
- tool errors,
- Synapse latency,
- Redis latency,
- rate-limit events,
- feedback ratings.

Fly.io can start with stdout logs and external drains. Azure should use
Application Insights or OpenTelemetry.

## Rate Limits And Cost Controls

The app should protect expensive and high-risk surfaces:

- chat,
- login,
- auth failures,
- simulation,
- rebalancing,
- feedback,
- Synapse reads.

For one instance, app-level rate limits are acceptable. For multiple instances,
move limits to Redis, Fly edge controls, Azure API Management, or another shared
layer.

LLM cost controls:

- cap max tool rounds,
- configure max chat tokens,
- configure max extraction tokens,
- track estimated tokens,
- track tool count,
- add per-user or per-household chat limits,
- use a gateway later for quotas, routing, and attribution.

## Deployment Model

Near term deployment target:

- Fly.io for the backend.
- Redis on Fly for short-term chat memory.
- Azure OpenAI GPT-4o for the LLM.
- Seed or Synapse-shaped data depending on environment.
- Expo or native builds for the mobile frontend.

Future Azure path:

- Azure Container Apps or App Service for the backend.
- Azure Cache for Redis for session memory.
- Azure OpenAI behind Azure API Management if gateway controls are needed.
- Application Insights / OpenTelemetry for observability.
- Entra ID for production authentication.
- Managed database or read model for app-ready household context.
- Synapse or downstream curated stores for warehouse-backed data.

Backend runtime secrets should include:

```text
SESSION_SECRET
CORS_ORIGINS
LLM_PROVIDER
LLM_CHAT_MODEL
LLM_EXTRACT_MODEL
AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY
AZURE_OPENAI_API_VERSION
DATA_MODE
REDIS_URL
CHAT_MEMORY_ENABLED
```

Never expose Azure OpenAI keys or other backend secrets through Expo
`EXPO_PUBLIC_*` variables.

## Production Readiness Checklist

Before serving real clients:

- Production config validation passes.
- `/api/health/live` and `/api/health/ready` reflect actual readiness.
- Entra/SSO or another production identity path is implemented.
- Demo login and household header fallback are disabled.
- Live data mode fails closed when Synapse or required data is unavailable.
- LLM provider timeouts and bounded retries are configured.
- Wrong model/deployment names fail clearly.
- Redis memory is enabled with appropriate TTL.
- Long-term memory is disabled or governed.
- Rate limits protect chat, auth, simulation, and rebalancing.
- Structured logs and metrics are available.
- Financial tool outputs are deterministic and tested.
- Model names and allocation weights come from data-shaped schemas.
- Frontend shows synthetic/stale/live data states correctly.
- Advisor-review language appears for high-impact recommendations.
- No backend secrets exist in frontend config.

## Testing Strategy

Required test groups:

- production config validation,
- liveness/readiness,
- auth and household scoping,
- live-mode strictness,
- LLM unavailable/timeout/wrong-config behavior,
- tool-use assertions for simulation and rebalancing,
- exact AWF model-name regression cases,
- Monte Carlo deterministic output,
- tax-aware rebalancer output including realized gains and tax budgets,
- rate limits,
- Redis memory read/write/failure behavior,
- MCP smoke tests,
- frontend contract and TypeScript checks.

LLM evaluation cases should include:

- retirement projection,
- affordability scenario,
- rebalance request,
- exact model-name retrieval,
- tax-budget rebalance,
- unsupported trade/tax/legal request,
- follow-up that depends on Redis conversation memory.

## Experience Principles From The Original Vision

The original product thesis was that the app should feel less like a financial
dashboard and more like a financially literate companion. The technology is not
the magic by itself. The feeling comes from the following product behaviors:

- **It knows the client without asking**: the opening experience should already
  understand household context, current nudges, portfolio state, advisor, and
  active goals.
- **It answers the question behind the question**: if the client asks about
  portfolio performance, the answer should connect performance to plan
  confidence, goal timing, risk, and advisor review.
- **It is honest about uncertainty**: outputs should show downside cases,
  assumptions, and trade-offs rather than simplistic green/yellow/red claims.
- **Every answer opens a door**: each response should create a useful next step,
  such as a contextual follow-up, a scenario, a rebalance view, or an advisor
  handoff.
- **It remembers appropriately**: Redis short-term memory supports conversational
  continuity now; governed durable memory later should preserve important
  client preferences, goals, concerns, and decisions with provenance.

These principles are the test for whether the app feels like an AI experience
rather than a portal with a chat box.

## Engineering Priorities For A Conversational Experience

The original engineering guide listed implementation choices that create the
feeling of a live advisor conversation. They remain valid, but the current
canonical implementation narrows and governs them:

1. **Streaming responses**: keep Server-Sent Events so answers begin quickly and
   tool activity is visible without blocking the whole interaction.
2. **Cached session context**: use Redis and safe server-side caches for
   short-lived context that does not need to hit Synapse repeatedly within a
   conversation.
3. **Parallel independent work**: run independent data fetches concurrently when
   composing dashboard or advisor context, while preserving household scoping.
4. **Optimistic UI**: render the user's message immediately, show tool chips as
   work begins, and avoid dead loading states.
5. **Dynamic follow-up suggestions**: generate suggestions from latest user
   intent, answer text, tool sources, active nudges, and profile facts. Avoid
   static demo-only chips.
6. **Graceful degradation**: when LLM or data dependencies fail, explain what is
   unavailable. In production live-data mode, do not silently replace missing
   live data with seed data unless an explicit emergency fallback is enabled.
7. **Conversation context management**: use Redis for recent turns and summarize
   or retrieve older context only when durable governed memory exists.
8. **Response quality signal**: keep thumbs up/down feedback tied to
   conversation id, sources, and tool calls so the app can improve over time.

The product should only add proactive notifications, churn prediction, or
behavioral analytics after consent, privacy, supervision, and retention policies
are approved.

## Enterprise Value And Moat

The moat is not simply "an AI app." The moat is the governed intelligence loop
created when client questions, advisor handoffs, tool usage, portfolio context,
and outcomes are safely connected.

Long-term compounding advantages:

- **Behavioral insight**: repeated client questions reveal anxieties, upcoming
  life events, consolidation opportunities, and moments when advisor outreach is
  valuable.
- **Advisor productivity**: routine explanations and pre-meeting summaries can
  help advisors focus time on judgment, planning, and relationship work.
- **Switching cost through continuity**: useful memory makes the relationship
  feel continuous, but only if clients can understand, review, and delete what
  is remembered.
- **Early risk signals**: declining engagement, withdrawal questions, repeated
  concern patterns, or unresolved nudges can eventually support supervised
  retention workflows.
- **Data flywheel**: better governed usage data leads to better prompts, better
  tools, better nudges, and better advisor prep.

This value depends on data quality and governance. Bad data, opaque memory, or
ungrounded LLM answers would destroy trust faster than they create leverage.

## Roadmap

Phase 1: harden the current Fly production path.

- Validate production config.
- Keep readiness checks meaningful.
- Keep live data strict.
- Keep GPT-4o on Azure OpenAI working through the provider-neutral layer.
- Keep Redis session memory working.
- Expand auth, scoping, and rate-limit tests.

Phase 2: improve LLM quality.

- Add golden eval fixtures.
- Tighten prompts and tool descriptions.
- Log tool calls and sources.
- Enforce exact model-name behavior.
- Keep financial reasoning constrained to `simulate` and `rebalance`.

Phase 3: prepare for stateless multi-instance scale.

- Move rate limits to a shared layer.
- Move long-term profile memory and chat history to durable stores before
  enabling governed memory.
- Move background extraction to a queue/worker.
- Centralize audit and app logs.

Phase 4: prepare Azure architecture.

- Add Entra/SSO.
- Add Application Insights or OpenTelemetry.
- Add Azure Cache for Redis.
- Add Azure API Management as an AI gateway if desired.
- Add managed read models for app-ready household data.

Phase 5: build the compounding intelligence loop.

- Persist governed episodes and fact atoms.
- Add advisor briefs.
- Add outcome learning.
- Add proactive nudges.
- Add churn and consolidation opportunity signals after governance is ready.

## Documentation Map

Use this document first. The old scattered planning docs were removed after this
consolidation. The surviving docs are intentionally small:

- `FINANCIAL_TOOLS.md`: exact `simulate` and `rebalance` schemas and behavior.
- `REDIS_CHAT_MEMORY.md`: Redis setup for short-term conversation memory.
- `TESTING_OPERATIONS.md`: local run, testing, and GPT-4o deployment notes.
- `README.md`: documentation index.

## Final Operating Thesis

The app should feel personal because it remembers context, but it should remain
safe because every financial number comes from controlled tools and governed
data. GPT-4o provides the conversational layer today. The backend architecture
must keep that model replaceable tomorrow.
