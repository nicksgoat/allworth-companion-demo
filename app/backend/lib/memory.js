// Client intelligence layer: persistent profile store with provenance.
// Seed file is immutable; runtime file accumulates live facts. Reset = delete runtime.
import { readFileSync, writeFileSync, existsSync, unlinkSync } from "node:fs";
import { join } from "node:path";
import { BACKEND_DIR } from "./data.js";

const seedPath = (id) => join(BACKEND_DIR, "memory", `${id}.seed.json`);
const runtimePath = (id) => join(BACKEND_DIR, "memory", `${id}.runtime.json`);

export function loadProfile(clientId) {
  let profile;
  if (existsSync(runtimePath(clientId))) {
    profile = JSON.parse(readFileSync(runtimePath(clientId), "utf8"));
  } else if (existsSync(seedPath(clientId))) {
    profile = JSON.parse(readFileSync(seedPath(clientId), "utf8"));
  } else {
    profile = { clientId, facts: [], episodes: [] };
  }
  // Seed facts predate fact ids; assign stable ids on first load.
  let assigned = false;
  profile.facts.forEach((f, i) => {
    if (!f.id) {
      f.id = `fact_seed_${i}`;
      assigned = true;
    }
  });
  if (assigned || !existsSync(runtimePath(clientId))) save(clientId, profile);
  return profile;
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
    const existing = profile.facts.find((x) => x.status === "active" && similar(x.fact, f.fact));
    // Identical restatement: keep the original (provenance points at first mention).
    if (existing && existing.fact === f.fact) continue;
    // Similar but different wording in the same category: newer fact supersedes.
    if (existing && existing.category === f.category) {
      existing.status = "superseded";
      existing.superseded_at = new Date().toISOString();
    } else if (existing) {
      continue;
    }
    const entry = {
      id: `fact_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
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

// Governed deletion: facts are never removed, only marked deleted (append-only audit).
export function forgetFact(clientId, factId) {
  const profile = loadProfile(clientId);
  const fact = profile.facts.find((f) => f.id === factId && f.status === "active");
  if (!fact) return null;
  fact.status = "deleted";
  fact.deleted_at = new Date().toISOString();
  save(clientId, profile);
  return fact;
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
