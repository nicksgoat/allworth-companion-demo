"""Search logic: keyword → best-matching atomic entry.

Same retrieval rules as the FastAPI original, but synchronous for Flask.
"""

from __future__ import annotations

import logging
import os
import re
import time

from jarvis.knowledge_loader import (
    RESOURCES,
    explain_metric,
    file_signature,
    reload_resources,
    search_knowledge,
)

logger = logging.getLogger(__name__)

_RELOAD_CHECK_SECONDS = float(os.environ.get("JARVIS_RELOAD_CHECK_SECONDS", "30"))
_last_reload_check = 0.0
_last_signature: tuple[tuple[str, int], ...] = ()

_MAX_REPLY_CHARS = 1200
_SECTION_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_QUESTION_NOISE = {
    "a", "about", "an", "and", "are", "define", "definition", "do", "does",
    "explain", "for", "how", "in", "is", "me", "mean", "means", "of", "on",
    "or", "our", "stands", "tell", "the", "to", "was", "were", "what",
    "whats", "why", "you",
}

# Sidebar grouping. Each YAML's `category:` field is preferred; this dict is
# a fallback for files that don't declare one.
_DOC_CATEGORY: dict[str, str] = {
    "fee-schedule": "Metrics & Fees",
    "industry-benchmarks": "Metrics & Fees",
    "rebalancing-policy": "Policies",
    "service-standards": "Policies",
    "risk-tolerance": "Policies",
    "investment-philosophy": "Policies",
    "analysis-playbooks": "Playbooks",
    "funnel-cost-process": "Playbooks",
    "tool-selection-policy": "Playbooks",
    "data-caveats": "Data Model",
    "entity-taxonomy": "Data Model",
    "client-priority": "Policies",
    "docs-library": "Reference",
    "user-context": "Reference",
}
_CATEGORY_ORDER = [
    "Metric Definitions",
    "Metrics & Fees",
    "Policies",
    "Playbooks",
    "Compliance",
    "Data Model",
    "Reference",
]


def search(question: str) -> dict:
    """Structured lookup. Returns {question, body, source, uri} or {question, error}."""
    question = (question or "").strip()
    if not question:
        return {"question": question, "error": "Ask me about a metric or term (e.g. NCNM)."}

    _maybe_reload()
    keywords = _strip_noise(question)
    lookup = keywords or question

    result = explain_metric(metric=lookup)
    if not result.get("matches"):
        result = search_knowledge(query=lookup, top_n=5)

    matches = result.get("matches") or []
    if not matches:
        return {"question": question, "error": f"No match found for '{question}'."}

    best = matches[0]
    body = _extract_section(best["uri"], lookup) or best.get("snippet", "")
    source = best.get("category") or best.get("name") or best.get("uri", "")
    return {
        "question": question,
        "body": body,
        "source": source,
        "uri": best.get("uri", ""),
    }


def answer(question: str) -> str:
    """Markdown-formatted wrapper around search() for CLI-style output."""
    result = search(question)
    if "error" in result:
        return result["error"]
    reply = (
        f"**{result['question']}**\n\n"
        f"{result['body']}\n\n"
        f"_Source: {result['source']}_"
    )
    if len(reply) > _MAX_REPLY_CHARS:
        reply = reply[: _MAX_REPLY_CHARS - 1] + "…"
    return reply


def search_all(query: str, limit: int = 8) -> list[dict]:
    """Return multiple ranked matches for the search-results view."""
    _maybe_reload()
    query = (query or "").strip()
    if not query:
        return []
    keywords = _strip_noise(query)
    lookup = keywords or query
    result = search_knowledge(query=lookup, top_n=limit)
    matches = result.get("matches") or []
    out: list[dict] = []
    for m in matches:
        uri = m.get("uri", "")
        section = _extract_section(uri, lookup)
        snippet = (section or m.get("snippet", "")).strip()
        if len(snippet) > 320:
            snippet = snippet[:319].rstrip() + "…"
        out.append(
            {
                "key": _key_for_uri(uri),
                "name": m.get("name"),
                "uri": uri,
                "snippet": snippet,
            }
        )
    return out


