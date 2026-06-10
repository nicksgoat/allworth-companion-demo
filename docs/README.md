# Documentation Index

This folder is the working handbook for the Allworth mobile planning application.

> **Note:** These docs describe the target platform design and roadmap. The June 22 demo implementation lives in `app/` (React Native client + Node backend); references to `apps/mobile` and `services/api` describe the prototype these docs were authored against.

## Product And App

- [App Design](APP_DESIGN.md): current app map, UX principles, screen requirements, local development, and production roadmap.
- [Product Brief](PRODUCT_BRIEF.md): product thesis, target users, core jobs, and experience principles.
- [Frontend](FRONTEND.md): Expo app structure, screen responsibilities, state flow, styling approach, and refactor plan.

## Backend And Data

- [Backend API](BACKEND_API.md): FastAPI routes, orchestration, tool adapter, endpoint behavior, and future service boundaries.
- [Data Contracts](DATA_CONTRACTS.md): mobile/backend payloads, household profile, portfolio positions, tool results, and versioning guidance.
- [Testing And Operations](TESTING_OPERATIONS.md): setup, run commands, test strategy, preview modes, and operational notes.

## Intelligence Layer

- [LLM Chat Plan](LLM_CHAT_PLAN.md): hybrid LLM architecture, prompt responsibilities, model modes, and rollout steps.
- [MCP And Plugin Integration](MCP_INTEGRATION.md): how sanctioned MCP connectors, existing plugin modules, and future production tools should fit.
- [Client Intelligence Layer](CLIENT_INTELLIGENCE_LAYER.md): governed memory, self-improving loops, profile facts, and advisor briefs.

## Governance

- [Safety And Compliance](SAFETY_COMPLIANCE.md): financial safety boundaries, audit trail, advice limits, and controls.
- [Roadmap](ROADMAP.md): phased delivery plan from prototype to production.

## Existing Architecture

- [Architecture](ARCHITECTURE.md): high-level frontend/backend/tool-adapter sketch.
