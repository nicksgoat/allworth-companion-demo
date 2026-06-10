// Client intelligence layer: persistent profile store with provenance.
// Seed file is immutable; runtime file accumulates live facts. Reset = delete runtime.
import { readFileSync, writeFileSync, existsSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { BACKEND_DIR } from "./data.js";

const seedPath = (id) => join(BACKEND_DIR, "memory", `${id}.seed.json`);
const runtimePath = (id) => join(BACKEND_DIR, "memory", `${id}.runtime.json`);

export function loadProfile(clientId) {
  if (existsSync(runtimePath(clientId)))
    return JSON.parse(readFileSync(runtimePath(clientId), "utf8"));
  if (existsSync(seedPath(clientId))) {
    const profile = JSON.parse(readFileSync(seedPath(clientId), "utf8"));
    save(clientId, profile);
    return profile;
  }
  const empty = { clientId, facts: [], episodes: [] };
  save(clientId, empty);
  return empty;
}

function save(clientId, profile) {
  writeFileSync(runtimePath(clientId), JSON.stringify(profile, null, 2));
}

const tokens = (s) => new Set(s.toLowerCase().replace(/[^a-z0-9$ ]/g, "").split(/\s+/).filter((w) => w.length > 2));
function similar(a, b) {
  const ta = tokens(a), tb = tokens(b);
  let inter = 0;
  for (const t of ta) if (tb.has(t)) inter++;
  return inter / Math.min(ta.size, tb.size || 1) > 0.6;
}

export function addFacts(clientId, facts, episodeId) {
  const profile = loadProfile(clientId);
  const added = [];
  for (const f of facts) {
    if (!f.fact || !f.category) continue;
    const dupe = profile.facts.find((x) => x.status === "active" && similar(x.fact, f.fact));
    if (dupe) continue;
    const entry = {
      fact: f.fact,
      category: f.category,
      source_episode_id: episodeId ?? null,
      source_quote: f.source_quote ?? "",
      learned_at: new Date().toISOString(),
      confidence: f.confidence ?? 0.8,
      status: "active",
    };
    profile.facts.push(entry);
    added.push(entry);
  }
  if (added.length) save(clientId, profile);
  return added;
}

export function appendEpisode(clientId, { session, role, content }) {
  const profile = loadProfile(clientId);
  const ep = {
    id: `ep_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
    session, role, content,
    timestamp: new Date().toISOString(),
  };
  profile.episodes.push(ep);
  save(clientId, profile);
  return ep;
}

export function episodesFor(clientId, session) {
  return loadProfile(clientId).episodes.filter((e) => e.session === session);
}

export function activeFacts(clientId) {
  return loadProfile(clientId).facts.filter((f) => f.status === "active");
}

export function resetProfile(clientId) {
  if (existsSync(runtimePath(clientId))) unlinkSync(runtimePath(clientId));
  return loadProfile(clientId); // re-seeds from .seed.json
}

export function profileAsContext(clientId) {
  const facts = activeFacts(clientId);
  if (!facts.length) return "No profile facts learned yet.";
  const byCat = {};
  for (const f of facts) (byCat[f.category] ??= []).push(f);
  return Object.entries(byCat)
    .map(([cat, fs]) => `${cat}:\n` + fs.map((f) => `  - ${f.fact} (learned ${f.learned_at.slice(0, 10)})`).join("\n"))
    .join("\n");
}
