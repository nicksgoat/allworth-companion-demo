# Allworth Companion — AI Demo

Demo app for the Allworth Financial executive pitch (June 22, 2026): an AI-native client engagement platform. React Native (Expo) iOS app backed by a Python/FastAPI server with an Anthropic tool-use loop.

> **Synthetic data only.** No real client information anywhere in this repo. The assistant never gives directive advice — every answer hands off to the advisor.

## Quick start

One command runs everything — backend and iOS app:

```bash
./demo.sh               # FastAPI backend on :3000 + app on the iOS simulator
./demo.sh --release     # demo-day mode: Release build, no Metro needed
```

Prereqs: [uv](https://docs.astral.sh/uv/), Node, and Xcode. Ctrl-C stops everything the script started.

To run the pieces separately:

```bash
./run.sh                # backend only (FastAPI on :3000; deps sync automatically)
cd frontend
npm install
npx expo run:ios        # native build + launch on the iOS simulator
```

The app talks to `http://localhost:3000`.

### Agent startup (cross-platform)

Use this section when an agent needs to start the app reliably from a cold workspace.

On macOS with Xcode, use the one-command iOS flow:

```bash
./demo.sh
```

On Windows/Linux (or when iOS simulator is unavailable), run backend + web in two terminals:

For Windows, there is now a one-command startup that installs everything and launches both backend and web:

```powershell
npm run start:all:win
```

What it does:
- Runs `uv sync` for `backend`
- Runs `npm install` for `frontend`
- Starts backend in a new PowerShell window on `:3000`
- Starts Expo web in the current terminal on `:8081`

If you prefer manual startup, use the two-terminal commands below.

```bash
# Terminal 1: backend
uv --project backend run --directory backend python -m uvicorn main:app --host 0.0.0.0 --port 3000
```

```bash
# Terminal 2: frontend web
cd frontend
npm install
npm install react-dom@19.2.3 react-native-web @expo/metro-runtime
npm run web
```

Open `http://localhost:8081` in a browser.

Health check:

```bash
curl http://localhost:3000/api/health
```

Expected response includes `{"ok": true, ...}`.

**Live chat (optional):** configure the selected LLM provider in `backend/.env`.
For Azure OpenAI GPT-4o:

```
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
LLM_CHAT_MODEL=gpt-4o
LLM_EXTRACT_MODEL=gpt-4o
```

For deployment, set those values as backend runtime environment variables or secrets.
Do not put the GPT-4o key in Expo/frontend config. The frontend only needs:

```
EXPO_PUBLIC_API_URL=https://YOUR-BACKEND-HOST
```

Chat requires a configured LLM provider. Local development can still use the deterministic seed dataset for household data.

## Production readiness

The backend is designed to run stateless across multiple Fly.io or Azure instances:

- Auth tokens are signed bearer tokens, not process-local sessions.
- Chat requests do not rely on server-local conversation state.
- Production audit logs default to stdout.
- Learned profile memory is disabled by default in production unless you wire it to durable storage.

Required production settings:

```
APP_ENV=production
SESSION_SECRET=<strong random secret shared by all backend instances>
CORS_ORIGINS=https://YOUR-FRONTEND-HOST
LLM_PROVIDER=azure_openai
AZURE_OPENAI_API_KEY=<secret>
AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
AZURE_OPENAI_API_VERSION=2024-12-01-preview
LLM_CHAT_MODEL=gpt-4o
LLM_EXTRACT_MODEL=gpt-4o
EXPO_PUBLIC_API_URL=https://YOUR-BACKEND-HOST
```

For real client traffic, also replace demo email auth with Entra/SSO, keep `ALLOW_SEED_AUTH=false`, keep `ALLOW_DEMO_AUTH_FALLBACK=false`, and move any durable client memory to a managed store such as Postgres, Cosmos DB, or Redis.

## Layout

```
frontend/                React Native app (Expo SDK 56 + TypeScript)
  src/api.ts             REST + SSE chat (expo/fetch streaming)
  src/state.tsx          app context + deep-link demo overrides
  src/components/        hero number, sparkline, nudge/handoff cards, chat
  src/screens/           dashboard, chat, profile, advisor, vision, controls
backend/                 Python + FastAPI backend (uv-managed)
  allworth_api/          layered package (presentation, application, domain, infrastructure)
  mcp_server.py          MCP server (stdio, read-only, household-scoped)
  data/seed.json         deterministic synthetic data
run.sh                   one-command backend startup
allworth-ai-demo-handoff.md   full spec — all decisions trace to it
docs/                    vision + production roadmap (design docs)
```

## Vision & roadmap

The `docs/` directory holds the platform design docs — product brief, [Client Intelligence Layer](docs/CLIENT_INTELLIGENCE_LAYER.md) (governed memory, fact atoms, learning loops), safety/compliance boundaries, and the [phased roadmap](docs/ROADMAP.md) from this demo to production (LLM chat → MCP/real data → advisor briefs → governed memory → production readiness). The demo's vision screen (Beat 6) presents this path.

## MCP server (Phase 3 preview)

`backend/mcp_server.py` exposes the backend's tool layer over the Model Context Protocol (stdio), implementing the connector rules in [docs/MCP_INTEGRATION.md](docs/MCP_INTEGRATION.md): backend-only, **read-only** (writes like `update_client_profile` are excluded pending approval/audit design), entitlement-scoped to one household (`ALLWORTH_CLIENT_ID`, never a tool parameter), and every result wrapped in a provenance envelope (`source`, `tool`, `clientId`, `retrieved_at`, `read_only`). The repo's `.mcp.json` registers it, so Claude Code/Desktop pointed at this repo can query the same governed data the app uses:

```sh
# read-only tools include the composable financial tool suite from docs/FINANCIAL_TOOLS.md
claude mcp list   # → allworth-client-intelligence
```

## Demo script

Six beats, all driven from the app:

1. **Dashboard** — Maya's net worth across Allworth and held-away accounts
2. **Nudge** — spending running 18% over plan, with monthly breakdown
3. **Grounded chat** — "$200K SpaceX IPO" question answered via live tool calls (visible tool chips → sources)
4. **Memory** — return Wednesday, the assistant picks up the IPO thread unprompted, with provenance
5. **Advisor view** — Dana's book, $611K held-away detected, auto-prepared meeting brief
6. **Vision** — the Client Intelligence Layer platform story

Demo controls: triple-tap the Allworth wordmark (switch client/advisor/vision, Monday/Wednesday session, backend host, reset).

For automated verification, deep-link to a screen:

```bash
xcrun simctl openurl booted "allworthdemo://demo/{chat|profile|fact|advisor|advisor_detail|vision|nudge|controls}"
```

(The SwiftUI app uses `SIMCTL_CHILD_DEMO_SCREEN=<screen>` at launch instead.)

---

*Educational information, not investment advice. Allworth Financial demo — synthetic data.*
