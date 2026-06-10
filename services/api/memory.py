# Client intelligence layer: persistent profile store with provenance.
# Seed file is immutable; runtime file accumulates live facts. Reset = delete runtime.
import json
import random
import re
import string
import time

from data import API_DIR, iso_now

BASE36 = string.digits + string.ascii_lowercase


def _seed_path(client_id):
    return API_DIR / "memory" / f"{client_id}.seed.json"


def _runtime_path(client_id):
    return API_DIR / "memory" / f"{client_id}.runtime.json"


def _new_id(prefix):
    return f"{prefix}_{int(time.time() * 1000)}_{''.join(random.choices(BASE36, k=4))}"


def load_profile(client_id):
    runtime, seed_file = _runtime_path(client_id), _seed_path(client_id)
    if runtime.exists():
        profile = json.loads(runtime.read_text())
    elif seed_file.exists():
        profile = json.loads(seed_file.read_text())
    else:
        profile = {"clientId": client_id, "facts": [], "episodes": []}
    # Seed facts predate fact ids; assign stable ids on first load.
    assigned = False
    for i, f in enumerate(profile["facts"]):
        if not f.get("id"):
            f["id"] = f"fact_seed_{i}"
            assigned = True
    if assigned or not runtime.exists():
        _save(client_id, profile)
    return profile


def _save(client_id, profile):
    _runtime_path(client_id).write_text(json.dumps(profile, indent=2))


def _tokens(s):
    cleaned = re.sub(r"[^a-z0-9$ ]", "", s.lower())
    return {w for w in cleaned.split() if len(w) > 2}


def _similar(a, b):
    ta, tb = _tokens(a), _tokens(b)
    denom = min(len(ta), len(tb) or 1)
    if denom == 0:
        return False
    return len(ta & tb) / denom > 0.6


def add_facts(client_id, facts, episode_id=None):
    profile = load_profile(client_id)
    added = []
    for f in facts:
        if not f.get("fact") or not f.get("category"):
            continue
        existing = next(
            (x for x in profile["facts"] if x["status"] == "active" and _similar(x["fact"], f["fact"])),
            None,
        )
        # Identical restatement: keep the original (provenance points at first mention).
        if existing and existing["fact"] == f["fact"]:
            continue
        # Similar but different wording in the same category: newer fact supersedes.
        if existing and existing["category"] == f["category"]:
            existing["status"] = "superseded"
            existing["superseded_at"] = iso_now()
        elif existing:
            continue
        entry = {
            "id": _new_id("fact"),
            "fact": f["fact"],
            "category": f["category"],
            "source_episode_id": episode_id,
            "source_quote": f.get("source_quote", ""),
            "learned_at": iso_now(),
            "confidence": f.get("confidence", 0.8),
            "status": "active",
        }
        profile["facts"].append(entry)
        added.append(entry)
    if added:
        _save(client_id, profile)
    return added


# Governed deletion: facts are never removed, only marked deleted (append-only audit).
def forget_fact(client_id, fact_id):
    profile = load_profile(client_id)
    fact = next((f for f in profile["facts"] if f["id"] == fact_id and f["status"] == "active"), None)
    if not fact:
        return None
    fact["status"] = "deleted"
    fact["deleted_at"] = iso_now()
    _save(client_id, profile)
    return fact


def append_episode(client_id, session, role, content):
    profile = load_profile(client_id)
    ep = {"id": _new_id("ep"), "session": session, "role": role, "content": content, "timestamp": iso_now()}
    profile["episodes"].append(ep)
    _save(client_id, profile)
    return ep


def episodes_for(client_id, session):
    return [e for e in load_profile(client_id)["episodes"] if e["session"] == session]


def active_facts(client_id):
    return [f for f in load_profile(client_id)["facts"] if f["status"] == "active"]


def reset_profile(client_id):
    runtime = _runtime_path(client_id)
    if runtime.exists():
        runtime.unlink()
    return load_profile(client_id)  # re-seeds from .seed.json


def profile_as_context(client_id):
    facts = active_facts(client_id)
    if not facts:
        return "No profile facts learned yet."
    by_cat: dict[str, list] = {}
    for f in facts:
        by_cat.setdefault(f["category"], []).append(f)
    return "\n".join(
        f"{cat}:\n" + "\n".join(f"  - {f['fact']} (learned {f['learned_at'][:10]})" for f in fs)
        for cat, fs in by_cat.items()
    )
