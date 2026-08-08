"""JSON-backed persistence for File Explorer resource shares.

A *share* grants download access to a *resource* (a directory root or a single
table) to a *principal* (a user email or an Admin-console group). Directory
shares cascade to every table beneath them — that cascade is applied by the
route layer, not here; this module only stores and resolves the raw grants.

Group membership is resolved live from ``admin.store`` so removing a user from a
group immediately revokes any access that group cascaded to them. Persistence
mirrors the atomic-write + lock pattern used by ``admin/store.py``, and — like
the admin roster — the share ledger is backed up to and restored from ADLS Gen2
so a redeploy (or a PR/merge that ships a fresh container) never wipes it.
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)

_DIR = Path(__file__).parent / ".file-explorer-state"
_STATE = _DIR / "shares.json"
_lock = Lock()

PRINCIPAL_TYPES = ("user", "group")


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _empty_state() -> dict[str, Any]:
    return {"shares": []}


def _read_state() -> dict[str, Any]:
    if not _STATE.exists():
        return _empty_state()
    try:
        data = json.loads(_STATE.read_text(encoding="utf-8"))
        data.setdefault("shares", [])
        return data
    except Exception:
        return _empty_state()


def _write_state(state: dict[str, Any]) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_DIR), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _STATE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    # Push the change to ADLS off the request path so a redeploy can't lose it.
    # Suppressed until startup confirms a trusted writer (see init_persistence).
    _schedule_backup()


def _norm_principal(principal_type: str, principal_id: str) -> tuple[str, str]:
    ptype = (principal_type or "").strip().lower()
    if ptype not in PRINCIPAL_TYPES:
        raise ValueError("principal_type must be 'user' or 'group'")
    pid = (principal_id or "").strip()
    if not pid:
        raise ValueError("principal_id is required")
    if ptype == "user":
        pid = norm_email(pid)
        if "@" not in pid:
            raise ValueError("A valid user email address is required")
    return ptype, pid


# ── public API ───────────────────────────────────────────────────────────────


def all_shares() -> list[dict[str, Any]]:
    with _lock:
        return list(_read_state()["shares"])


def list_shares(resource_id: str) -> list[dict[str, Any]]:
    """All share grants for a single resource."""
    with _lock:
        return [
            s for s in _read_state()["shares"] if s.get("resource_id") == resource_id
        ]


def add_share(
    resource_id: str, principal_type: str, principal_id: str, actor: str
) -> dict[str, Any]:
    if not (resource_id or "").strip():
        raise ValueError("resource_id is required")
    ptype, pid = _norm_principal(principal_type, principal_id)
    with _lock:
        state = _read_state()
        for s in state["shares"]:
            if (
                s.get("resource_id") == resource_id
                and s.get("principal_type") == ptype
                and s.get("principal_id") == pid
            ):
                return s  # already shared — idempotent
        entry = {
            "resource_id": resource_id,
            "principal_type": ptype,
            "principal_id": pid,
            "created_at": _now_iso(),
            "created_by": norm_email(actor) or actor,
        }
        state["shares"].append(entry)
        _write_state(state)
        return entry


def remove_share(resource_id: str, principal_type: str, principal_id: str) -> bool:
    ptype, pid = _norm_principal(principal_type, principal_id)
    with _lock:
        state = _read_state()
        before = len(state["shares"])
        state["shares"] = [
            s
            for s in state["shares"]
            if not (
                s.get("resource_id") == resource_id
                and s.get("principal_type") == ptype
                and s.get("principal_id") == pid
            )
        ]
        removed = len(state["shares"]) < before
        if removed:
            _write_state(state)
        return removed


def _user_group_ids(email: str) -> set[str]:
    """Ids of the Admin-console groups the user belongs to (live membership)."""
    email = norm_email(email)
    if not email:
        return set()
    try:
        from admin import store as admin_store
    except Exception:
        return set()
    gids: set[str] = set()
    try:
        for g in admin_store.list_groups():
            members = {norm_email(m) for m in g.get("members", [])}
            if g.get("all_members") or email in members:
                gids.add(g["id"])
    except Exception:
        return set()
    return gids


def shared_resource_ids_for(email: str) -> set[str]:
    """Resource ids shared to the user directly or via any of their groups.

    Directory-cascade is NOT applied here — the caller expands directory roots
    to their child tables.
    """
    email = norm_email(email)
    gids = _user_group_ids(email)
    out: set[str] = set()
    for s in all_shares():
        rid = s.get("resource_id")
        if not rid:
            continue
        ptype = s.get("principal_type")
        pid = s.get("principal_id")
        if ptype == "user" and norm_email(pid) == email:
            out.add(rid)
        elif ptype == "group" and pid in gids:
            out.add(rid)
    return out


# ── data-lake durability (backup + restore) ──────────────────────────────────
#
# The share ledger lives on the container's local disk for fast, request-path
# reads/writes. Durability across restarts/redeploys mirrors ``admin/store.py``:
#   * restore-on-startup: if the local file is missing, download the latest
#     backup from ADLS Gen2 before serving.
#   * an immediate best-effort upload after every change (off the request path),
#     a low-frequency background backup, and a final upload on process exit.
# No ADLS I/O ever happens while handling a request.

_backup_started = False
_backup_safe = True
# Immediate per-write uploads stay OFF until startup confirms a trusted writer
# that restored (or found no) remote ledger, so an empty bootstrap state can
# never overwrite a populated shared ledger.
_immediate_backup_enabled = False


def _adls_target() -> tuple[str, str, str]:
    account = os.getenv("FILE_EXPLORER_STATE_ADLS_ACCOUNT") or os.getenv(
        "ADLS_ACCOUNT_NAME", "dlallworthai"
    )
    container = os.getenv("FILE_EXPLORER_STATE_ADLS_CONTAINER") or os.getenv(
        "ADLS_SILVER_CONTAINER", "silver"
    )
    path = os.getenv("FILE_EXPLORER_STATE_ADLS_PATH", "file-explorer/shares.json")
    return account, container, path


def _adls_credential():
    """Match delta_reader/admin auth precedence: account key → SP → MSI → CLI."""
    key = os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or os.getenv("ADLS_ACCOUNT_KEY")
    if key:
        return key
    try:
        from azure.identity import (
            AzureCliCredential,
            ClientSecretCredential,
            ManagedIdentityCredential,
        )
    except Exception:
        return None
    cid, cs, tid = (
        os.getenv("AZURE_CLIENT_ID"),
        os.getenv("AZURE_CLIENT_SECRET"),
        os.getenv("AZURE_TENANT_ID"),
    )
    if cid and cs and tid:
        return ClientSecretCredential(tid, cid, cs)
    if os.getenv("AZURE_USE_MANAGED_IDENTITY", "").lower() in ("1", "true", "yes"):
        msi = os.getenv("AZURE_MSI_CLIENT_ID")
        return ManagedIdentityCredential(client_id=msi) if msi else ManagedIdentityCredential()
    try:
        return AzureCliCredential()
    except Exception:
        return None


def _adls_file_client():
    """A DataLakeFileClient for the shares backup, or None if unavailable."""
    try:
        from azure.storage.filedatalake import DataLakeServiceClient
    except Exception:
        return None
    cred = _adls_credential()
    if cred is None:
        return None
    account, container, path = _adls_target()
    try:
        svc = DataLakeServiceClient(
            account_url=f"https://{account}.dfs.core.windows.net", credential=cred
        )
        return svc.get_file_system_client(container).get_file_client(path)
    except Exception as e:
        logger.warning("file-explorer backup: could not build ADLS client: %s", e)
        return None


def backup_enabled() -> bool:
    flag = os.getenv("FILE_EXPLORER_BACKUP_ENABLED")
    if flag is not None:
        return flag.strip().lower() in ("1", "true", "yes", "on")
    # Auto-enable only when explicit deploy credentials are present. Azure-CLI-
    # only local dev stays OFF to avoid noisy failed uploads.
    if os.getenv("AZURE_STORAGE_ACCOUNT_KEY") or os.getenv("ADLS_ACCOUNT_KEY"):
        return True
    if all(os.getenv(k) for k in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID")):
        return True
    if os.getenv("AZURE_USE_MANAGED_IDENTITY", "").lower() in ("1", "true", "yes"):
        return True
    return False


def _is_not_found(e: Exception) -> bool:
    """True when an ADLS error means the backup simply doesn't exist yet."""
    try:
        from azure.core.exceptions import ResourceNotFoundError

        if isinstance(e, ResourceNotFoundError):
            return True
    except Exception:
        pass
    if getattr(e, "status_code", None) == 404:
        return True
    name = type(e).__name__
    return "ResourceNotFound" in name or "PathNotFound" in name


