# Allworth Companion — AI Demo

Demo app for the Allworth Financial executive pitch (June 22, 2026): an AI-native client engagement platform. React Native (Expo) iOS app backed by a Node/Express server with an Anthropic tool-use loop. (The original SwiftUI implementation lives in `app/AllworthCompanion` as reference.)

> **Synthetic data only.** No real client information anywhere in this repo. The assistant never gives directive advice — every answer hands off to the advisor.

## Quick start

```bash
./run.sh                # installs deps if needed, starts backend on :3000
cd app/AllworthCompanionRN
npm install
npx expo run:ios        # native build + launch on the iOS simulator
```

The app talks to `http://localhost:3000`.

**Live chat (optional):** put an Anthropic key in `app/backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Without a key, chat streams cached fallback responses — the demo works fully offline by design and never dies on stage.

## Layout

```
app/AllworthCompanionRN/ React Native app (Expo SDK 56 + TypeScript)
  src/api.ts             REST + SSE chat (expo/fetch streaming)
  src/state.tsx          app context + deep-link demo overrides
  src/components/        hero number, sparkline, nudge/handoff cards, chat
  src/screens/           dashboard, chat, profile, advisor, vision, controls
app/AllworthCompanion/   original SwiftUI implementation (reference)
app/backend/             Node + Express, Anthropic SDK
  lib/tools.js           8 financial tools (accounts, portfolio, tax sim, brief…)
  lib/chat.js            streaming tool-use loop + fallback selection
  lib/memory.js          provenance memory (fact, source quote, timestamp)
  fallbacks/             cached responses for the scripted demo beats
  data/seed.json         deterministic synthetic data
run.sh                   one-command backend startup
allworth-ai-demo-handoff.md   full spec — all decisions trace to it
docs/                    vision + production roadmap (design docs)
```

## Vision & roadmap

The `docs/` directory holds the platform design docs — product brief, [Client Intelligence Layer](docs/CLIENT_INTELLIGENCE_LAYER.md) (governed memory, fact atoms, learning loops), safety/compliance boundaries, and the [phased roadmap](docs/ROADMAP.md) from this demo to production (LLM chat → MCP/real data → advisor briefs → governed memory → production readiness). The demo's vision screen (Beat 6) presents this path.

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
xcrun simctl openurl booted "allworthdemo://demo/{chat|profile|advisor|advisor_detail|vision|nudge|controls}"
```

(The SwiftUI app uses `SIMCTL_CHILD_DEMO_SCREEN=<screen>` at launch instead.)

---

*Educational information, not investment advice. Allworth Financial demo — synthetic data.*
