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
    build: 13,
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
      tag: "Advisory",
      title: "Advisor handoff",
      body: "Every substantive answer ends with a compliance-driven handoff — and can draft the note for the next meeting.",
    },
    {
      tag: "Presence",
      title: "Advisors inside the thread",
      body: "Advisors see the conversation and can step into it with their own message. Client, advisor, and assistant share one thread.",
    },
    {
      tag: "Relationship",
      title: "Meeting notes",
      body: "Past advisor meeting summaries surfaced in-app, so context never resets between conversations.",
    },
    {
      tag: "Proactive",
      title: "Insight nudges",
      body: "Alerts that matter: spending running over plan, a concentrated position. The detail is one tap away.",
    },
    {
      tag: "Households",
      title: "Two client profiles",
      body: "Maya, semi-retired and income-focused, and Kenny, working through a concentrated NVDA position.",
    },
  ],

  // Real captures live in assets/screenshots/. Until an image exists the frame
  // shows a tasteful placeholder, so the page is presentable before capture.
  screenshots: [
    { file: "dashboard.png", caption: "Dashboard", sub: "Net worth, held & held-away" },
    { file: "chat.png", caption: "Grounded chat", sub: "Live tool calls → sources" },
    { file: "advisor.png", caption: "Advisor brief", sub: "Auto-prepared for the meeting" },
    { file: "vision.png", caption: "Vision", sub: "The Client Intelligence Layer" },
  ],

  releases: [
    {
      build: 13,
      version: "1.0.0",
      date: "2026-07-03",
      channel: "TestFlight",
      title: "Home as a guide + live goal planning",
      notes: [
        "Home now leads with what needs attention and quick actions; totals and charts live one tap away in Wealth.",
        "Talk about a goal in chat and an adjustable plan appears — turn the timeline and contribution dials, watch the projection move.",
        "Advisor concierge (book a time, request a topic), a document vault, chat history, and haptic polish throughout.",
      ],
    },
    {
      build: 12,
      version: "1.0.0",
      date: "2026-07-03",
      channel: "TestFlight",
      title: "Advisor presence + a rebuilt chat",
      notes: [
        "Advisors can now message directly inside a client's assistant thread. It becomes a live three-way conversation the assistant understands as context.",
        "Rebuilt chat shell: assistant identity header, new chat, a composer that grows with the draft, and jump-to-latest.",
        "The advisor view adds a live conversation transcript beside the auto-prepared brief.",
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
