# Allworth AI Client Platform — Demo Build Handoff

**Deadline: June 22, 2026 (hard). Today: June 9.**
**Purpose:** Executive demo to secure full funding for an AI-native client engagement platform. This is a DEMO, not production. Every build decision should optimize for the demo script below, demo reliability, and speed of iteration — not scalability, auth, or production hardening.

---

## 1. Context (read this first)

Allworth Financial is a national RIA (wealth management firm). Clients talk to their advisor ~twice a year and live with financial ambiguity in between — many are already pasting their finances into ChatGPT, where the conversation dead-ends because it has no connection to their real accounts, plan, or advisor.

This app is the answer: a client-facing platform where the client sees their **entire** financial picture (Allworth accounts + connected outside/"held-away" accounts), receives proactive nudges tied to their financial plan, and can ask anything — with answers grounded in their actual data, always ending in a path back to their human advisor (never standalone advice).

**The business case being demoed:** when advisors can see held-away assets, they consolidate them. The app is a held-away capture engine and an organic growth engine, not a robo-advisor.

**Two executive asks baked into this build:**
1. "Bring the tools inside the app" → the AI chat is grounded in portfolio, plan, tax, and spending data via backend tool calls.
2. "Recursive self-improvement / learning about clients and advisors" → implemented as a **client intelligence layer**: a persistent memory/profile store that accumulates structured facts from every interaction and is loaded into all future context. In the UI and demo narration this is called the "client intelligence layer." Do NOT attempt actual self-modifying or self-training systems.

---

## 2. Hard constraints

- **SYNTHETIC DATA ONLY.** No real client, advisor, or firm data anywhere in this codebase, ever. All personas, accounts, balances, and transactions are fabricated (spec in §6). This is a compliance requirement, not a preference.
- **Compliance posture:** the AI never gives directive financial advice. Every analytical answer and every nudge ends with a variant of "here's what to discuss with [advisor name]" and a one-tap "Message/Schedule with advisor" CTA. No "you should buy/sell X." Frame outputs as observations, trade-off analysis, and questions to bring to the advisor. Include a persistent footer disclaimer: "Educational information, not investment advice. Allworth Financial demo — synthetic data."
- **Demo reliability beats realism.** Seeded data, deterministic where possible. No live bank aggregation (no Plaid/Yodlee) — outside accounts are pre-seeded and labeled "Connected." If an LLM call can fail mid-demo, add a cached/fallback response path.
- Runs locally on a MacBook: backend via single `./run.sh`, app via Xcode (iPhone 15/16 Pro simulator, or physical device on the same network). No cloud infra beyond the Anthropic API. Required screens — Client: Home dashboard, Nudge detail sheet, Chat, Profile ("What I've learned" panel). Advisor: Book list, Client detail (Maya). Plus the hidden demo control sheet and the Beat-6 vision screen.

---

## 3. The demo script = acceptance criteria

The app is done when this 5-beat script runs flawlessly. Build backwards from it.

**Beat 1 — The full picture.** Log in as client persona Maya Tran (no real auth; persona picker is fine). Dashboard shows net worth across Allworth-managed accounts AND connected outside accounts (held-away 401k at Fidelity, Robinhood brokerage, Chase checking/savings, mortgage). Clean net worth number up top, accounts grouped Allworth vs. Outside, 12-month net worth sparkline, spending-vs-plan widget.

**Beat 2 — The nudge.** A notification badge is waiting: *"Your spending the last 3 months is running ~18% above your plan's assumption. Want to look at what that means for your plan with Dana?"* Tapping it opens a detail view: spending trend chart vs. plan line, plain-English explanation of why it matters (sequence-of-returns / drawdown sensitivity), and two CTAs: "Explore in chat" and "Message Dana."

