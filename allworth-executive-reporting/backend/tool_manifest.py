"""Validated access to the workspace's canonical tool manifest."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "tool-manifest.json"
VALID_STATUSES = {"live", "new", "soon"}


@lru_cache(maxsize=1)
def load_tool_manifest() -> dict[str, Any]:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Unable to load tool manifest at {MANIFEST_PATH}") from exc

    tools = payload.get("tools")
    if not isinstance(tools, list) or not tools:
        raise RuntimeError("The tool manifest does not contain any tools")

    seen: set[str] = set()
    for entry in tools:
        if not isinstance(entry, dict):
            raise RuntimeError(f"Invalid tool manifest entry: {entry!r}")
        tool_id = str(entry.get("id", "")).strip()
        status = str(entry.get("status", "")).strip()
        if not tool_id or tool_id in seen or status not in VALID_STATUSES:
            raise RuntimeError(f"Invalid tool manifest entry: {entry!r}")
        seen.add(tool_id)
    return payload


def manifest_tools() -> tuple[dict[str, Any], ...]:
    return tuple(load_tool_manifest()["tools"])


def analytics_routes() -> tuple[tuple[str, str, str], ...]:
    """Return longest-prefix-first usage routes derived from the manifest."""
    routes: list[tuple[str, str, str]] = []
    for tool in manifest_tools():
        if tool["status"] == "soon":
            continue
        paths = tool.get("analytics_urls") or ([tool["url"]] if tool.get("url") else [])
        routes.extend((path, tool["id"], tool["name"]) for path in paths if path)
    routes.extend((("/home", "home", "Home"), ("/", "home", "Home")))
    return tuple(sorted(routes, key=lambda item: len(item[0]), reverse=True))
