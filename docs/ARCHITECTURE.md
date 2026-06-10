# Architecture

```text
Expo Mobile App
  -> FastAPI Backend
    -> Chat Orchestrator
    -> Tool Adapter
      -> Demo Tool Engine
      -> Existing Allworth Plugin Tools, future mode
    -> Audit/Safety Metadata
```

## Frontend Responsibilities

- Capture user intent through chat and structured forms
- Render scenario cards, metrics, charts, and advisor actions
- Store only low-risk local UI state
- Never run authoritative financial calculations locally

## Backend Responsibilities

- Authenticate and authorize requests
- Normalize user inputs
- Route chat requests to the correct financial tool
- Run planning, portfolio, tax, and Social Security analyses
- Return structured cards and plain-language summaries
- Audit tool calls and safety metadata

## What Stays Out Of Mobile

- Raw warehouse SQL
- MCP transport details
- Admin diagnostics
- Custodian batch processing
- Developer route names
- Local plugin launcher code