def restore_from_lake_if_empty() -> str:
    """Seed the local ledger from ADLS when it's missing.

    Returns ``"restored"`` (local file present), ``"empty"`` (no remote backup /
    ADLS not configured — safe to start fresh) or ``"failed"`` (a backup likely
    exists but couldn't be read, so uploads must be disabled to protect it).
    """
    if _STATE.exists():
        return "restored"
    fc = _adls_file_client()
    if fc is None:
        return "empty"
    try:
        data = fc.download_file().readall()
    except Exception as e:
        if _is_not_found(e):
            logger.info("file-explorer backup: no remote ledger yet — starting fresh")
            return "empty"
        logger.warning(
            "file-explorer backup: restore failed (%s) — uploads disabled to "
            "protect the remote ledger",
            type(e).__name__,
        )
        return "failed"
    try:
        json.loads(data)  # validate before trusting it
    except Exception:
        logger.warning("file-explorer backup: remote ledger is unreadable/corrupt")
        return "failed"
    _DIR.mkdir(parents=True, exist_ok=True)
    _STATE.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    logger.info("file-explorer backup: restored share ledger from ADLS")
    return "restored"


def backup_to_lake(force: bool = False) -> bool:
    """Upload the local ledger to ADLS. No-op unless it exists and is safe."""
    if not _backup_safe:
        return False
    with _lock:
        if not _STATE.exists():
            return False
        data = _STATE.read_bytes()
    fc = _adls_file_client()
    if fc is None:
        return False
    try:
        fc.upload_data(data, overwrite=True)
        logger.info("file-explorer backup: uploaded share ledger to ADLS")
        return True
    except Exception as e:
        logger.warning("file-explorer backup: upload failed: %s", type(e).__name__)
        return False