**Beat 3 — The grounded question.** In chat, the presenter asks: *"I want to put $200K into the SpaceX IPO. I have about 6 days to decide. What would that do to my taxes and my income plan?"* The AI calls backend tools (portfolio positions, tax lots, plan/income data, spending data), and returns a structured answer: where the $200K could come from, estimated capital-gains impact of each funding option, effect on her income-from-portfolio plan, concentration risk note — ending with "questions to bring to Dana" + schedule CTA. This is the wow moment; the response should visibly show which data sources were consulted (e.g., chips: "Portfolio · Tax lots · Financial plan · Spending").

**Beat 4 — The memory.** Presenter switches to a "Wednesday" session (a session/date toggle is fine). The app proactively opens with: *"Last time you were weighing $200K into the SpaceX IPO with a decision deadline around June 15. A few things since then: [seeded change]. Want to pick that back up, or send your scenario to Dana?"* It remembered without being asked. Show the intelligence layer working: a small "What I've learned" panel in settings listing accumulated profile facts with timestamps.

**Beat 5 — The advisor view.** Switch to advisor persona Dana Whitfield. Her dashboard shows: book overview, and on Maya's card — **held-away assets detected: $611K** with breakdown, the nudge that fired and the conversation it generated, the IPO question summary, and a suggested talking-points brief auto-generated from the intelligence layer. Narration line this enables: "advisors who can see outside money consolidate it — this is the consolidation engine."

**Beat 6 — The vision screen (static).** The demo closes on a single designed screen showing what the funded platform becomes — the three learning loops and the nightly job. Spec in §9.5. This beat is the bridge to the funding ask.

---

## 4. Architecture

Keep it simple and mono-repo. The client app is **native SwiftUI (iOS 17+)** — it demos from an iPhone (or simulator mirrored to the projector), which lands far better than a browser mockup. The backend runs locally on the same MacBook.

```
/app
  /AllworthCompanion   SwiftUI iOS app (Xcode project) — client AND advisor views,
                       switched via hidden demo persona picker
  /backend             Node + Express (or FastAPI if Python preferred)
    /tools             Tool implementations the LLM can call
    /data              Seed JSON (personas, accounts, transactions, plan, tax lots)
    /memory            Profile store (SQLite or JSON file per persona)
  run.sh               One-command backend startup
```

The app talks to `http://localhost:3000` (simulator) / the Mac's LAN IP (physical device — add NSAppTransportSecurity local-networking exception for the demo). The Anthropic API key lives ONLY in the backend; the app never calls Anthropic directly.

**AI layer:** Anthropic Messages API with tool use. Backend exposes one `/api/chat` endpoint; the backend (not the browser) holds the API key and orchestrates the tool-call loop. Tools to implement (all read from seed data):

- `get_accounts(client_id)` — all accounts, balances, Allworth vs. outside
- `get_portfolio(client_id)` — positions, allocation, cost basis / tax lots
- `get_financial_plan(client_id)` — goals, income plan, spending assumption, risk target
- `get_spending(client_id, months)` — monthly spending vs. plan assumption
- `get_client_profile(client_id)` — the memory/intelligence layer (see §5)
- `update_client_profile(client_id, facts[])` — write new learned facts
- `simulate_tax_impact(client_id, sale_amount, source)` — rough cap-gains estimate from seeded tax lots (simple math is fine; label as estimate)
- `get_advisor_brief(advisor_id, client_id)` — assembles the advisor view payload

**System prompt for the in-app AI (write it into the backend):** persona = "Allworth Companion"; grounded answers only from tool results; observations and trade-offs, never directives; always close with advisor handoff; concise, warm, plain-English; cite which tools/data informed the answer.

**Nudge engine:** rule-based, runs on seed data at load (e.g., `spending_3mo_avg > plan_assumption * 1.15` → spending nudge; `single_position_weight > 0.20` → concentration nudge). 2–3 rules total. No ML needed.

**Memory / intelligence layer (the "recursive self-improvement" ask):** after each chat turn, a second lightweight LLM call extracts structured facts (`{fact, category, source_quote, timestamp}` — categories: goals, concerns, liquidity_events, preferences, outside_assets_mentioned). Append to the profile store; dedupe by similarity. Profile is injected into every chat system prompt and powers the Beat-4 proactive open and the Beat-5 advisor brief. This is the entire "learning" implementation — keep it this simple.

