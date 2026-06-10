// Streaming chat: Anthropic tool-use loop over SSE, with cached fallback
// responses so the demo never dies on stage.
import Anthropic from "@anthropic-ai/sdk";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { BACKEND_DIR } from "./data.js";
import { toolDefinitions, runTool, TOOL_LABELS } from "./tools.js";
import { profileAsContext, addFacts, appendEpisode, episodesFor } from "./memory.js";
import { STABLE_SYSTEM, volatileContext } from "../prompts/system.js";

const CHAT_MODEL = "claude-opus-4-7";
const EXTRACT_MODEL = "claude-haiku-4-5";
const MAX_TOOL_ROUNDS = 8;

const apiKey = process.env.ANTHROPIC_API_KEY || "";
const client = apiKey ? new Anthropic({ apiKey }) : null;

const SOURCE_NAMES = {
  get_accounts: "Accounts",
  get_portfolio: "Portfolio",
  get_financial_plan: "Financial plan",
  get_spending: "Spending",
  get_client_profile: "Your profile",
  update_client_profile: "Your profile",
  simulate_tax_impact: "Tax estimate",
  get_advisor_brief: "Advisor brief",
};

const loadFallback = (name) =>
  JSON.parse(readFileSync(join(BACKEND_DIR, "fallbacks", `${name}.json`), "utf8"));

function pickFallback(userText, session) {
  const text = userText.toLowerCase();
  const beat3 = loadFallback("beat3");
  const beat4 = loadFallback("beat4");
  const changed = loadFallback("whats_changed");
  // Wednesday: "what changed?" beats the memory beat, which beats everything else.
  if (session === "wednesday" && changed.match.some((m) => text.includes(m))) return changed;
  if (session === "wednesday" && beat4.match.some((m) => text.includes(m))) return beat4;
  if (beat3.match.some((m) => text.includes(m))) return beat3;
  return session === "wednesday" ? beat4 : beat3;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function streamFallback({ userText, session, send }) {
  const fb = pickFallback(userText, session);
  for (const tool of fb.tools) {
    send("tool_start", { name: tool, label: TOOL_LABELS[tool] ?? tool });
    await sleep(450);
    send("tool_end", { name: tool });
  }
  // Stream the cached text in word chunks so it feels live.
  const words = fb.text.split(" ");
  for (let i = 0; i < words.length; i += 6) {
    send("text", { delta: words.slice(i, i + 6).join(" ") + " " });
    await sleep(40);
  }
  send("done", { sources: fb.sources, fallback: true, suggested: fb.suggested ?? [] });
  return fb.text;
}

export async function streamChat({ clientId, session, messages, send }) {
  const userText = lastUserText(messages);
  let assistantText = "";

  if (!client) {
    assistantText = await streamFallback({ userText, session, send });
  } else {
    try {
      assistantText = await streamLive({ clientId, session, messages, send });
    } catch (err) {
      console.error("[chat] live stream failed, using fallback:", err.message);
      send("text", { delta: "\n" });
      assistantText = await streamFallback({ userText, session, send });
    }
  }

  // Persist the turn and extract facts in the background (never blocks the response).
  appendEpisode(clientId, { session, role: "user", content: userText });
  appendEpisode(clientId, { session, role: "assistant", content: assistantText });
  extractFacts(clientId, userText).catch((e) => console.error("[extract]", e.message));

  return assistantText;
}

async function streamLive({ clientId, session, messages, send }) {
  const system = [
    { type: "text", text: STABLE_SYSTEM, cache_control: { type: "ephemeral" } },
    {
      type: "text",
      text: volatileContext({
        clientId,
        session,
        profileContext: profileAsContext(clientId),
        priorSessionSummary: session === "wednesday" ? mondayRecap(clientId) : null,
      }),
    },
  ];

  const convo = [...messages];
  const sources = new Set();
  let fullText = "";

  for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
    const stream = client.messages.stream({
      model: CHAT_MODEL,
      max_tokens: 2048,
      system,
      tools: toolDefinitions,
      messages: convo,
    });

    stream.on("streamEvent", (ev) => {
      if (ev.type === "content_block_start" && ev.content_block?.type === "tool_use") {
        const name = ev.content_block.name;
        send("tool_start", { name, label: TOOL_LABELS[name] ?? name });
      }
    });
    stream.on("text", (delta) => {
      fullText += delta;
      send("text", { delta });
    });

    const response = await stream.finalMessage();
    convo.push({ role: "assistant", content: response.content });

    if (response.stop_reason !== "tool_use") break;

    const results = [];
    for (const block of response.content) {
      if (block.type !== "tool_use") continue;
      const result = runTool(block.name, block.input, clientId);
      sources.add(SOURCE_NAMES[block.name] ?? block.name);
      send("tool_end", { name: block.name });
      results.push({
        type: "tool_result",
        tool_use_id: block.id,
        content: JSON.stringify(result),
      });
    }
    convo.push({ role: "user", content: results });
  }

  send("done", { sources: [...sources], fallback: false, suggested: suggestedFor(session) });
  return fullText;
}

export const suggestedFor = (session) =>
  session === "wednesday"
    ? ["What changed since I was last here?", "Where did we land on the SpaceX IPO?"]
    : ["What would $200K into the SpaceX IPO mean for me?"];

function mondayRecap(clientId) {
  const eps = episodesFor(clientId, "monday");
  if (!eps.length) return null;
  const summary = eps.filter((e) => e.role === "assistant").map((e) => e.content).join("\n");
  return summary || null;
}

function lastUserText(messages) {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "user") continue;
    if (typeof m.content === "string") return m.content;
    const text = m.content.filter((b) => b.type === "text").map((b) => b.text).join(" ");
    if (text) return text;
  }
  return "";
}

// Lightweight second-model pass: pull durable facts out of the client's message.
async function extractFacts(clientId, userText) {
  if (!client || !userText) return;
  const response = await client.messages.create({
    model: EXTRACT_MODEL,
    max_tokens: 1024,
    system:
      'Extract durable facts about the client from their message — goals, preferences, concerns, liquidity events, outside assets, life events. Only facts that matter months from now; skip questions and small talk. Respond with ONLY a JSON array (possibly empty): [{"fact": string, "category": "goals"|"preferences"|"concerns"|"liquidity_events"|"outside_assets_mentioned"|"life_events", "source_quote": string, "confidence": number}]',
    messages: [{ role: "user", content: userText }],
  });
  const text = response.content.filter((b) => b.type === "text").map((b) => b.text).join("");
  const match = text.match(/\[[\s\S]*\]/);
  if (!match) return;
  const facts = JSON.parse(match[0]);
  if (Array.isArray(facts) && facts.length) {
    const added = addFacts(clientId, facts, null);
    if (added.length) console.log(`[memory] learned ${added.length} fact(s) about ${clientId}`);
  }
}
