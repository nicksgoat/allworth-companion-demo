# Allworth Companion — Design Rules

The enforceable system behind every screen. Tokens live in `src/theme.ts`; brand
values come from `ALW001_01_Brand_Dashboard_DEC2024.pdf` (via the
`allworth-brand` skill) and always win over guesses. If a value isn't a token,
it's a bug or it becomes a token.

## Voice of the UI

Sophisticated, calm, upmarket — a fiduciary, not a fintech toy. Nothing bounces,
nothing shouts, nothing is clever at the reader's expense. When in doubt, remove.

## Color

- **Primaries**: `colors.allworthNavy` (#173D67, wordmark, filled actions),
  `colors.allworthAccent` (#3E71B7, Iris — links, active accents, the advisor
  presence color). White does the rest of the work.
- **Surfaces**: `surfacePrimary` (Feather Gray) for screens, `surfaceCard`
  (white) for cards, `surfaceHero` (Night Blue) for the one premium dark hero
  per screen at most. Beige/Linen/Ice are available neutrals — use sparingly.
- **Ink**: `inkPrimary` → `inkSecondary` → `inkTertiary` is the only text
  hierarchy. Never place secondary-palette colors on body text.
- **Secondary palette (`chart*`) is for charts and infographics only** — never
  buttons, never backgrounds, never text. `gain`/`loss`/`attention` map money
  semantics onto Evergreen/Pumpkin; on dark heroes use `gainOnDark`/`lossOnDark`.
- Navy is the app's header identity — see **Navy header system** below. Within a
  screen's *body*, still at most one dark hero (the top one); everything below it
  stays light so content reads.

## Navy header system

Every header in the app is navy (Night Blue `chartNightBlue` → Indigo
`allworthNavy` gradient for heroes; solid `chartNightBlue` for bars). Pick the
tier by surface type — don't invent a fourth. Shared implementations live in
`components/GreetingHero.tsx` (`NavyGradient`, `NavyHeroBand`), `components/
Glass.tsx` (`AppHeader`), and `components/Rows.tsx` (`SheetHeader`).

- **Tier 1 — Navy hero** (full-bleed gradient band + adaptive header). For
  screens that lead with identity/summary content: Home, Wealth, Profile,
  advisor Book. Wrap the top module in `NavyHeroBand` (bleeds to the top + side
  edges, rounded bottom lip, header-safe top padding) and render `<AppHeader …
  onHero />` (floats transparent + white over the navy, cross-fades to light
  glass as the hero scrolls past). Pass the screen's `scrollY`.
- **Tier 2 — Solid navy bar** (`<AppHeader … solid />`). For surfaces with no
  room for a hero: Chat (the conversation needs its height). White title + white
  mark/action on solid navy; same collapse-on-scroll as the glass header. The
  advisor native stack headers use the same navy via the navigator
  `screenOptions` (navy `headerStyle`, white tint).
- **Tier 3 — Navy sheet header** (`Rows.SheetHeader`). For every detail
  sheet/modal: a full-bleed solid-navy bar (white title + optional subtitle + a
  white close chip, or a custom `right` slot) sitting flush at the sheet top.
  The sheet's scroll content keeps a 20px gutter and `paddingTop: 0` so the bar
  bleeds to the edges; **content below the bar stays light** for readability.
  Full-screen chart modals (NetWorthDetail, chat tool detail) are entirely navy
  — that's the north-star surface Tier 3 echoes.

Rules of thumb: heroes get the gradient + cerulean glow (`NavyGradient`); bars
are solid navy. White (`#FFFFFF`) title/mark; `rgba(255,255,255,0.7)` for
secondary text and `rgba(255,255,255,0.16)` for chip fills on navy. Money/severity
accents on navy use the `*OnDark` variants or the saturated secondary colors.

## Typography

- **Playfair Display** (`fonts.display*`): headlines, hero numerals, large
  stats. Big numbers always use `text.display` (tabular figures — brand rule).
- **Lato** (`fonts.sans*`): everything interactive and everything body-sized.
- Use the `text.*` ladder — `display 48 / title 28 / heading 20 / body 15 /
  bodySm 13 / caption 12` plus `sectionLabel` (11 uppercase, +0.6 tracking).
  Do not invent sizes between rungs; if a design needs one, add it to the
  ladder deliberately.
- Chat is the one surface with its own body size (17pt) — conversation reads
  bigger than UI. Keep that exception contained to chat bubbles/composer.

## Spacing & shape

- **4px scale only**: `space[1..12]` (4→48). Screen gutters are `space[5]`
  (20). Card padding is `space[4]` (16). Never a bare magic number.
- **Radii**: `radius.card` 16 for cards/sheets, `radius.chip` 10 for chips and
  small inputs, `radius.pill` 999 for fully-round (pills, orbs, avatars).
  Circular elements use a radius of exactly half their height (34px orb → 17).
- **Elevation**: `shadowSoft` is the only shadow in the app — a tight
  navy-tinted lift. Cards use the `card` token (white + hairline navy border +
  shadowSoft). Never stack or invent shadows.
- Hairlines: `colors.hairline` at `StyleSheet.hairlineWidth` or 1px.

## Iconography

- Ionicons only; **outline variants by default, filled only for the active
  state** (see tab bar: `home-outline` ↔ `home`).
- Sizes: 24 tab bar, 20–22 in-row actions, 12–13 inside section-header chips.
- Icon colors: navy/accent/ink tones only, white on dark surfaces. One color
  per icon (brand: 1-color, 1-stroke).
- Tap targets ≥ 44×44pt — small visual icons get `hitSlop`.

## Components (canonical implementations — reuse, don't fork)

| Component | Source | Rule |
|---|---|---|
| Card | `theme.card` token | White, radius 16, hairline navy border, `shadowSoft`. |
| Section header | `Rows.SectionHeader` | 11pt uppercase Lato Bold, `inkTertiary`. Sits `space[2]` above content. |
| Hero number | `HeroNumber` | Playfair, tabular, count-up ≤800ms. One per screen. |
| **Global header** | `Glass.tsx AppHeader` | THE header — every top-level screen (see **Navy header system**). Mark chip + title left, ≤1 action right. Default = light glass that closes on scroll-down / reopens on scroll-up (diffClamp), status-bar strip stays. `onHero` = white-over-navy fading to glass (pair with `NavyHeroBand`); `solid` = solid navy bar. With a `scrollY`. Content scrolls under it (`paddingTop: insets.top + APP_HEADER_HEIGHT`). No per-screen title/logo rows. |
| Navy hero band | `GreetingHero.tsx NavyHeroBand` | Tier-1 full-bleed navy hero: bleeds to top + side edges, rounded bottom lip, header-safe top padding. Wrap the top module; pair with `AppHeader onHero`. `NavyGradient` is the gradient+glow fill. |
| Sheet header | `Rows.SheetHeader` | Tier-3 navy sheet bar: full-bleed solid navy, white title (+ optional `subtitle`, `right` slot) and white close. First child of the sheet's ScrollView; sheet content uses a 20px gutter + `paddingTop: 0`. Content below stays light. |
| Glass surface | `Glass.tsx` (`GlassSurface`, `TAB_BAR_HEIGHT`) | The only translucent material (BlurView on iOS). Light glass header (default) + tab bar. |
| Chips | hairline border, no fill, `bodySm` | Assistive, never competing with the primary action. |
| Primary action | navy fill, white Lato Bold text, radius pill/12 | One per view. Secondary = ice/ghost fill, accent text. |
| Chat: user bubble | `Chat.tsx` userBubble | Gray fill, right-aligned. |
| Chat: assistant | `Chat.tsx` AssistantBubble | No bubble — bare text, word-fade reveal. |
| Chat: advisor | `Chat.tsx` AdvisorBubble | White card, 3px accent left edge, initials avatar + name + Advisor pill, `RiseIn` entrance. |
| Composer | `ChatScreen` inputBar | Rounded pill (26), grows with draft, navy send orb appears only with text. |
| Disclaimer | `Rows.DisclaimerFooter` | On every client-facing screen bottom. |

## The glance rule

Every screen's key state fits the first viewport — no scrolling to find out
"what's going on." Details collapse behind summary-first modules:

- `Collapsible.tsx CollapsibleCard` is the one container for this: icon +
  section-label title (with a `· count` when it hides a list) + optional
  2-line preview, body behind a tap (Light haptic).
- Cards with their own rich header (e.g. `RecurringCard`, holdings account
  sections) implement the same pattern inline: header always visible, rows
  unfold.
- Lists longer than ~4 rows at screen level either collapse or move behind a
  pushed detail screen. Never nest a card inside a card.
- Order modules by "why did I open this screen" — the live/actionable thing
  first (see advisor ClientDetail: stat strip → live conversation → briefs).

## Motion

All motion lives in `src/anim.tsx` — reuse `RiseIn` (fade + 14px rise, 420ms),
`FadeScaleIn` (chips), `usePulse` (thinking dot). Rules:

- Easing out, 180–420ms. Nothing springs, bounces, or overshoots.
- Native driver wherever the property allows.
- Entrances animate **once** — on arrival, not on re-render (see the
  `animate`-captured-once pattern in `AssistantBubble`).
- Tab switches crossfade at 180ms (`App.tsx ClientTabs`). Screens never slide.
- Charts draw in ≤800ms; count-ups settle before the user can read the number.

## Haptics

`expo-haptics`, called directly at the interaction site (existing idiom):

- `ImpactFeedbackStyle.Light` — ambient: tab switch, chip select, send,
  new-chat, scrubbing ticks.
- `ImpactFeedbackStyle.Medium` — a human moment: advisor interjection arriving.
- `NotificationFeedbackType.Success` — completed commitments only (handoff
  sent). Never for passive events.
- Web builds: expo-haptics no-ops — no platform gate needed.

## Compliance-shaped copy (UI text)

- **No combined-asset totals, performance deltas, or return charts at screen
  level** (stakeholder rule). Screens show structure — managed vs held away vs
  owed, allocation, share-of-account — and guide to chat/advisor. Performance
  figures live only inside tapped-in detail sheets, with the synthetic-data
  disclaimer. Advisor-facing screens are exempt.
- The assistant is a **companion/assistant — never "advisor"**. Advice verbs
  ("recommend", "should") are reserved for the human advisor path.
- Every substantive answer surface keeps the handoff affordance visible.
- Synthetic-data disclaimer stays on every client-facing screen.
