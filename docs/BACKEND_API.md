# Backend API

## Stack

- FastAPI
- Pydantic v2
- Uvicorn
- Pytest

## Application Entry

[services/api/app/main.py](/home/stevenluong/MobileApp/services/api/app/main.py) creates the FastAPI app, configures CORS, and registers the current routes.

## Routes

### `GET /health`

Returns service health and current tool mode.

Response:

```json
{
  "status": "ok",
  "tool_mode": "demo"
}
```

### `GET /api/tools/catalog`

Returns the planning and portfolio tools exposed by the adapter.

### `POST /api/chat`

Primary chat route used by the mobile app.

Flow:

```text
request
  -> answer_chat()
  -> classify_intent()
  -> ToolAdapter
  -> demo tool or future plugin/production tool
  -> ChatResponse
```

### `POST /api/tools/planning/run`

Runs a planning analysis directly.

Supported analyses:

- `retirement_readiness`
- `roth_conversion`
- `social_security`
- `withdrawal_strategy`
- `tax_optimization`

The current adapter routes unknown or unimplemented planning analyses to retirement readiness.

### `POST /api/tools/portfolio/run`

Runs a portfolio analysis directly.

Supported analyses:

- `portfolio_review`
- `tax_loss_harvesting`
- `wash_sale_check`
- `drift_analysis`

The current adapter routes unknown or unimplemented portfolio analyses to portfolio review.

## Orchestrator

[services/api/app/orchestrator.py](/home/stevenluong/MobileApp/services/api/app/orchestrator.py) currently does simple keyword intent classification.

Current intent map:

- Roth questions -> `roth_conversion`
- Social Security questions -> `social_security`
- Tax questions -> `tax_optimization`
- Loss harvesting questions -> `tax_loss_harvesting`
- Wash sale questions -> `wash_sale_check`
- Portfolio, drift, allocation, rebalance, risk -> `portfolio_review`
- Default -> `retirement_readiness`

This file is the best first place to add LLM mode because it already owns chat-level orchestration.

## Tool Adapter

[services/api/app/tool_adapter.py](/home/stevenluong/MobileApp/services/api/app/tool_adapter.py) is the boundary between product API and planning engines.

Current mode:

```bash
MOBILEAPP_TOOL_MODE=demo
```

Future mode:

```bash
MOBILEAPP_TOOL_MODE=plugin
ALLWORTH_PLUGIN_ROOT=/home/stevenluong/Allworth_Plugin
```

The adapter should remain the only route from API code to planning engines. This keeps mobile/API contracts stable when tools move from demo functions to plugin modules or production services.

## Demo Tools

[services/api/app/demo_tools.py](/home/stevenluong/MobileApp/services/api/app/demo_tools.py) contains deterministic planning functions.

Current tools:

- `retirement_readiness`
- `roth_conversion`
- `social_security`
- `tax_optimization`
- `portfolio_review`
- `tax_loss_harvesting`
- `wash_sale_check`

These functions return structured `ToolResult` objects with summaries, metric cards, advisor actions, raw data, and disclaimers.

## Production Service Boundaries

Recommended future services:

- Auth/session service.
- Client profile service.
- Account and holdings service.
- Planning calculation service.
- Tax lot service.
- Advisor CRM/task service.
- LLM orchestration service.
- Audit and supervision service.

The FastAPI app can remain a backend-for-frontend while those services mature.
