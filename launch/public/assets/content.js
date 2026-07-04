// Allworth Companion — editable content.
// EDIT THIS FILE to update the page. No code changes needed.
//   meta        → version/build shown in the hero pill and footer
//   features[]  → the feature grid on the pitch
//   screenshots → the Screens gallery (drop the image in assets/screenshots/)
//   releases[]  → the Updates / changelog tab (newest first)
//
// Note: the iOS build number is managed remotely by EAS; confirm in App Store Connect.

window.ALW_CONTENT = {
  meta: {
    version: "1.0.0",
    build: 14,
    channel: "TestFlight",
    model: "Azure OpenAI · GPT-4o",
  },

  features: [
    {
      tag: "Conversation",
      title: "Live GPT-4o chat with tool-use",
      body: "A live GPT-4o conversation that calls deterministic financial tools and streams grounded answers, never unsourced guesses.",
    },
    {
      tag: "Memory",
      title: "Multi-turn conversation memory",
      body: "Redis-backed recall. A client can return days later and the assistant picks the thread back up, unprompted.",
    },
    {
      tag: "Analytics",
      title: "Portfolio analytics",
      body: "Allocation vs. target, drift, and concentration flags across held and held-away accounts.",
    },
    {
      tag: "Planning",
      title: "Monte Carlo retirement",
      body: "Success probability and downside cases for the real question: “Can I retire in 2027?”",
    },
    {
      tag: "Tax",
      title: "Tax-aware rebalancer",
      body: "Mock Core-Satellite trades with tax impact and loss-harvesting flags. Nothing executes — it prepares the advisor.",
    },
    {
      tag: "Goals",
      title: "Live, adjustable goals",
      body: "The real goals from the client's plan — funded status, projection, and the monthly amount that closes the gap. Turn the dials, save a plan, and both the assistant and the advisor plan around it.",
    },
    {
      tag: "Concierge",
      title: "Book a meeting, Calendly-style",
      body: "Pick a day, pick a time from the advisor's availability, confirm. Bookings and topic requests land in the advisor's view of that client — no email round trip.",
    },
    {
      tag: "Advisory",
      title: "Advisor handoff",
      body: "Every substantive answer ends with a compliance-driven handoff — and can draft the note for the next meeting.",
    },
    {
      tag: "Presence",
      title: "Advisors inside the thread",
      body: "Advisors see the conversation live and can step into it with their own message. Client, advisor, and assistant share one thread.",
    },
    {
      tag: "Advisor view",
      title: "The client at a glance",
      body: "One screen per client: managed and held-away totals, open items, the live conversation, the request inbox, and an auto-prepared brief — no scrolling to find out what's going on.",
    },
    {
      tag: "Access",
      title: "Face ID and one design language",
      body: "Biometric unlock on return, a single glass header that tucks away as you read, and a calm, summary-first layout on every screen.",
    },
    {
      tag: "Proactive",
      title: "Insight nudges",
      body: "Alerts that matter: spending running over plan, a concentrated position. The detail is one tap away.",
    },
  ],

  // Real captures live in assets/screenshots/. Until an image exists the frame
  // shows a tasteful placeholder, so the page is presentable before capture.
  screenshots: [
    { file: "dashboard.png", caption: "Home", sub: "What needs attention, and the advisor in reach" },
    { file: "goals.png", caption: "My goals", sub: "Real plan goals with adjustable funding" },
    { file: "chat.png", caption: "Goals in chat", sub: "Ask, and the live tracker streams in" },
    { file: "booking.png", caption: "Book a meeting", sub: "Pick a day, pick a time, confirmed" },
    { file: "advisor.png", caption: "Advisor view", sub: "The client at a glance — requests included" },
    { file: "conversation.png", caption: "Three-way thread", sub: "Advisor, client, and assistant together" },
    { file: "vision.png", caption: "Vision", sub: "The Client Intelligence Layer" },
  ],

  releases: [
    {
      build: 14,
      version: "1.0.0",
      date: "2026-07-03",
      channel: "TestFlight",
      title: "The big one: goals, booking, advisor presence, and a new look",
      notes: [
        "My goals is real now. Open it from Home or Profile: the actual goals in your plan, how funded each one is, and dials to set a monthly amount and timeline. Save the plan and both the assistant and your advisor use it from then on.",
        "Ask the chat about your goals and a live tracker streams into the answer — same numbers, same saved plan.",
        "Book a meeting like Calendly: pick a day, pick a real time slot, confirm. Your booking (or topic request) shows up in your advisor's view immediately.",
        "Your advisor is in the thread. Advisors watch the conversation live and can reply inside it — client, advisor, and assistant in one chat, clearly attributed.",
        "A full advisor side: switch to advisor view from Profile, see each client at a glance (totals, open items, live conversation, request inbox, auto-prepared brief), and open the full conversation to read and reply.",
        "New look everywhere: one glass header that tucks away as you scroll, Face ID unlock when you return, a calmer Home, and every screen showing what matters on the first screen — details one tap deeper.",
        "Wealth shows structure, not scores: what's managed, what's held away, what's owed. Performance detail lives in tapped-in views.",
      ],
    },
    {
      build: 11,
      version: "1.0.0",
      date: "2026-06-22",
      channel: "TestFlight",
      title: "Design-system foundation + refreshed access",
      notes: [
        "Decluttered chat, dashboard, and advisor surfaces into a calmer, upmarket layout.",
        "Added a shared spacing / type / radius / shadow system across the app.",
        "Updated demo sign-in to nicole@demo.com (Maya) and kyle@demo.com (Kenny).",
      ],
    },
    {
      build: 10,
      version: "1.0.0",
      date: "2026-06-22",
      channel: "TestFlight",
      title: "Analytics + planning integration",
      notes: [
        "Modified Dietz performance, a tax-aware Core-Satellite rebalancer, and chat fixes.",
        "Rebalancer and Monte-Carlo results now render as rich in-chat widgets.",
        "Backend hardening for stateless, multi-instance operation.",
      ],
    },
    {
      build: 9,
      version: "1.0.0",
      date: "2026-06-21",
      channel: "TestFlight",
      title: "Conversation memory + second client",
      notes: [
        "Redis-backed multi-turn memory — the assistant recalls prior turns with provenance.",
        "Added the Kenny Smith household with a concentrated NVDA position.",
        "Seeded advisor meeting notes and gave the assistant a more human voice.",
      ],
    },
    {
      build: "Foundation",
      version: "1.0.0",
      date: "Jun 15–19, 2026",
      channel: "Internal",
      title: "Live AI + the demo foundation",
      notes: [
        "Brought up live Azure OpenAI GPT-4o chat with a real tool-use loop.",
        "Rebuilt the net-worth charts and redesigned sign-in.",
        "Wired the mock↔live switch and the Fly.io deployment path.",
      ],
    },
  ],
};
