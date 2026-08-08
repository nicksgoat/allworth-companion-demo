"""Framework YAML loader + keyword search.

Reads YAMLs from ``backend/jarvis/knowledge/`` (or the path set by the
``JARVIS_FRAMEWORKS_DIR`` env var) and exposes a keyword-search function
and a mutable ``RESOURCES`` dict that ``handler`` and ``routes`` read.

No web-framework dependencies — pure Python + PyYAML.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_FRAMEWORKS_DIR = Path(__file__).resolve().parent / "knowledge"
_reload_lock = threading.Lock()


def frameworks_dir() -> Path:
    override = os.environ.get("JARVIS_FRAMEWORKS_DIR")
    return Path(override) if override else _DEFAULT_FRAMEWORKS_DIR


def file_signature() -> tuple[tuple[str, int], ...]:
    """Change-detection key: (filename, mtime_ns) for every YAML in the dir."""
    d = frameworks_dir()
    if not d.is_dir():
        return ()
    return tuple(sorted((f.name, f.stat().st_mtime_ns) for f in d.glob("*.yaml")))


def _load_resources() -> dict[str, dict[str, Any]]:
    resources: dict[str, dict[str, Any]] = {}
    directory = frameworks_dir()
    if not directory.is_dir():
        logger.warning("Jarvis frameworks directory not found: %s", directory)
        return resources

    for yaml_file in sorted(directory.glob("*.yaml")):
        try:
            meta = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            if not isinstance(meta, dict):
                logger.warning("Skipping %s: not a YAML mapping", yaml_file.name)
                continue
            if meta.get("deprecated"):
                continue
            name = meta.get("name")
            uri = meta.get("uri")
            if not name or not uri:
                logger.warning("Skipping %s: missing name or uri", yaml_file.name)
                continue
            key = yaml_file.stem
            resources[key] = {
                "uri": uri,
                "name": name,
                "description": meta.get("description", ""),
                "content": (meta.get("content") or "").strip(),
                "keywords": meta.get("keywords", []) or [],
                "directive": (meta.get("directive") or "").strip(),
                "category": meta.get("category"),
                "draft": bool(meta.get("draft")),
                # Optional cross-links to the data catalog (read by the unified
                # /catalog explorer; ignored by the MCP server).
                "related_tables": meta.get("related_tables", []) or [],
                "related_columns": meta.get("related_columns", []) or [],
            }
        except Exception:
            logger.exception("Failed to load %s", yaml_file.name)
    return resources


RESOURCES: dict[str, dict[str, Any]] = _load_resources()


def reload_resources() -> int:
    """Re-scan the dir; swap RESOURCES in place. Returns new count."""
    fresh = _load_resources()
    with _reload_lock:
        RESOURCES.clear()
        RESOURCES.update(fresh)
    logger.info("Jarvis: reloaded %d resources from %s", len(fresh), frameworks_dir())
    return len(fresh)


_SNIPPET_LIMIT = 280


def _search_resources(query: str, limit: int = 5) -> list[dict[str, Any]]:
    query_lower = (query or "").strip().lower()
    if not query_lower:
        return []

    scored: list[tuple[int, dict[str, Any]]] = []
    for resource in RESOURCES.values():
        haystack = " ".join(
            [
                resource.get("name", ""),
                resource.get("description", ""),
                resource.get("content", ""),
                " ".join(resource.get("keywords", [])),
            ]
        ).lower()
        if query_lower not in haystack and not any(
            term in haystack for term in query_lower.split()
        ):
            continue

        score = 0
        if query_lower in resource.get("name", "").lower():
            score += 5
        if query_lower in resource.get("description", "").lower():
            score += 3
        for keyword in resource.get("keywords", []):
            if query_lower == str(keyword).lower():
                score += 4

        snippet_source = resource.get("content", "").strip().replace("\n", " ")
        snippet = snippet_source[:_SNIPPET_LIMIT] + (
            "…" if len(snippet_source) > _SNIPPET_LIMIT else ""
        )
        payload = {
            "uri": resource.get("uri", ""),
            "name": resource.get("name", ""),
            "snippet": snippet,
            "description": resource.get("description", ""),
            "keywords": resource.get("keywords", []),
            "category": resource.get("category"),
        }
        scored.append((score or 1, payload))

    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [item[1] for item in scored[:limit]]


def explain_metric(metric: str = "", domain: str = "") -> dict:
    query = " ".join(part for part in [metric, domain] if part).strip()
    if not query:
        return {"error": "metric is required."}
    matches = _search_resources(query, limit=5)
    if not matches:
        return {
            "metric": metric,
            "matches": [],
            "context": "No matching resource context found for that metric.",
        }
    return {
        "metric": metric,
        "domain": domain or None,
        "matches": matches,
        "context": f"Found {len(matches)} resource matches for '{query}'.",
    }


def search_knowledge(query: str = "", top_n: int = 5) -> dict:
    matches = _search_resources(query, limit=max(1, min(top_n, 10)))
    return {
        "query": query,
        "matches": matches,
        "row_count": len(matches),
        "context": f"Found {len(matches)} knowledge matches.",
    }
