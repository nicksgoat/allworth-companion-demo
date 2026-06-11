# Client intelligence layer: persistent profile store with provenance.
# Seed file is immutable; runtime file accumulates live facts. Reset = delete runtime.
from allworth_api.domain.facts import similar
from allworth_api.domain.formatting import iso_now
from allworth_api.infrastructure.profile_store import (
    load_profile,
    new_id,
    runtime_path,
    save_profile,
)


def add_facts(client_id: str, facts: list[dict], episode_id: str | None = None) -> list[dict]:
    profile = load_profile(client_id)
    added = []
    for f in facts:
        if not f.get("fact") or not f.get("category"):
            continue
        existing = next(
            (x for x in profile["facts"] if x["status"] == "active" and similar(x["fact"], f["fact"])),
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
            "id": new_id("fact"),
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
        save_profile(client_id, profile)
    return added


# Governed deletion: facts are never removed, only marked deleted (append-only audit).
def forget_fact(client_id: str, fact_id: str) -> dict | None:
    profile = load_profile(client_id)
    fact = next((f for f in profile["facts"] if f["id"] == fact_id and f["status"] == "active"), None)
    if not fact:
        return None
    fact["status"] = "deleted"
    fact["deleted_at"] = iso_now()
    save_profile(client_id, profile)
    return fact


def append_episode(client_id: str, session: str, role: str, content: str) -> dict:
    profile = load_profile(client_id)
    ep = {"id": new_id("ep"), "session": session, "role": role, "content": content, "timestamp": iso_now()}
    profile["episodes"].append(ep)
    save_profile(client_id, profile)
    return ep


def episodes_for(client_id: str, session: str) -> list[dict]:
    return [e for e in load_profile(client_id)["episodes"] if e["session"] == session]


def active_facts(client_id: str) -> list[dict]:
    return [f for f in load_profile(client_id)["facts"] if f["status"] == "active"]


def reset_profile(client_id: str) -> dict:
    runtime = runtime_path(client_id)
    if runtime.exists():
        runtime.unlink()
    return load_profile(client_id)  # re-seeds from .seed.json


def profile_as_context(client_id: str) -> str:
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
