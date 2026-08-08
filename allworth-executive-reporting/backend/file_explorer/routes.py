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

import csv
import io
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from flask import Blueprint, Response, jsonify, request

from file_explorer import adls, shares

bp = Blueprint("file_explorer", __name__)

_RESOURCES_YAML = Path(__file__).parent / "resources.yaml"
_MAX_ROWS = int(os.getenv("FILE_EXPLORER_MAX_ROWS", "5000000"))
_DISCOVERY_TTL = int(os.getenv("FILE_EXPLORER_DISCOVERY_TTL", "300"))

_ALLOWED_FORMATS = ("csv", "txt")
_MAX_UPLOAD_BYTES = int(os.getenv("FILE_EXPLORER_MAX_UPLOAD_BYTES", str(200 * 1024 * 1024)))

_roots_cache: Optional[list[dict[str, Any]]] = None
_uploads_cache: Optional[list[dict[str, Any]]] = None
_discovery_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


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


def _load_uploads() -> list[dict[str, Any]]:
    """Upload targets from the registry (id, label, container, path, columns…)."""
    global _uploads_cache
    if _uploads_cache is not None:
        return _uploads_cache
    uploads: list[dict[str, Any]] = []
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(_RESOURCES_YAML.read_text(encoding="utf-8")) or {}
        for entry in data.get("uploads", []):
            uid = str(entry.get("id", "")).strip()
            columns: list[list[str]] = []
            for c in entry.get("columns") or []:
                alts = (
                    [str(x).strip() for x in c if str(x).strip()]
                    if isinstance(c, (list, tuple))
                    else [str(c).strip()]
                )
                if alts:
                    columns.append(alts)
            if not uid or not columns:
                continue
            header_rows = [
                int(r) for r in (entry.get("header_rows") or [1]) if int(r) >= 1
            ] or [1]
            uploads.append(
                {
                    "id": uid,
                    "label": str(entry.get("label", uid)),
                    "container": str(entry.get("container", "bronze")),
                    "path": str(entry.get("path", "")).strip("/"),
                    "format": str(entry.get("format", "csv")).lower(),
                    "header_rows": header_rows,
                    "columns": columns,
                }
            )
    except Exception:
        uploads = []
    _uploads_cache = uploads
    return uploads


def _upload_by_id(upload_id: str) -> Optional[dict[str, Any]]:
    return next((u for u in _load_uploads() if u["id"] == upload_id), None)