def _schedule_backup() -> None:
    """Fire a best-effort ADLS upload off the request path after a change."""
    if not _immediate_backup_enabled or not _backup_safe:
        return
    try:
        threading.Thread(
            target=backup_to_lake,
            kwargs={"force": True},
            daemon=True,
            name="file-explorer-lake-backup-now",
        ).start()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("file-explorer backup: could not schedule upload: %s", e)


def _backup_loop(interval_seconds: float) -> None:
    while True:
        time.sleep(interval_seconds)
        try:
            backup_to_lake()
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("file-explorer backup: loop error: %s", e)


def init_persistence() -> None:
    """Startup hook: restore-if-empty → enable durable backups.

    Call once at app startup. Until this runs, per-write uploads are suppressed
    so an empty bootstrap ledger can never overwrite a populated shared one.
    """
    global _backup_started, _backup_safe, _immediate_backup_enabled

    try:
        status = restore_from_lake_if_empty()
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("file-explorer backup: restore failed: %s", e)
        status = "failed"

    if status == "failed":
        # A remote ledger likely exists but couldn't be read. Serve locally but
        # disable uploads so a transient error can't overwrite the saved shares.
        _backup_safe = False
        logger.error(
            "file-explorer backup: could not restore the share ledger — uploads "
            "DISABLED for this process. Check ADLS access, then restart."
        )
        return

    if not backup_enabled():
        logger.info(
            "file-explorer backup: disabled (no ADLS credentials or "
            "FILE_EXPLORER_BACKUP_ENABLED=0)"
        )
        return

    # Capture the current ledger immediately, then keep it durable.
    backup_to_lake(force=True)

    if not _backup_started:
        try:
            hours = float(os.getenv("FILE_EXPLORER_BACKUP_INTERVAL_HOURS", "24"))
        except ValueError:
            hours = 24.0
        interval = max(60.0, hours * 3600.0)
        threading.Thread(
            target=_backup_loop, args=(interval,), daemon=True, name="file-explorer-lake-backup"
        ).start()
        atexit.register(lambda: backup_to_lake(force=True))
        _backup_started = True
        logger.info("file-explorer backup: daily backup thread started (every %.1fh)", hours)

    # Trusted writer: every future add/remove now persists to ADLS immediately.
    _immediate_backup_enabled = True
