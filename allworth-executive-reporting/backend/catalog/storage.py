"""Curated overlay writes for the catalog, with an append-only history log.

Curated fields (table description, per-column descriptions, PII flags) are
stored in ``data/overlays/<slug>.yaml`` so they survive regeneration of the
physical files. History lives at ``data/overlays/.catalog-history/events.jsonl``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from catalog.loader import overlays_dir

logger = logging.getLogger(__name__)

_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_HISTORY_DIR = ".catalog-history"
_EVENTS_FILE = "events.jsonl"
_MAX_BYTES = 500_000


def user_from_headers(headers) -> str:
    def _get(name):
        try:
            return headers.get(name)
        except AttributeError:
            return headers.get(name, "")

    azure = _get("x-ms-client-principal-name") or _get("X-Ms-Client-Principal-Name")
    if azure:
        return azure
    explicit = _get("X-User-Email") or _get("x-user-email")
    if explicit:
        return explicit
    return (
        os.environ.get("CATALOG_USER")
        or os.environ.get("JARVIS_USER")
        or os.environ.get("USERNAME")
        or os.environ.get("USER")
        or "anonymous"
    )


def _overlay_path(slug: str) -> Path:
    if not _KEY_RE.match(slug or ""):
        raise ValueError(f"invalid table id {slug!r}")
    return overlays_dir() / f"{slug}.yaml"


def _history_path() -> Path:
    p = overlays_dir() / _HISTORY_DIR / _EVENTS_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _read_overlay(slug: str) -> dict[str, Any]:
    p = _overlay_path(slug)
    if not p.exists():
        return {"id": slug}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        if isinstance(data, dict):
            data["id"] = slug
            return data
    except Exception:
        logger.exception("Catalog: bad overlay %s", slug)
    return {"id": slug}


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", delete=False, dir=path.parent, encoding="utf-8", suffix=".tmp"
    ) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def write_curation(
    slug: str,
    *,
    user: str,
    description: str | None = None,
    notes: str | None = None,
    columns: dict[str, dict[str, Any]] | None = None,
    deprecated: bool | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Merge curated fields into the overlay for one table and log the change."""
    overlay = _read_overlay(slug)
    before = yaml.safe_dump(overlay, sort_keys=False, allow_unicode=True)

    if description is not None:
        overlay["description"] = description.strip()
    if notes is not None:
        overlay["notes"] = notes.strip()
    if deprecated is not None:
        overlay["deprecated"] = bool(deprecated)
    if columns:
        col_map = overlay.get("columns") or {}
        for col_name, patch in columns.items():
            existing = col_map.get(col_name, {})
            if "description" in patch:
                existing["description"] = (patch.get("description") or "").strip()
            if "pii" in patch:
                existing["pii"] = bool(patch["pii"])
            col_map[col_name] = existing
        overlay["columns"] = col_map

    rendered = yaml.safe_dump(overlay, sort_keys=False, allow_unicode=True, width=100)
    if len(rendered.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("overlay too large")

    _atomic_write(_overlay_path(slug), rendered)
    _append_history(
        {
            "ts": _now_iso(),
            "user": user,
            "id": slug,
            "action": "curate",
            "summary": (summary or "").strip(),
            "before": before,
            "after": rendered,
        }
    )
    logger.info("Catalog curation %s by %s", slug, user)
    return overlay


# --------------------------------------------------------------------------- #
# Business-logic function overlay (editable plain-English summaries)
# --------------------------------------------------------------------------- #

_BL_OVERLAY = "business_logic.yaml"
_FN_RE = re.compile(r"^[A-Za-z_]\w{0,79}$")


def _bl_overlay_path() -> Path:
    return overlays_dir() / _BL_OVERLAY


def write_function_plain_english(
    name: str, *, user: str, plain_english: str, summary: str | None = None
) -> dict[str, Any]:
    """Persist an edited plain-English summary for a business-logic function,
    in an overlay that survives regeneration."""
    if not _FN_RE.match(name or ""):
        raise ValueError(f"invalid function name {name!r}")
    p = _bl_overlay_path()
    doc: dict[str, Any] = {}
    if p.exists():
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            doc = {}
    before = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    funcs = doc.get("functions") or {}
    funcs[name] = {"plain_english": (plain_english or "").strip()}
    doc["functions"] = funcs

    rendered = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100)
    if len(rendered.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("overlay too large")
    _atomic_write(p, rendered)
    _append_history(
        {
            "ts": _now_iso(),
            "user": user,
            "id": f"fn:{name}",
            "action": "curate-fn",
            "summary": (summary or "").strip(),
            "before": before,
            "after": rendered,
        }
    )
    logger.info("Catalog function summary %s by %s", name, user)
    return funcs[name]


def _append_history(record: dict[str, Any]) -> None:
    with open(_history_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _read_events() -> list[dict[str, Any]]:
    p = overlays_dir() / _HISTORY_DIR / _EVENTS_FILE
    if not p.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def history_for_id(slug: str, limit: int = 50) -> list[dict[str, Any]]:
    events = [e for e in _read_events() if e.get("id") == slug]
    return list(reversed(events[-limit:]))


def global_history(limit: int = 100) -> list[dict[str, Any]]:
    return list(reversed(_read_events()[-limit:]))
