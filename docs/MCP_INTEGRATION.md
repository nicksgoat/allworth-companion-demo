# MCP And Plugin Integration

## Purpose

This document describes how Model Context Protocol connectors, previous Allworth modules, and future production planning engines should fit into this app.

## Current State

The current repo does not directly call MCP tools from the mobile app.

Instead, it has a clean backend boundary:

```text
Mobile app
  -> FastAPI backend
  -> ToolAdapter
  -> demo tools today
  -> future plugin or MCP-backed services
```

This is intentional. Mobile clients should not know about MCP transport, connector names, credentials, or internal tool routing.

## Financial Tool Registry

Financial planning tools are now registered in one backend module:

```text
backend/allworth_api/financial_tools/tools.py
```

That registry owns:

- `FINANCIAL_TOOL_DEFINITIONS` for LLM/MCP schemas.
- `FINANCIAL_TOOL_LABELS` for UI progress labels.
- `FINANCIAL_TOOL_NAMES` for routing.
- `run_financial_tool(...)` for execution.

The same contracts are consumed by:

- FastAPI endpoints under `/tools/...`
- Chat tool-calling through `core/tool_defs.py` and `core/tool_runner.py`
- MCP stdio server through `backend/allworth_api/mcp.py`

This keeps the data/compute/decision tools composable while avoiding duplicate schemas across HTTP, chat, and MCP.

## Existing Hook

[services/api/app/tool_adapter.py](/home/stevenluong/MobileApp/services/api/app/tool_adapter.py) already anticipates future plugin mode:

```bash
MOBILEAPP_TOOL_MODE=plugin
ALLWORTH_PLUGIN_ROOT=/home/stevenluong/Allworth_Plugin
```

The adapter inserts the plugin Python root into `sys.path` when plugin mode is enabled and the plugin root exists.

## Role Of MCP

MCP should be treated as a backend capability layer, not a frontend dependency.

Possible MCP-backed capabilities:

- Read client profile from approved CRM connector.
- Read account and household data from analytics connector.
- Fetch advisor/team metadata.
- Retrieve activity history.
- Retrieve held-away asset signals.
- Create advisor briefs or task drafts through approved internal systems.

## Lessons From Previous Client Intelligence Run

The attached client intelligence brief described a read-only validation run through sanctioned MCP connectors. Important lessons for this app:

- Use read-only data access for exploration and validation.
- Do not persist client facts until governance is designed.
- Redact identity in demos and documents.
- Keep source/provenance for every extracted fact.
- Treat MCP connector outputs as source episodes, not final client truth.
- Build advisor briefs from governed facts, not one-off model memory.

## Recommended MCP Boundary

Add backend service modules such as:

```text
services/api/app/connectors/mcp_client.py
services/api/app/connectors/client_profile.py
services/api/app/connectors/activity_history.py
services/api/app/connectors/advisor_context.py
```

These modules should return normalized internal models, not raw connector payloads.

## Connector Rules

- MCP access only from backend.
- No MCP credentials in mobile.
- No raw connector payloads returned directly to mobile.
- Every connector result gets a source label and timestamp.
- Read-only first.
- Writes require separate approval and audit design.

## Plugin Integration Rules

When integrating `/home/stevenluong/Allworth_Plugin` or other previous modules:

1. Define the public facade first.
2. Keep tool inputs and outputs close to current `ToolResult`.
3. Add adapter tests before replacing demo tools.
4. Keep demo mode available for offline testing.
5. Do not leak plugin-specific names to mobile UI.

## Suggested Adapter Interface

```python
class PlanningEngine:
    async def run_planning(self, analysis, household): ...
    async def run_portfolio(self, analysis, portfolio): ...
    async def get_client_context(self, client_id): ...
    async def create_advisor_brief(self, client_id, topic): ...
```

## MCP Data To Product Mapping

| MCP/Module Data | Product Use |
| --- | --- |
| Activity history | Client intelligence episodes, advisor brief context |
| CRM household profile | Household assumptions and advisor metadata |
| Account/holding data | Portfolio screen and concentration insights |
| Future assets/held-away records | Consolidation opportunities and advisor prompts |
| Meeting notes/transcripts | Fact extraction and preference learning |
| Advisor task data | Advisor workflow and follow-up state |

## Production Concerns

- Entitlements: user can only access their own household.
- Supervision: advisor and compliance views need different permissions.
- Audit: every MCP read/write requires traceability.
- Retention: connector-derived facts need deletion and supersession.
- Consent: some client intelligence features may need explicit consent.
- Rate limits: MCP calls should be cached and batched where possible.

## Build Order

1. Keep demo mode stable.
2. Add normalized connector interfaces.
3. Add read-only MCP context fetch for advisor/profile data.
4. Add source/provenance fields to API responses.
5. Add plugin-backed planning tools.
6. Add advisor brief generation.
7. Add governed memory persistence.
