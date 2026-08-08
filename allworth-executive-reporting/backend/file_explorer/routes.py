"""File Explorer routes — mounted at /api/file-explorer by app.py.

Phase 1 (Downloads):
  GET    /api/file-explorer/downloads              tables the caller may download
  GET    /api/file-explorer/download/<resource_id> stream a table as csv|txt
Sharing (admin/all-access only):
  GET    /api/file-explorer/resources              full root+table tree (share picker)
  GET    /api/file-explorer/principals             users + groups (share picker)
  GET    /api/file-explorer/shares/<resource_id>   grants on a resource
  POST   /api/file-explorer/shares                 grant a user/group
  DELETE /api/file-explorer/shares                 revoke a user/group
  GET    /api/file-explorer/health

Access model: a *resource* is a directory root (id = "<root>") or a single table
(id = "<root>/<table>"). Sharing a root cascades download access to every table
beneath it. Managers (Admin-console all-access, or the "admin" tool) see and can
share everything; everyone else sees only what has been shared with them.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

from flask import Blueprint, Response, jsonify, request

from file_explorer import adls, shares

bp = Blueprint("file_explorer", __name__)

_RESOURCES_YAML = Path(__file__).parent / "resources.yaml"
_MAX_ROWS = int(os.getenv("FILE_EXPLORER_MAX_ROWS", "2000000"))
_DISCOVERY_TTL = int(os.getenv("FILE_EXPLORER_DISCOVERY_TTL", "300"))

_ALLOWED_FORMATS = ("csv", "txt")

_roots_cache: Optional[list[dict[str, Any]]] = None
_discovery_cache: dict[str, tuple[float, list[str]]] = {}


# ── registry + discovery ─────────────────────────────────────────────────────


def _load_roots() -> list[dict[str, Any]]:
    global _roots_cache
    if _roots_cache is not None:
        return _roots_cache
    roots: list[dict[str, Any]] = []
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(_RESOURCES_YAML.read_text(encoding="utf-8")) or {}
        for entry in data.get("roots", []):
            rid = str(entry.get("id", "")).strip()
            if not rid:
                continue
            formats = [
                f for f in (entry.get("formats") or list(_ALLOWED_FORMATS))
                if f in _ALLOWED_FORMATS
            ] or list(_ALLOWED_FORMATS)
            roots.append(
                {
                    "id": rid,
                    "label": str(entry.get("label", rid)),
                    "container": str(entry.get("container", "silver")),
                    "path": str(entry.get("path", "")).strip("/"),
                    "formats": formats,
                }
            )
    except Exception:
        roots = []
    _roots_cache = roots
    return roots


def _root_by_id(root_id: str) -> Optional[dict[str, Any]]:
    return next((r for r in _load_roots() if r["id"] == root_id), None)


def _discover_tables(root: dict[str, Any]) -> list[str]:
    key = f"{root['container']}/{root['path']}"
    now = time.time()
    cached = _discovery_cache.get(key)
    if cached and (now - cached[0]) < _DISCOVERY_TTL:
        return cached[1]
    tables = adls.list_delta_tables(root["container"], root["path"])
    _discovery_cache[key] = (now, tables)
    return tables


def _abfss_path(root: dict[str, Any], table: str) -> str:
    return (
        f"abfss://{root['container']}@{adls.ADLS_ACCOUNT_NAME}"
        f".dfs.core.windows.net/{root['path']}/{table}"
    )


# ── identity + authorization ─────────────────────────────────────────────────


def _current_email() -> str:
    email = request.environ.get("user.email")
    if email:
        return email
    try:
        from admin import store as admin_store

        return admin_store.user_from_headers(request.headers)
    except Exception:
        return "anonymous"


def _can_manage(email: str) -> bool:
    """Managers can share resources and see the full tree.

    When Admin enforcement is off (the default / local dev) everyone reaching
    the tool is treated as a manager, matching the app-wide convention that an
    unenforced roster never gates. With enforcement on, only all-access users or
    holders of the ``admin`` tool may manage shares.
    """
    try:
        from admin import store as admin_store

        if not admin_store.enforcement_enabled():
            return True
        info = admin_store.effective_for(email)
        return bool(info.get("all_access")) or "admin" in set(
            info.get("effective_tools", [])
        )
    except Exception:
        return True


def _has_download_access(email: str, resource_id: str, root_id: str) -> bool:
    shared = shares.shared_resource_ids_for(email)
    # Direct table share, or a cascading directory (root) share.
    return resource_id in shared or root_id in shared


def _require_manager() -> Optional[Response]:
    if not _can_manage(_current_email()):
        return jsonify({"success": False, "error": "Not authorized to manage shares"}), 403
    return None


# ── downloads ────────────────────────────────────────────────────────────────


@bp.get("/downloads")
def list_downloads():
    """List the tables the current user may download (shares + dir cascade)."""
    email = _current_email()
    manager = _can_manage(email)
    shared = shares.shared_resource_ids_for(email)
    out: list[dict[str, Any]] = []

    for root in _load_roots():
        root_id = root["id"]
        root_shared = root_id in shared
        prefix = f"{root_id}/"
        has_child_share = any(s.startswith(prefix) for s in shared)
        if not (manager or root_shared or has_child_share):
            continue
        try:
            tables = _discover_tables(root)
        except Exception:  # pragma: no cover - network/permission dependent
            continue
        for table in tables:
            rid = f"{root_id}/{table}"
            if manager or root_shared or rid in shared:
                out.append(
                    {
                        "id": rid,
                        "label": table,
                        "root_id": root_id,
                        "root_label": root["label"],
                        "formats": root["formats"],
                    }
                )
    return jsonify({"success": True, "resources": out, "can_manage": manager})


@bp.get("/download/<path:resource_id>")
def download(resource_id: str):
    """Convert a Delta table to csv|txt and stream it as an attachment."""
    root_id, _, table = resource_id.partition("/")
    root = _root_by_id(root_id)
    if not root or not table:
        return jsonify({"success": False, "error": "Unknown resource"}), 404

    email = _current_email()
    if not _can_manage(email) and not _has_download_access(email, resource_id, root_id):
        return jsonify({"success": False, "error": "Not authorized"}), 403

    fmt = (request.args.get("format") or "csv").lower()
    if fmt not in root["formats"]:
        return jsonify({"success": False, "error": f"Unsupported format '{fmt}'"}), 400

    try:
        from delta_reader import DELTA_AVAILABLE, read_delta_table
    except Exception as e:  # pragma: no cover - defensive
        return jsonify({"success": False, "error": f"Delta reader unavailable: {e}"}), 503
    if not DELTA_AVAILABLE:
        return jsonify({"success": False, "error": "Delta reader unavailable"}), 503

    try:
        df = read_delta_table(_abfss_path(root, table), limit=_MAX_ROWS + 1)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to read table: {e}"}), 502

    if len(df) > _MAX_ROWS:
        return (
            jsonify(
                {
                    "success": False,
                    "error": (
                        f"Table exceeds the {_MAX_ROWS:,}-row download limit. "
                        "Ask for a pre-generated export."
                    ),
                }
            ),
            413,
        )

    if fmt == "txt":
        body = df.to_csv(index=False, sep="\t")
        mimetype, ext = "text/plain", "txt"
    else:
        body = df.to_csv(index=False)
        mimetype, ext = "text/csv", "csv"

    filename = f"{table.split('/')[-1]}.{ext}"
    resp = Response(body, mimetype=mimetype)
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


# ── sharing (manager only) ───────────────────────────────────────────────────


@bp.get("/resources")
def list_resources():
    """Full root + table tree for the share picker."""
    denied = _require_manager()
    if denied:
        return denied
    tree: list[dict[str, Any]] = []
    for root in _load_roots():
        node = {
            "id": root["id"],
            "label": root["label"],
            "type": "dir",
            "formats": root["formats"],
            "tables": [],
        }
        try:
            for table in _discover_tables(root):
                node["tables"].append(
                    {"id": f"{root['id']}/{table}", "label": table, "type": "table"}
                )
        except Exception as e:  # pragma: no cover - network dependent
            node["error"] = str(e)
        tree.append(node)
    return jsonify({"success": True, "resources": tree})


@bp.get("/principals")
def list_principals():
    """Users and groups available as share recipients."""
    denied = _require_manager()
    if denied:
        return denied
    users: list[str] = []
    groups: list[dict[str, str]] = []
    try:
        from admin import store as admin_store

        users = [u["email"] for u in admin_store.list_users()]
        groups = [{"id": g["id"], "name": g["name"]} for g in admin_store.list_groups()]
    except Exception:
        pass
    return jsonify({"success": True, "users": sorted(users), "groups": groups})


@bp.get("/shares/<path:resource_id>")
def get_shares(resource_id: str):
    denied = _require_manager()
    if denied:
        return denied
    return jsonify({"success": True, "shares": shares.list_shares(resource_id)})


@bp.post("/shares")
def create_share():
    denied = _require_manager()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    try:
        entry = shares.add_share(
            str(body.get("resource_id", "")),
            str(body.get("principal_type", "")),
            str(body.get("principal_id", "")),
            _current_email(),
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "share": entry}), 201


@bp.delete("/shares")
def delete_share():
    denied = _require_manager()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    try:
        removed = shares.remove_share(
            str(body.get("resource_id", "")),
            str(body.get("principal_type", "")),
            str(body.get("principal_id", "")),
        )
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, "removed": removed})


@bp.get("/health")
def health():
    return jsonify(
        {
            "success": True,
            "roots": [r["id"] for r in _load_roots()],
            "adls_available": adls.ADLS_AVAILABLE,
        }
    )
