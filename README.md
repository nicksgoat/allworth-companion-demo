# Allworth Companion — AI Demo

Demo app for the Allworth Financial executive pitch (June 22, 2026): an AI-native client engagement platform. Native SwiftUI iOS app backed by a Node/Express server with an Anthropic tool-use loop.

> **Synthetic data only.** No real client information anywhere in this repo. The assistant never gives directive advice — every answer hands off to the advisor.

## Quick start

```bash
./run.sh                # installs deps if needed, starts backend on :3000
```

Then open `app/AllworthCompanion/AllworthCompanion.xcodeproj` in Xcode and run on an iOS 17+ simulator. The app talks to `http://localhost:3000`.

**Live chat (optional):** put an Anthropic key in `app/backend/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Without a key, chat streams cached fallback responses — the demo works fully offline by design and never dies on stage.

## Layout

```
app/AllworthCompanion/   SwiftUI iOS app (no third-party dependencies)
app/backend/             Node + Express, Anthropic SDK
  lib/tools.js           8 financial tools (accounts, portfolio, tax sim, brief…)
  lib/chat.js            streaming tool-use loop + fallback selection
  lib/memory.js          provenance memory (fact, source quote, timestamp)
  fallbacks/             cached responses for the scripted demo beats
  data/seed.json         deterministic synthetic data
run.sh                   one-command backend startup
allworth-ai-demo-handoff.md   full spec — all decisions trace to it
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

For automated verification, launch with `SIMCTL_CHILD_DEMO_SCREEN={chat|profile|advisor|advisor_detail|vision|nudge|controls}` to boot directly into a screen.

---

*Educational information, not investment advice. Allworth Financial demo — synthetic data.*
