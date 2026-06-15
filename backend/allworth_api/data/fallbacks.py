"""Deterministic, intent-routed scripted chat responses (no LLM involved).

When no LLM provider is configured, the chat runs on these cached "beats."
pick_fallback() scores every intent by keyword hits and returns the best match,
with a graceful greeting for anything off-script — so a clicked question never
lands on an unrelated answer.
"""

import json

from allworth_api.config import FALLBACKS_DIR


def load_fallback(name: str) -> dict:
    return json.loads((FALLBACKS_DIR / f"{name}.json").read_text())


# Topic intents in priority order — earlier wins on a score tie. The SpaceX IPO
# beats (session-dependent) and the greeting default are handled separately.
_TOPIC_INTENTS = [
    "whats_changed",   # Wednesday return-visit recap (session-gated below)
    "spending",
    "taxes",
    "roth",
    "concentration",
    "goals",
    "retirement",
    "networth",
    "portfolio",
    "advisor",
    "advice",          # non-directive guard — last, so any real topic wins
]

_IPO_KEYWORDS = ["spacex", "ipo", "200k", "200,000"]


def _score(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


def pick_fallback(user_text: str, session: str) -> dict:
    """Route a message to the best-matching scripted answer.

    Score each intent by how many of its keywords appear; the highest score wins,
    with priority order breaking ties. Off-topic messages return the greeting
    rather than falling through to an unrelated script.
    """
    text = user_text.lower()
    candidates: list[tuple[int, int, dict]] = []  # (score, priority, fallback)

    for priority, name in enumerate(_TOPIC_INTENTS):
        if name == "whats_changed" and session != "wednesday":
            continue  # the recap only makes sense on the Wednesday return visit
        fb = load_fallback(name)
        score = _score(text, fb["match"])
        if score:
            candidates.append((score, priority, fb))

    # The SpaceX IPO beat depends on the session: the follow-up on Wednesday,
    # the first-look analysis otherwise.
    ipo_score = _score(text, _IPO_KEYWORDS)
    if ipo_score:
        ipo_name = "beat4" if session == "wednesday" else "beat3"
        candidates.append((ipo_score, len(_TOPIC_INTENTS), load_fallback(ipo_name)))

    if not candidates:
        return load_fallback("greeting")

    candidates.sort(key=lambda c: (-c[0], c[1]))
    return candidates[0][2]
