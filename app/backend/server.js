// Allworth Companion demo backend. Demo-grade by design: no auth, in-memory
// conversation state, synthetic data only.
import express from "express";
import { seed, fmtUSD, accountsFor, spendingSummary, portfolioFor } from "./lib/data.js";
import { nudgesFor } from "./lib/nudges.js";
import { activeFacts, forgetFact, resetProfile, episodesFor } from "./lib/memory.js";
import { runTool } from "./lib/tools.js";
import { streamChat } from "./lib/chat.js";

const app = express();
app.use(express.json());

// Conversation state per client+session, reset via demo control.
const conversations = new Map();
const convoKey = (clientId, session) => `${clientId}:${session}`;

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, llm: Boolean(process.env.ANTHROPIC_API_KEY), generatedAt: seed.generatedAt });
});

app.get("/api/clients/:id/dashboard", (req, res) => {
  const a = accountsFor();
  const s = spendingSummary(3);
  res.json({
    client: seed.personas.clients.find((c) => c.id === req.params.id) ?? null,
    advisor: seed.personas.advisors[0],
    netWorth: a.netWorth,
    netWorthHistory: seed.netWorthHistory,
    allworthTotal: a.allworthTotal,
    heldAwayTotal: a.heldAwayTotal,
    liabilitiesTotal: a.liabilitiesTotal,
    accounts: { allworth: a.allworth, outside: a.outside },
    spending: { avg3mo: s.avg3mo, plan: s.plan, overPlanPct: s.overPlanPct },
    nudges: nudgesFor(req.params.id),
    liquidityEvent: seed.liquidityEvent,
    disclaimer: seed.disclaimer,
  });
});

app.get("/api/clients/:id/nudges", (req, res) => res.json({ nudges: nudgesFor(req.params.id) }));

app.get("/api/clients/:id/spending", (req, res) => {
  const s = spendingSummary(Number(req.query.months) || 3);
  res.json(s);
});

app.get("/api/clients/:id/portfolio", (_req, res) => res.json(portfolioFor()));

app.get("/api/clients/:id/profile", (req, res) => {
  res.json({ clientId: req.params.id, facts: activeFacts(req.params.id) });
});

// Governed memory: "Forget this detail" — marks the fact deleted, never erases it.
app.delete("/api/clients/:id/facts/:factId", (req, res) => {
  const fact = forgetFact(req.params.id, req.params.factId);
  if (!fact) return res.status(404).json({ error: "fact not found or not active" });
  res.json({ ok: true, fact });
});

// Proactive greeting for the chat screen — deterministic so Beat 4 never flakes.
app.get("/api/clients/:id/proactive", (req, res) => {
  const session = req.query.session ?? "wednesday";
  if (session === "wednesday") {
    const facts = activeFacts(req.params.id);
    const ipo = facts.find((f) => f.category === "liquidity_events");
    if (ipo) {
      return res.json({
        message:
          "Welcome back, Maya. Last time you were weighing $200K into the SpaceX IPO — your deadline is Sunday, June 15. Want to pick up where we left off, or look at something else?",
        basedOn: { fact: ipo.fact, source_quote: ipo.source_quote, learned_at: ipo.learned_at },
      });
    }
  }
  res.json({
    message: "Hi Maya — I can help you understand your accounts, spending, plan, or anything you're weighing. What's on your mind?",
    basedOn: null,
  });
});

app.get("/api/clients/:id/chat-history", (req, res) => {
  const session = req.query.session ?? "wednesday";
  res.json({ session, episodes: episodesFor(req.params.id, session) });
});

app.get("/api/advisors/:id/book", (req, res) => {
  // Maya's nudge count comes from the live rule engine; other households are static.
  const households = seed.book.map((h) =>
    h.clientId === "maya" ? { ...h, openNudges: nudgesFor(h.clientId).length } : h
  );
  res.json({
    advisor: seed.personas.advisors.find((a) => a.id === req.params.id) ?? seed.personas.advisors[0],
    households,
  });
});

app.get("/api/advisors/:id/clients/:clientId/brief", (req, res) => {
  const data = runTool("get_advisor_brief", {}, req.params.clientId);
  res.json({ ...data, narrative: briefNarrative(data) });
});

app.post("/api/chat", async (req, res) => {
  const { clientId = "maya", session = "wednesday", message } = req.body ?? {};
  if (!message) return res.status(400).json({ error: "message required" });

  res.writeHead(200, {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  });
  const send = (event, data) => res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);

  const key = convoKey(clientId, session);
  const history = conversations.get(key) ?? [];
  const messages = [...history, { role: "user", content: message }];

  try {
    const assistantText = await streamChat({ clientId, session, messages, send });
    conversations.set(key, [...messages, { role: "assistant", content: assistantText }]);
  } catch (err) {
    console.error("[chat] unrecoverable:", err);
    send("error", { message: "Something went wrong. Please try again." });
  }
  res.end();
});

app.post("/api/demo/reset", (req, res) => {
  const clientId = req.body?.clientId ?? "maya";
  conversations.clear();
  const profile = resetProfile(clientId);
  res.json({ ok: true, clientId, facts: profile.facts.length });
});

function briefNarrative(d) {
  const nudge = d.openNudges[0];
  const lines = [
    `Maya is weighing a ${fmtUSD(d.liquidityEvent.amount)} allocation to the ${d.liquidityEvent.label.replace(" allocation", "")} with a ${d.liquidityEvent.deadline} deadline — she has worked through funding sources with the assistant and has open questions on liquidity vs. her $9,000/mo income draw.`,
    `Held-away assets detected: ${fmtUSD(d.heldAwayDetected)} across ${d.heldAwayAccounts.length} outside accounts (largest: Fidelity 401(k), ${fmtUSD(385000)}) — a consolidation conversation may be timely if the IPO discussion opens the door.`,
    nudge ? `Open nudge: ${nudge.title.toLowerCase()} (${nudge.headline}).` : null,
    `She prefers plain-English explanations and is tax-sensitive about her 2015 Apple shares.`,
  ];
  return lines.filter(Boolean).join("\n");
}

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Allworth demo backend listening on :${PORT}`));
