# Roadmap

## Phase 0: Current Prototype

Status: mostly complete.

Delivered:

- Expo mobile app.
- FastAPI backend.
- Chat-first UI.
- Goals, Portfolio, Advisor tabs.
- Demo planning and portfolio tools.
- Web preview support.
- App design docs.

## Phase 1: App Hardening

Goals:

- Split large `App.tsx` into screens and components.
- Add reusable theme tokens.
- Add better empty/loading/error states.
- Use backend `suggested_prompts`.
- Improve responsive web/mobile layout.
- Add component tests.

Deliverables:

- `src/screens/*`
- `src/components/*`
- `src/theme.ts`
- Screen smoke tests.

## Phase 2: LLM Chat Mode

Goals:

- Add real LLM testing path.
- Keep deterministic tools as calculation source.
- Add prompt and safety layers.
- Add model audit metadata.

Deliverables:

- `llm_client.py`
- `prompts.py`
- `safety.py`
- `audit.py`
- `MOBILEAPP_CHAT_MODE=llm`
- Mocked LLM tests.

## Phase 3: MCP And Plugin Integration

Goals:

- Connect read-only approved data sources.
- Normalize connector outputs.
- Integrate previous Allworth plugin modules behind adapter.
- Preserve deterministic mock data for local tool and UI testing.

Deliverables:

- Connector interfaces.
- Plugin adapter tests.
- Source/provenance metadata.
- Tool catalog sourced from real modules.

## Phase 4: Advisor Briefs

Goals:

- Convert insights into advisor-ready briefs.
- Generate meeting prep.
- Draft client messages.
- Support advisor approval workflow.

Deliverables:

- Advisor brief endpoint.
- Brief cards in mobile app.
- Draft message flow.
- CRM/task integration design.

## Phase 5: Client Intelligence Memory

Goals:

- Persist governed client facts.
- Build episode ingestion.
- Extract fact atoms.
- Generate client/advisor/compliance views.

Deliverables:

- Episode store schema.
- Fact store schema.
- Provenance UI.
- Deletion and supersession workflow.
- Outcome learning loop.

## Phase 6: Production Readiness

Goals:

- Authentication and authorization.
- Production telemetry.
- Compliance controls.
- Deployment pipeline.
- Security review.

Deliverables:

- Auth integration.
- Environment management.
- Audit logging.
- Monitoring dashboards.
- Release checklist.

## Backlog

- Goal creation.
- Account aggregation.
- Tax lot viewer.
- Concentration analysis tool.
- Scenario comparison.
- Retirement spending sensitivity.
- Advisor calendar integration.
- Client transparency view for learned facts.
- "Why do you think that?" source explorer.
- Conversation export.