def _discover_tables(root: dict[str, Any]) -> list[dict[str, Any]]:
    """Discovered tables under a root as ``{"name", "last_modified"}`` dicts.

    The list and each table's last-modified timestamp are cached together for
    ``_DISCOVERY_TTL`` seconds so date lookups never hit ADLS on a request path.
    """
    key = f"{root['container']}/{root['path']}"
    now = time.time()
    cached = _discovery_cache.get(key)
    if cached and (now - cached[0]) < _DISCOVERY_TTL:
        return cached[1]
    tables = [
        {
            "name": name,
            "last_modified": adls.table_last_modified(
                root["container"], root["path"], name
            ),
        }
        for name in adls.list_delta_tables(root["container"], root["path"])
    ]
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
        for meta in tables:
            table = meta["name"]
            rid = f"{root_id}/{table}"
            if manager or root_shared or rid in shared:
                out.append(
                    {
                        "id": rid,
                        "label": table,
                        "root_id": root_id,
                        "root_label": root["label"],
                        "formats": root["formats"],
                        "last_modified": meta.get("last_modified"),
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
            for meta in _discover_tables(root):
                node["tables"].append(
                    {
                        "id": f"{root['id']}/{meta['name']}",
                        "label": meta["name"],
                        "type": "table",
                        "last_modified": meta.get("last_modified"),
                    }
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


# ── uploads (manager only) ───────────────────────────────────────────────────


def _decode_csv(data: bytes) -> str:
    """Decode uploaded CSV bytes, tolerating a UTF-8 BOM then falling back to
    latin-1 so an odd byte never crashes header validation."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _column_display(accepted: list[str]) -> str:
    """Human-readable form of a column's accepted spellings for the UI."""
    if len(accepted) <= 1:
        return accepted[0] if accepted else ""
    return f"{accepted[0]} (or {', '.join(accepted[1:])})"


def _validate_header(
    data: bytes, expected: list[list[str]], header_rows: list[int]
) -> tuple[bool, Optional[int], Optional[str]]:
    """Confirm the CSV header matches ``expected`` on one of ``header_rows``.

    ``expected`` is an ordered list of columns, each a list of accepted spellings
    (the first is canonical). A single-column row 1 (a title/banner) is skipped
    so the real header on a later row (e.g. row 3) is used. Returns
    ``(ok, header_row_1based, error)``; on failure ``error`` names the offending
    column or the wrong column count so the user can fix the file.
    """
    text = _decode_csv(data)
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return False, None, "The file is empty."

    candidates: list[tuple[int, list[str]]] = []
    for r in header_rows:
        idx = r - 1
        if 0 <= idx < len(rows):
            candidates.append((r, [c.strip() for c in rows[idx]]))
    # If row 1 is a single column (a title/banner) and there's another header
    # row to try, skip row 1 and look further down (e.g. row 3).
    if len(candidates) > 1:
        candidates = [
            (rn, cells) for rn, cells in candidates if not (rn == 1 and len(cells) <= 1)
        ] or candidates
    if not candidates:
        return False, None, "The file has no header row to check."

    def _matches(cells: list[str]) -> bool:
        return len(cells) == len(expected) and all(
            found in accepted for found, accepted in zip(cells, expected)
        )

    # Exact match on any allowed header row wins.
    for rownum, cells in candidates:
        if _matches(cells):
            return True, rownum, None

    # Report against the most likely header row: prefer one with the right
    # number of columns, else the first candidate.
    rownum, cells = next(
        ((rn, c) for rn, c in candidates if len(c) == len(expected)), candidates[0]
    )
    where = f"row {rownum}"
    if len(cells) != len(expected):
        wanted = ", ".join(_column_display(c) for c in expected)
        return False, None, (
            f"Expected {len(expected)} columns but found {len(cells)} in the "
            f"header ({where}). The columns must be, in order: {wanted}."
        )
    for i, (found, accepted) in enumerate(zip(cells, expected), start=1):
        if found not in accepted:
            return False, None, (
                f'Column {i} in the header ({where}) should be '
                f'"{_column_display(accepted)}" but the file has "{found}".'
            )
    return True, rownum, None


def _safe_filename(name: str) -> str:
    """A filesystem/ADLS-safe basename derived from the uploaded filename."""
    base = os.path.basename(name or "").strip() or "upload.csv"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", base)


@bp.get("/uploads")
def list_uploads():
    """Upload targets the caller may push files into (manager-gated)."""
    manager = _can_manage(_current_email())
    targets = (
        [
            {
                "id": u["id"],
                "label": u["label"],
                "format": u["format"],
                "columns": [_column_display(c) for c in u["columns"]],
            }
            for u in _load_uploads()
        ]
        if manager
        else []
    )
    return jsonify({"success": True, "uploads": targets, "can_manage": manager})


@bp.post("/upload/<target_id>")
def upload(target_id: str):
    """Validate an uploaded file against a target's schema, then store it."""
    denied = _require_manager()
    if denied:
        return denied

    target = _upload_by_id(target_id)
    if not target:
        return jsonify({"success": False, "error": "Unknown upload target"}), 404

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "No file was provided"}), 400

    if not file.filename.lower().endswith(".csv"):
        return (
            jsonify({"success": False, "error": "Please upload a .csv file"}),
            400,
        )

    data = file.read()
    if not data:
        return jsonify({"success": False, "error": "The file is empty"}), 400
    if len(data) > _MAX_UPLOAD_BYTES:
        return (
            jsonify(
                {
                    "success": False,
                    "error": f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit",
                }
            ),
            413,
        )

    ok, _header_row, err = _validate_header(
        data, target["columns"], target["header_rows"]
    )
    if not ok:
        return jsonify({"success": False, "error": err}), 422

    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    stored_name = f"{ts}_{_safe_filename(file.filename)}"
    try:
        stored = adls.upload_bytes(
            target["container"], target["path"], stored_name, data
        )
    except Exception as e:
        return (
            jsonify({"success": False, "error": f"Upload failed: {e}"}),
            502,
        )

    return jsonify(
        {"success": True, "stored": stored, "filename": stored_name}
    )


@bp.get("/health")
def health():
    return jsonify(
        {
            "success": True,
            "roots": [r["id"] for r in _load_roots()],
            "adls_available": adls.ADLS_AVAILABLE,
        }
    )