---

## 5. UI Design Rules — SwiftUI (MANDATORY, applies to every screen)

**The brief in one line:** Allworth's brand wearing Robinhood's confidence and OpenAI's calm. A trusted fiduciary that feels like the best consumer software the exec audience uses — not "enterprise fintech."

### 5.1 Brand & color tokens

Define every color once in `Theme.swift` (a `Color` extension); never use ad-hoc colors in views.

| Token | Role | Value |
|---|---|---|
| `allworthNavy` | Primary brand: headers, key icons, primary buttons | Pull EXACT hex from official Allworth logo/site assets (allworthfinancial.com) — placeholder `#0F2A4A`, VERIFY before day 3 |
| `allworthAccent` | Single accent: CTAs, active states, the advisor-handoff button | Pull exact secondary brand hex from the same assets — VERIFY |
| `surfacePrimary` | App background | `#FAFAF8` (warm off-white — OpenAI calm, not stark white) |
| `surfaceCard` | Cards/sheets | `#FFFFFF` |
| `inkPrimary` / `inkSecondary` / `inkTertiary` | Text hierarchy | `#0B1220` / 60% / 38% opacity of it |
| `gainGreen` / `lossRed` | Semantic ONLY — money movement, deltas | `#00C805`-family green, restrained red. Never decorative. |
| `hairline` | Dividers | 8% ink |

