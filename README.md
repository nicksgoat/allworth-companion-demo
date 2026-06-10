# Allworth Mobile Planning App

Mobile-first financial planning assistant built around a chat interface, structured planning inputs, portfolio review cards, and a Python API that can run in demo mode or delegate to the existing Allworth plugin tools.

## What Is Included

- Expo React Native mobile app in `apps/mobile`
- FastAPI backend in `services/api`
- Deterministic planning, portfolio, tax, and Social Security demo engines
- Adapter layer for future integration with `/home/stevenluong/Allworth_Plugin`
- Unit and API tests
- One-command setup and test scripts

## Design Docs

- [Documentation index](docs/README.md): full map of product, frontend, backend, LLM, MCP, testing, and governance docs.
- [App design](docs/APP_DESIGN.md): screen map, file responsibilities, data flow, LLM integration plan, testing plan, and production roadmap.
- [Product brief](docs/PRODUCT_BRIEF.md): product thesis, users, jobs, principles, risks, and success criteria.
- [Frontend](docs/FRONTEND.md): Expo app structure, screen responsibilities, state flow, styling approach, and refactor plan.
- [Backend API](docs/BACKEND_API.md): FastAPI routes, orchestration, tool adapter, endpoint behavior, and service boundaries.
- [Data contracts](docs/DATA_CONTRACTS.md): mobile/backend payloads, response types, and versioning guidance.
- [LLM chat plan](docs/LLM_CHAT_PLAN.md): hybrid LLM architecture, model modes, safety, prompts, and rollout steps.
- [MCP and plugin integration](docs/MCP_INTEGRATION.md): sanctioned MCP connector boundary, previous module integration, and plugin path.
- [Client intelligence layer](docs/CLIENT_INTELLIGENCE_LAYER.md): governed memory, learning loops, fact atoms, and advisor briefs.
- [Safety and compliance](docs/SAFETY_COMPLIANCE.md): safety boundaries, audit trail, advice limits, and demo hygiene.
- [Testing and operations](docs/TESTING_OPERATIONS.md): setup, run commands, preview modes, and test plan.
- [Roadmap](docs/ROADMAP.md): phased delivery plan from prototype to production.
- [Architecture](docs/ARCHITECTURE.md): high-level frontend/backend/tool-adapter architecture.

## Quick Start

```bash
./scripts/setup.sh
./scripts/test.sh
./scripts/dev-api.sh
```

In a second terminal:

```bash
./scripts/dev-mobile.sh
```

The API defaults to `http://127.0.0.1:8000`. For physical devices, set `EXPO_PUBLIC_API_URL` to your machine LAN IP before starting Expo.

## Product Shape

The app is intentionally not a raw tool catalog. Users interact through:

- **Chat**: ask planning, tax, and portfolio questions
- **Plan**: edit household assumptions
- **Portfolio**: review allocation, drift, risk, and tax opportunities
- **Actions**: advisor-ready next steps

## Backend Modes

The backend currently runs deterministic demo tools so it works immediately.

Later, set:

```bash
export ALLWORTH_PLUGIN_ROOT=/home/stevenluong/Allworth_Plugin
export MOBILEAPP_TOOL_MODE=plugin
```

Then replace the adapter calls in `services/api/app/tool_adapter.py` with direct calls into the public facade once the production API contract is finalized.

## Safety

The app is designed for planning assistance, scenario comparison, and advisor preparation. It should not place trades, send tax instructions, or make final legal/tax recommendations without advisor review.
