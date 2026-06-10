# Product Brief

## One-Line Summary

Allworth Invest is a chat-first mobile planning assistant that helps clients understand their financial picture, prepare for advisor conversations, and act on planning opportunities with appropriate human review.

## Product Thesis

Clients do not want a raw planning tool catalog. They want to ask questions in plain language, see the most important next issue, and understand what to do with an advisor. The app should combine a conversational interface with structured financial cards so users can move between "What should I do?" and "Show me the numbers."

## Target Users

- Clients who want quick answers about retirement, portfolio risk, taxes, and goals.
- Advisors who need cleaner client context before meetings.
- Product and data teams validating a client intelligence layer.
- Internal stakeholders testing future LLM and MCP-backed planning workflows.

## Core Jobs

1. Answer planning questions conversationally.
2. Surface priority insights before the client asks.
3. Explain portfolio concentration, drift, and tax opportunities.
4. Track progress toward goals.
5. Prepare advisor-ready summaries and next steps.
6. Keep calculations grounded in controlled tools and auditable data.

## Current Product Shape

The current application has four primary surfaces:

- **Chat**: the home screen and main mode of interaction.
- **Goals**: progress toward retirement and other household goals.
- **Portfolio**: allocation, drift, concentration, and recommendations.
- **Advisor**: advisor profile, brief, message, and scheduling affordances.

## Design Principles

- Chat first, dashboard second.
- Insights should be written like advisor prep, not trading instructions.
- Every important number should have context.
- Recommendations should distinguish education from advice.
- The client should know when live data is missing.
- The app should preserve a path from insight to advisor review.

## Non-Goals For The Prototype

- No account opening.
- No trade placement.
- No tax filing.
- No legal advice.
- No permanent client memory until governance is designed.
- No production identity or entitlement model yet.

## Product Risks

- Users may over-trust model prose if safety language is weak.
- LLM answers may drift from deterministic calculations if tools are not the source of truth.
- Synthetic demo data may be mistaken for live data without clear labels.
- Advisor workflow can become noisy if every insight becomes a task.

## Success Criteria

Short term:

- Users can test the app in web or Expo Go.
- Chat can route common planning questions.
- The UI feels like a real mobile wealth application.
- Product docs explain what exists and what comes next.

Medium term:

- LLM mode can explain deterministic tool outputs.
- Advisor brief generation is useful and auditable.
- Prompt and response behavior can be tested safely.
- MCP/plugin integration has a clear boundary.

Long term:

- Client intelligence improves through governed fact extraction and outcomes.
- Advisor workflows convert insights into timely, supervised action.
- The system can explain why it believes a fact and where it came from.
