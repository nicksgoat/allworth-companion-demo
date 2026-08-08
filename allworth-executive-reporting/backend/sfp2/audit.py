"""Audit log writer for SFP2 schema changes.

Appends one row per add/drop attempt (success or failure) to a Delta table at
`silver/logging/sfp2_schema_changes`. The table is created lazily on first
write. Audit failures must NEVER raise — they are logged and swallowed so an
audit-table outage cannot roll back a successful schema change.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import pyarrow as pa  # type: ignore
    PYARROW_AVAILABLE = True
except Exception:  # pragma: no cover
    pa = None  # type: ignore
    PYARROW_AVAILABLE = False

try:
    from deltalake import write_deltalake  # type: ignore
    DELTA_WRITE_AVAILABLE = True
except Exception:  # pragma: no cover
    write_deltalake = None  # type: ignore
    DELTA_WRITE_AVAILABLE = False

try:
    from delta_reader import _build_storage_options  # type: ignore
except Exception:  # pragma: no cover
    def _build_storage_options() -> dict[str, str]:  # type: ignore
        return {}


_log = logging.getLogger(__name__)

# Action values written to the audit Delta table. Drops are now deferred:
#   - 'drop_queued'   : user requested a drop; column NOT yet removed.
#   - 'drop'          : the overnight worker (or a future inline path) attempted
#                       the actual ALTER. `success` field tells you whether it
#                       worked.
#   - 'drop_canceled' : a queued drop was canceled before the worker ran.
ACTION_ADD = 'add'
ACTION_ADD_QUEUED = 'add_queued'
ACTION_ADD_CANCELED = 'add_canceled'
ACTION_DROP = 'drop'
ACTION_DROP_QUEUED = 'drop_queued'
ACTION_DROP_CANCELED = 'drop_canceled'

ADLS_ACCOUNT_NAME = os.getenv('ADLS_ACCOUNT_NAME', 'dlallworthai')
ADLS_SILVER_CONTAINER = os.getenv('ADLS_SILVER_CONTAINER', 'silver')
AUDIT_RELATIVE_PATH = os.getenv(
    'SFP2_AUDIT_PATH', 'logging/sfp2_schema_changes'
).strip('/')

AUDIT_PATH = (
    f"abfss://{ADLS_SILVER_CONTAINER}@{ADLS_ACCOUNT_NAME}"
    f".dfs.core.windows.net/{AUDIT_RELATIVE_PATH}"
)

APP_VERSION = os.getenv('APP_VERSION') or os.getenv('GITHUB_SHA') or 'unknown'


def _build_schema():
    return pa.schema([
        pa.field('ts', pa.timestamp('us', tz='UTC'), nullable=False),
        pa.field('action', pa.string(), nullable=False),
        pa.field('table', pa.string(), nullable=False),
        pa.field('column', pa.string(), nullable=False),
        pa.field('sf_type', pa.string(), nullable=True),
        pa.field('delta_type', pa.string(), nullable=True),
        pa.field('user_email', pa.string(), nullable=True),
        pa.field('success', pa.bool_(), nullable=False),
        pa.field('error', pa.string(), nullable=True),
        pa.field('request_id', pa.string(), nullable=True),
        pa.field('app_version', pa.string(), nullable=True),
    ])


def record_change(
    action: str,
    table: str,
    column: str,
    user_email: Optional[str],
    success: bool,
    sf_type: Optional[str] = None,
    delta_type: Optional[str] = None,
    error: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """Best-effort append to the audit Delta table. Never raises."""
    if not (PYARROW_AVAILABLE and DELTA_WRITE_AVAILABLE):
        _log.warning(
            "sfp2 audit skipped (pyarrow/deltalake unavailable): "
            "action=%s table=%s column=%s success=%s",
            action, table, column, success,
        )
        return

    try:
        schema = _build_schema()
        row = {
            'ts': [datetime.now(timezone.utc)],
            'action': [action],
            'table': [table],
            'column': [column],
            'sf_type': [sf_type],
            'delta_type': [delta_type],
            'user_email': [user_email],
            'success': [bool(success)],
            'error': [error],
            'request_id': [request_id],
            'app_version': [APP_VERSION],
        }
        tbl = pa.table(row, schema=schema)
        write_deltalake(
            AUDIT_PATH,
            tbl,
            mode='append',
            schema_mode='merge',
            storage_options=_build_storage_options(),
        )
    except Exception as e:  # pragma: no cover - best-effort
        _log.exception(
            "sfp2 audit write failed: action=%s table=%s column=%s err=%s",
            action, table, column, e,
        )


# ---------------------------------------------------------------------------
# Read helpers (used by GET /sfp2/schema-changes and the overnight worker)
# ---------------------------------------------------------------------------
try:
    from deltalake import DeltaTable  # type: ignore
    DELTA_READ_AVAILABLE = True
except Exception:  # pragma: no cover
    DeltaTable = None  # type: ignore
    DELTA_READ_AVAILABLE = False


# Terminal actions that close out a pending drop. A row is "pending" iff its
# latest-by-ts row is `drop_queued` and there's no later row with a terminal
# action for the same (table, column).
_TERMINAL_DROP_ACTIONS = frozenset({ACTION_DROP, ACTION_DROP_CANCELED})
_TERMINAL_ADD_ACTIONS = frozenset({ACTION_ADD, ACTION_ADD_CANCELED})


def read_recent(
    table_filter: Optional[str] = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent audit rows, newest first, with a derived per-row state.

    `state` is one of:
      - 'pending'    : `drop_queued` row with no later terminal row.
      - 'add_pending': `add_queued` row with no later terminal row.
      - 'done'       : `drop` row with success=True.
      - 'failed'     : `drop` row with success=False.
      - 'canceled'   : `drop_canceled` row.
      - 'added'      : `add` row with success=True.
      - 'add_failed' : `add` row with success=False.
      - 'add_canceled': `add_canceled` row.
      - 'superseded' : older queued row that was followed by a terminal row.
    """
    if not DELTA_READ_AVAILABLE:
        return []
    try:
        dt = DeltaTable(AUDIT_PATH, storage_options=_build_storage_options())
    except Exception as e:  # table doesn't exist yet
        _log.info("sfp2 audit table not readable yet: %s", e)
        return []

    try:
        arrow = dt.to_pyarrow_table()
    except Exception:  # pragma: no cover
        _log.exception("sfp2 audit read failed")
        return []

    rows: list[dict[str, Any]] = arrow.to_pylist()

    if table_filter:
        tf = table_filter.lower()
        rows = [r for r in rows if (r.get('table') or '').lower() == tf]

    # Sort newest first. `ts` may be a datetime or None.
    rows.sort(key=lambda r: r.get('ts') or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    # Track per (table, column) whether a newer terminal row exists, separately
    # for adds and drops (they're independent operations).
    seen_drop_terminal: set[tuple[str, str]] = set()
    seen_add_terminal: set[tuple[str, str]] = set()
    for r in rows:  # newest first
        key = ((r.get('table') or '').lower(), (r.get('column') or '').lower())
        action = r.get('action') or ''
        success = bool(r.get('success'))
        if action == ACTION_DROP_QUEUED:
            r['state'] = 'superseded' if key in seen_drop_terminal else 'pending'
        elif action == ACTION_DROP:
            r['state'] = 'done' if success else 'failed'
            seen_drop_terminal.add(key)
        elif action == ACTION_DROP_CANCELED:
            r['state'] = 'canceled'
            seen_drop_terminal.add(key)
        elif action == ACTION_ADD_QUEUED:
            r['state'] = 'superseded' if key in seen_add_terminal else 'add_pending'
        elif action == ACTION_ADD:
            r['state'] = 'added' if success else 'add_failed'
            seen_add_terminal.add(key)
        elif action == ACTION_ADD_CANCELED:
            r['state'] = 'add_canceled'
            seen_add_terminal.add(key)
        else:
            r['state'] = action  # forward-compat for unknown actions

        # Make timestamps JSON-serializable.
        ts = r.get('ts')
        if hasattr(ts, 'isoformat'):
            r['ts'] = ts.isoformat()

    if limit and len(rows) > limit:
        rows = rows[:limit]
    return rows


def has_pending_drop(table: str, column: str) -> bool:
    """True if (table, column) already has an open drop request."""
    table_l = (table or '').lower()
    col_l = (column or '').lower()
    for r in read_recent(table_filter=table, limit=1000):
        if (r.get('column') or '').lower() != col_l:
            continue
        if (r.get('table') or '').lower() != table_l:
            continue
        # read_recent yields newest first; the first matching drop-row decides.
        if r.get('action') in (ACTION_DROP_QUEUED, ACTION_DROP, ACTION_DROP_CANCELED):
            return r.get('state') == 'pending'
    return False


def has_pending_add(table: str, column: str) -> bool:
    """True if (table, column) already has an open add request."""
    table_l = (table or '').lower()
    col_l = (column or '').lower()
    for r in read_recent(table_filter=table, limit=1000):
        if (r.get('column') or '').lower() != col_l:
            continue
        if (r.get('table') or '').lower() != table_l:
            continue
        if r.get('action') in (ACTION_ADD_QUEUED, ACTION_ADD, ACTION_ADD_CANCELED):
            return r.get('state') == 'add_pending'
    return False

