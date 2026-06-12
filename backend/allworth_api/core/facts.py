"""Fact similarity rules for the governed memory's dedupe/supersede logic."""

import re


def tokens(s: str) -> set[str]:
    cleaned = re.sub(r"[^a-z0-9$ ]", "", s.lower())
    return {w for w in cleaned.split() if len(w) > 2}


def similar(a: str, b: str) -> bool:
    ta, tb = tokens(a), tokens(b)
    denom = min(len(ta), len(tb) or 1)
    if denom == 0:
        return False
    return len(ta & tb) / denom > 0.6
