"""Cached fallback chat responses for the scripted demo beats."""

import json

from allworth_api.config import FALLBACKS_DIR


def load_fallback(name):
    return json.loads((FALLBACKS_DIR / f"{name}.json").read_text())


def pick_fallback(user_text, session):
    text = user_text.lower()
    beat3 = load_fallback("beat3")
    beat4 = load_fallback("beat4")
    changed = load_fallback("whats_changed")
    # Wednesday: "what changed?" beats the memory beat, which beats everything else.
    if session == "wednesday" and any(m in text for m in changed["match"]):
        return changed
    if session == "wednesday" and any(m in text for m in beat4["match"]):
        return beat4
    if any(m in text for m in beat3["match"]):
        return beat3
    return beat4 if session == "wednesday" else beat3