def _category_for(key: str, res: dict) -> str:
    explicit = res.get("category")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return _DOC_CATEGORY.get(key, "Reference")


def list_docs() -> dict:
    _maybe_reload()
    buckets: dict[str, list[dict]] = {}
    for key, res in RESOURCES.items():
        cat = _category_for(key, res)
        buckets.setdefault(cat, []).append(
            {
                "key": key,
                "name": res.get("name", key),
                "uri": res.get("uri", ""),
                "description": res.get("description", ""),
                "draft": bool(res.get("draft")),
            }
        )
    for cat in buckets:
        buckets[cat].sort(key=lambda d: d["name"])
    groups = [
        {"category": cat, "docs": buckets[cat]}
        for cat in _CATEGORY_ORDER
        if cat in buckets
    ]
    for cat in buckets:
        if cat not in _CATEGORY_ORDER:
            groups.append({"category": cat, "docs": buckets[cat]})
    return {"groups": groups}


def get_doc(key: str) -> dict | None:
    _maybe_reload()
    res = RESOURCES.get(key)
    if not res:
        return None
    return {
        "key": key,
        "name": res.get("name", key),
        "uri": res.get("uri", ""),
        "description": res.get("description", ""),
        "keywords": res.get("keywords", []),
        "content": res.get("content", ""),
        "category": _category_for(key, res),
        "draft": bool(res.get("draft")),
    }


def known_categories() -> list[str]:
    _maybe_reload()
    extras = {
        res.get("category")
        for res in RESOURCES.values()
        if isinstance(res.get("category"), str) and res.get("category", "").strip()
    }
    return list(_CATEGORY_ORDER) + sorted(e for e in extras if e not in _CATEGORY_ORDER)


# ── Internals ─────────────────────────────────────────────────────────────


def _strip_noise(text: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9']+", text)
    kept = [t for t in tokens if t.lower() not in _QUESTION_NOISE]
    return " ".join(kept)


def _extract_section(uri: str, query: str) -> str | None:
    resource = _resource_by_uri(uri)
    if not resource:
        return None
    content = resource.get("content", "")
    if not content:
        return None

    headings = list(_SECTION_HEADING_RE.finditer(content))
    if not headings:
        return None

    query_terms = _query_terms(query)
    if not query_terms:
        return None

    best_idx = -1
    best_score = 0
    for i, m in enumerate(headings):
        heading_words = set(re.findall(r"[a-z0-9]+", m.group(2).lower()))
        score = len(query_terms & heading_words)
        if score > best_score:
            best_score = score
            best_idx = i

    if best_idx < 0:
        return None

    start = headings[best_idx].start()
    end = headings[best_idx + 1].start() if best_idx + 1 < len(headings) else len(content)
    return content[start:end].strip()


def _query_terms(query: str) -> set[str]:
    return {
        t for t in re.findall(r"[a-z0-9]+", query.lower())
        if len(t) > 1 and t not in _QUESTION_NOISE
    }


def _resource_by_uri(uri: str) -> dict | None:
    for res in RESOURCES.values():
        if res.get("uri") == uri:
            return res
    return None


def _key_for_uri(uri: str) -> str | None:
    for key, res in RESOURCES.items():
        if res.get("uri") == uri:
            return key
    return None


def _maybe_reload() -> None:
    """Re-scan YAML mtimes every _RELOAD_CHECK_SECONDS; reload if changed."""
    global _last_reload_check, _last_signature
    now = time.monotonic()
    if now - _last_reload_check < _RELOAD_CHECK_SECONDS:
        return
    _last_reload_check = now
    try:
        sig = file_signature()
    except OSError:
        return
    if sig and sig != _last_signature:
        if _last_signature:
            logger.info("Jarvis YAMLs changed, reloading")
        try:
            reload_resources()
            _last_signature = sig
        except Exception:
            logger.exception("reload_resources failed")


def force_reload() -> int:
    global _last_reload_check, _last_signature
    count = reload_resources()
    _last_reload_check = time.monotonic()
    _last_signature = file_signature()
    return count


def bump_reload_marker() -> None:
    """Force the next search to re-stat (called after storage.py writes)."""
    global _last_reload_check
    _last_reload_check = 0.0