Rules: **one accent color, used sparingly** — if a screen has more than two accent-colored elements, remove some. Navy is identity; accent is action; green/red are information. Nothing else carries color. Light mode only for the demo (don't burn time on dark mode). Allworth logo appears exactly once in the client app (login/persona screen) and once in the advisor view header — brand confidence, not brand wallpaper.

### 5.2 Typography & numbers (the Robinhood feel lives here)

- System font only: SF Pro. Numbers use `.rounded` design — `Font.system(size:weight:design:.rounded)`.
- The hero number rule: every primary screen leads with ONE big number (net worth, spending vs. plan, held-away total). ~44–56pt, `.semibold`, `.rounded`, with its delta underneath in `gainGreen`/`lossRed` at ~15pt. Everything else on screen is visually subordinate to it.
- Use `.monospacedDigit()` on any number that updates, and `.contentTransition(.numericText())` for value changes.
- Text scale (only these): hero 48 / title 28 `.semibold` / body 17 / secondary 15 / caption 13. Support Dynamic Type defaults; don't fight it.
- No ALL-CAPS labels except 11pt tertiary section headers with +0.6 tracking, used rarely.

### 5.3 Layout & surfaces

- 4pt spacing grid; default content padding 20pt; generous whitespace is the design — when in doubt, add space, not decoration.
- Prefer **flat lists with hairline dividers** (Robinhood) over card-grids. Cards only for: nudges, the advisor CTA, and chat input. Card style: `surfaceCard`, 16pt corner radius (`.continuous`), shadow `black.opacity(0.05), radius 12, y 4` — one shadow style app-wide.
- Charts: Swift Charts. **No gridlines, no axis labels by default, no legends.** A line chart is a single 2pt line with a soft gradient fill fading to clear; min/max or selected-point values appear on scrub (`chartOverlay` + drag gesture, with haptic ticks). Allocation donut: thin ring, navy/accent/neutrals only.
- Navigation: bottom `TabView` for client (Home, Chat, Profile — three tabs max), `NavigationStack` pushes, `.sheet` with detents for nudge detail. Advisor view: simple sidebar-free list → client detail push.
- Iconography: SF Symbols only, `.regular` weight, monochrome (`inkSecondary` default; navy when active). No third-party icon packs, no illustrations, no emoji in UI chrome.

### 5.4 Chat (the OpenAI feel lives here)

- Chat surface is calm and document-like: assistant messages are **plain text on the background — no bubble**, 17pt, relaxed line spacing (`.lineSpacing(5)`), max readable width. User messages: right-aligned in a quiet `inkPrimary.opacity(0.05)` rounded rectangle.
- Streaming text renders progressively (SSE or chunked endpoint → append to `@State` string). Cursor: subtle pulsing block during stream.
- **Tool chips:** while the backend runs tools, show small pills above the incoming message — SF Symbol + label ("Reading your portfolio…", "Checking tax lots…", "Reviewing your plan…") appearing sequentially with a gentle fade/slide. When the answer lands, chips collapse into a single tappable "Sources: Portfolio · Tax lots · Plan · Spending" row. This visible orchestration is a core demo moment — make it beautiful.
- Every analytical answer ends with the advisor handoff block: a distinct card — Dana's avatar, "Bring this to Dana," buttons `Message` / `Schedule` in `allworthAccent`. This is the most important recurring component in the app; design it once, perfectly, reuse everywhere (nudges use the same block).
- The persistent compliance footer (§2) lives as an 11pt `inkTertiary` line above the input field.

### 5.5 Motion & feel

- One animation personality app-wide: `.spring(response: 0.35, dampingFraction: 0.8)`. No linear/ease-in-out mixing.
- Haptics via `.sensoryFeedback`: `.impact(.light)` on chart scrub ticks and tab changes; `.success` when a nudge is sent to the advisor. Nothing else.
- Numbers animate on appear (count-up on the hero number, once, fast). Nudge badge uses a single subtle pulse on first appearance — never looping animation anywhere.
- Skeleton shimmer for loading states; never a bare spinner on a primary screen.

### 5.6 Do / Don't

**Do:** ruthless subtraction — every screen should look almost empty until you notice everything you need is there; one hero number per screen; one accent; one shadow; one spring.
**Don't:** gradients on text or buttons, borders around cards, more than 3 font sizes per screen, colored section backgrounds, stock-photo or illustration filler, badges/pills in more than one style, any UI element that exists to "fill space."

### 5.7 Structure for Claude Code

- `Theme.swift` (colors, type scale, spacing, radius, shadow, spring constant) — views consume tokens only.
- Component library first, screens second: `HeroNumberView`, `AccountRow`, `SparklineChart`, `NudgeCard`, `AdvisorHandoffCard`, `ToolChipRow`, `ChatMessageView`, `LearnedFactRow`. Build these in a `#Preview`-driven gallery screen, then assemble Beats from them.
- MVVM-lite: one `@Observable` view model per screen, an `APIClient` actor for the backend, `Codable` models mirroring the backend JSON. No third-party dependencies — SwiftUI + Swift Charts + Foundation only.
- Demo control bar (persona switch, Monday/Wednesday session toggle, reset) = a triple-tap gesture on the logo opens a hidden sheet. Invisible during the demo, instant when needed.

---

## 6. Synthetic personas & seed data

**Client: Maya Tran**, 58, Plano TX. Recently semi-retired consultant; lives partly off portfolio income. Advisor: Dana Whitfield.

- Allworth-managed: Trust brokerage $1.42M (60/40, includes appreciated AAPL position ~12% weight, mixed tax lots), Rollover IRA $880K, Roth IRA $145K.
- Outside (connected): Fidelity 401k from old employer $385K, Robinhood taxable $96K (concentrated tech, low basis), Chase checking $28K, Chase savings $102K, mortgage −$310K. **Held-away total ≈ $611K.**
- Plan: $14K/mo spending assumption; actual last 3 months ≈ $16.5K/mo (triggers the nudge). Income plan: $9K/mo from portfolio. Goals: lake house in 4 years ($350K), grandkids' 529s.
- Seeded liquidity event: interested in SpaceX IPO, ~$200K, decision by June 15. Pre-seed one prior chat session (the "Monday" session) containing the Beat-3 exchange so Beat 4 works even if Beat 3 is skipped; live Beat 3 should append to the same memory.
- Tax lots: enough granularity that `simulate_tax_impact` produces different estimates for "sell AAPL lot A" vs "use savings" vs "sell Robinhood positions" — that contrast is the substance of the Beat-3 answer.

**Advisor: Dana Whitfield** — book of 5 synthetic households (Maya + 4 lightweight ones with names/balances only).

Generate 12 months of plausible transactions/balances so charts look real (no flat lines, no obviously generated patterns).

---

## 7. Build order (13 days)

1. **Days 1–2:** Repo scaffold, seed data complete, backend tools returning correct JSON, basic chat loop with tool use working end-to-end in plain UI.
2. **Days 3–5:** Client dashboard + nudge engine + nudge detail view, real visual design pass.
3. **Days 6–7:** Chat UX (streaming, tool chips, advisor CTAs), Beat-3 answer quality tuning — iterate on the system prompt until the IPO answer is consistently excellent.
4. **Days 8–9:** Memory layer + Beat-4 proactive session + "What I've learned" panel.
5. **Days 10–11:** Advisor view + auto-generated brief. Demo control bar + reset.
6. **Days 12–13:** Polish, rehearse full script ≥5 times, add fallback cached responses for Beats 3–4, fix everything that wobbles. Freeze.

If behind schedule, cut in this order: extra nudge rules → advisor brief auto-generation (can be semi-canned) → chart variety. Never cut: Beat 3 quality, Beat 4 memory, the visual polish of the client dashboard.

## 8. Explicitly out of scope

Real authentication, real account aggregation (Plaid etc.), real client data, push notifications, trading/execution of any kind, production security hardening, multi-tenant anything, app-store packaging, actual self-modifying AI. If a feature isn't in the 5-beat script (or the static Beat-6 vision screen in §9.5), it doesn't exist.

---

## 9. v2: Full Learning Architecture (the funded version)

This section is NOT built for June 22 — except §9.5, a single static screen that closes the demo. It exists so (a) the demo ends by showing what the blank check buys, and (b) v1 code is structured so nothing has to be thrown away to get here. Where a §9 concept has a v1 counterpart, build the v1 version as a thin slice of this design.

### 9.1 What "self-improving" means here

The foundation model is never retrained on client data. The **system** improves through three feedback loops layered on top of it:

**Loop 1 — Per-client learning (memory).** Every interaction, transaction, meeting, and life event updates that client's profile. The agent knows the client better in month six than in week one; nudges and answers get more personal and more accurate per client over time. *v1 demo ships a thin slice of this loop (§4 memory layer).*

**Loop 2 — Cross-client learning (patterns).** Anonymized signals across the entire book become better rules and briefs: e.g., "semi-retired clients running 15%+ over plan-assumed spending tend to need a risk conversation within two quarters." Outputs of this loop are improved nudge rules, segment models, and advisor playbooks — never another client's facts. **Hard isolation rule: no client's data ever appears in another client's context; Loop 2 consumes only aggregated/anonymized features.**

**Loop 3 — System learning (outcomes).** Every nudge and answer gets an outcome label: opened, dismissed, acted on, escalated to advisor; advisor thumbs-up/down on briefs; client follow-through. Outcomes feed an offline evaluation harness that tunes nudge thresholds, wording variants, and agent prompts. This loop is what makes the system measurably better every week it runs, not merely better informed.

### 9.2 Memory: three layers

**Episodic memory (append-only record).** Every conversation turn, nudge fired, data event (deposit, withdrawal, meeting transcript, CRM note), and system action — timestamped, immutable, stored in Postgres with a vector index over content for semantic search ("what did Maya say about the lake house?"). This layer doubles as the compliance audit trail / books-and-records store.

**Semantic memory (the distilled profile).** Structured facts extracted from episodes:

```json
{
  "fact": "Considering $200K allocation to SpaceX IPO",
  "category": "liquidity_event",        // goals | concerns | liquidity_events | preferences | outside_assets | family | risk_attitude
  "source_episode_id": "ep_8841",
  "source_quote": "I want to put $200K into the SpaceX IPO",
  "learned_at": "2026-06-09T19:14:00Z",
  "confidence": 0.92,
  "status": "active"                    // active | superseded | decayed | deleted
}
```

A consolidation job dedupes near-identical facts, resolves conflicts (newer + higher confidence supersedes older), and decays stale facts by category-specific half-lives. Only this small, high-signal distillation is injected into live context — the agent never rereads a year of transcripts.

**Procedural memory (how to work with this person).** Learned interaction preferences for both clients and advisors: response length, jargon tolerance, nudge frequency and channel, brief format. Stored as key-value preferences with the same provenance fields; applied to every output.

**Provenance is non-negotiable.** Every semantic and procedural fact carries source, timestamp, and confidence. This is what makes the system auditable ("why did it say this?"), supports clean deletion requests (delete cascades from fact → flag source episodes), enforces Loop-2 isolation, and satisfies books-and-records expectations. Build provenance into the v1 schema now — it is nearly impossible to retrofit.

### 9.3 The nightly learning job

A scheduled pipeline that runs for every client, every night:

1. **Ingest** the day's new episodes: transactions and balance changes (custodian + aggregation feeds), app conversations, advisor meeting transcripts/notes, CRM activity, relevant market events.
2. **Extract** new candidate facts via LLM extraction pass → write to semantic memory with provenance.
3. **Consolidate** — dedupe, supersede, decay.
4. **Re-evaluate** nudge rules against the updated profile and fresh data → queue tomorrow's nudges.
5. **Refresh** advisor briefs for any client whose profile materially changed; flag high-signal changes (new held-away account detected, large withdrawal, life-event language) for advisor attention.
6. **Log** a per-client learning digest: "what the system learned about this client today and from where."

Net effect, stated plainly for the demo: *the platform knows more about every client each morning than it did the day before — and there's a line-item log proving exactly what it learned and from what source.*

### 9.4 Evaluation & improvement harness (Loop 3 mechanics)

- Outcome events table: every nudge/answer/brief gets `{delivered, opened, dismissed, acted_on, advisor_rating, led_to_meeting, led_to_consolidation}`.
- Weekly offline eval: nudge precision (acted-on rate), answer quality vs. a golden-question set (the IPO question and peers), brief usefulness (advisor ratings).
- Tuning targets, in order of safety: nudge thresholds → wording variants (A/B) → prompt revisions → rule proposals from Loop-2 patterns (human-approved before activation).
- Everything tuned is versioned; every client-visible output records which prompt/rule version produced it (provenance again).

### 9.5 BUILD FOR DEMO — Beat 6: the vision screen

Add one final static screen to the demo app (reachable from the demo control bar): **"What the funded platform becomes."** A single, beautifully designed diagram view — no live functionality — showing:

- The three loops as a labeled cycle around a central "Client Intelligence Layer" (memory store), with the nightly job as the clock that drives it.
- Callouts: "Knows every client better every day" (Loop 1), "Every client benefits from patterns across the book — fully anonymized" (Loop 2), "Measurably better every week it runs" (Loop 3), "Every fact has a source, a timestamp, and an audit trail" (provenance).
- A closing line at the bottom: **"Models are rented. This memory is owned — and it compounds."**

This screen is the last beat of the demo script and the bridge to the funding ask. Keep it static, fast, and gorgeous; it should take less than half a day. Slot it into Days 10–11 of the build order; in the cut-order it ranks above chart variety but below Beat 3/Beat 4 quality.

### 9.6 v2 governance requirements (for the roadmap slide, not the build)

Client consent flows for memory and data connection; encryption at rest/in transit; role-based access (advisor sees their book only); right-to-deletion pipeline; supervision/review queue for AI-generated client communications; retention policies aligned to books-and-records rules; Loop-2 anonymization review. These are funded-version workstreams — listed here so the ask includes them and nobody can say the plan ignored compliance.
