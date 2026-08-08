"""Change-history capture + rollback for tho.repcodes.

Synapse dedicated SQL pool does NOT support temporal tables or triggers, so we
journal every write from the application layer. On each INSERT/UPDATE/DELETE we
append a full row snapshot (the "after-image"; for DELETE the last-known image)
to tho.repcodes_history inside the SAME transaction as the live write — the
caller's existing conn.commit() makes the pair atomic.

Rollback = take a chosen history row and copy its column values back onto the
live row (re-inserting with IDENTITY_INSERT if the row had been deleted). The
restore is itself journaled (operation='RESTORE') so it can be audited and undone.

The editable column tuple is passed in by routes.py (the single source of truth)
to avoid duplicating the schema or creating a circular import.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Iterable, Optional, Sequence

_log = logging.getLogger(__name__)

HISTORY_TABLE = 'tho.repcodes_history'
LIVE_TABLE = 'tho.repcodes'

# Operations recorded in the `operation` column.
OP_INSERT = 'INSERT'
OP_UPDATE = 'UPDATE'
OP_DELETE = 'DELETE'
OP_RESTORE = 'RESTORE'
OP_BASELINE = 'BASELINE'

# Bit columns need to be surfaced as bools to the client (mirrors routes.py).
_BIT_COLUMNS = frozenset({'actively_used', 'for_employee_accounts'})

# Lazy CREATE TABLE — keep in sync with sql/create_repcodes_history_table.sql.
_DDL = f"""
IF NOT EXISTS (
    SELECT * FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'tho' AND TABLE_NAME = 'repcodes_history'
)
CREATE TABLE {HISTORY_TABLE} (
    [history_id]                    INT IDENTITY(1,1) NOT NULL,
    [repcode_id]                    INT             NOT NULL,
    [operation]                     NVARCHAR(10)    NOT NULL,
    [batch_id]                      NVARCHAR(36)    NULL,
    [source]                        NVARCHAR(20)    NULL,
    [custodian]                     NVARCHAR(100)   NULL,
    [actively_used]                 BIT             NULL,
    [wrap_fee_type]                 NVARCHAR(100)   NULL,
    [for_employee_accounts]         BIT             NULL,
    [fidelity_g_number]             NVARCHAR(50)    NULL,
    [g_number_usage]                NVARCHAR(255)   NULL,
    [description]                   NVARCHAR(500)   NULL,
    [notes]                         NVARCHAR(2000)  NULL,
    [schwab_master_account]         NVARCHAR(50)    NULL,
    [master_account_type]           NVARCHAR(100)   NULL,
    [allworth_advisor]              NVARCHAR(255)   NULL,
    [allworth_office]               NVARCHAR(255)   NULL,
    [separate_account_manager]      NVARCHAR(255)   NULL,
    [sma_strategy]                  NVARCHAR(255)   NULL,
    [other_third_party]             NVARCHAR(255)   NULL,
    [american_funds_rep_number]     NVARCHAR(50)    NULL,
    [american_funds_branch_number]  NVARCHAR(50)    NULL,
    [bloomwell_529_rep_code]        NVARCHAR(50)    NULL,
    [changed_by]                    NVARCHAR(320)   NULL,
    [changed_at]                    DATETIME2       NOT NULL
)
WITH (DISTRIBUTION = ROUND_ROBIN, HEAP)
"""

_META_COLS: tuple[str, ...] = ('repcode_id', 'operation', 'batch_id', 'source')
_TAIL_COLS: tuple[str, ...] = ('changed_by', 'changed_at')


def new_batch_id() -> str:
    """A short id used to group all snapshots written by one bulk operation."""
    return uuid.uuid4().hex


def ensure_history_table(cursor) -> None:
    """Create tho.repcodes_history on first use. Best-effort; logs on failure."""
    try:
        cursor.execute(_DDL)
    except Exception:  # pragma: no cover - surfaced by the caller's write
        _log.exception('repcodes.history: ensure_history_table failed')
        raise


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------
def record_snapshot(
    cursor,
    *,
    repcode_id: int,
    operation: str,
    values: dict,
    changed_by: str,
    editable_columns: Sequence[str],
    source: str = 'ui',
    batch_id: Optional[str] = None,
    changed_at: Optional[datetime] = None,
) -> None:
    """Append one history row. Uses the caller's cursor (same transaction)."""
    cols = [*_META_COLS, *editable_columns, *_TAIL_COLS]
    placeholders = ', '.join('?' for _ in cols)
    col_list = ', '.join(f'[{c}]' for c in cols)
    params: list[Any] = [
        repcode_id,
        operation,
        batch_id,
        source,
        *[values.get(c) for c in editable_columns],
        changed_by,
        changed_at or datetime.utcnow(),
    ]
    cursor.execute(
        f'INSERT INTO {HISTORY_TABLE} ({col_list}) VALUES ({placeholders})',
        params,
    )


def fetch_live_values(
    cursor, repcode_id: int, editable_columns: Sequence[str]
) -> Optional[dict]:
    """Read the current editable values of a live row, or None if it's gone."""
    col_list = ', '.join(f'[{c}]' for c in editable_columns)
    cursor.execute(
        f'SELECT {col_list} FROM {LIVE_TABLE} WHERE [repcode_id] = ?',
        (repcode_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {c: row[i] for i, c in enumerate(editable_columns)}


# ---------------------------------------------------------------------------
# Rollback path
# ---------------------------------------------------------------------------
def _live_exists(cursor, repcode_id: int) -> bool:
    cursor.execute(
        f'SELECT TOP 1 1 FROM {LIVE_TABLE} WHERE [repcode_id] = ?', (repcode_id,)
    )
    return cursor.fetchone() is not None


def apply_snapshot_values(
    cursor,
    *,
    repcode_id: int,
    values: dict,
    changed_by: str,
    editable_columns: Sequence[str],
    changed_at: Optional[datetime] = None,
) -> str:
    """Write `values` onto the live row. Returns 'updated' or 'inserted'.

    If the row still exists it is updated; if it had been deleted it is
    re-inserted with its original repcode_id (IDENTITY_INSERT) so downstream
    references stay valid.
    """
    now = changed_at or datetime.utcnow()
    if _live_exists(cursor, repcode_id):
        set_clause = ', '.join(f'[{c}] = ?' for c in editable_columns)
        set_clause += ', [modified_by] = ?, [modified_at] = ?'
        params = [values.get(c) for c in editable_columns] + [changed_by, now, repcode_id]
        cursor.execute(
            f'UPDATE {LIVE_TABLE} SET {set_clause} WHERE [repcode_id] = ?', params
        )
        return 'updated'

    cols = ['repcode_id', *editable_columns, 'modified_by', 'modified_at']
    col_list = ', '.join(f'[{c}]' for c in cols)
    placeholders = ', '.join('?' for _ in cols)
    params = [repcode_id, *[values.get(c) for c in editable_columns], changed_by, now]
    # IDENTITY_INSERT lets us restore the original id for an un-deleted row.
    cursor.execute(f'SET IDENTITY_INSERT {LIVE_TABLE} ON')
    try:
        cursor.execute(
            f'INSERT INTO {LIVE_TABLE} ({col_list}) VALUES ({placeholders})', params
        )
    finally:
        cursor.execute(f'SET IDENTITY_INSERT {LIVE_TABLE} OFF')
    return 'inserted'


def delete_live(cursor, repcode_id: int) -> int:
    """Hard-delete a live row (used when undoing an INSERT). Returns rowcount."""
    cursor.execute(f'DELETE FROM {LIVE_TABLE} WHERE [repcode_id] = ?', (repcode_id,))
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------
def _serialize(row: Any, columns: Sequence[str]) -> dict:
    out: dict = {}
    for i, col in enumerate(columns):
        val = row[i]
        if isinstance(val, datetime):
            out[col] = val.isoformat()
        elif col in _BIT_COLUMNS and val is not None:
            out[col] = bool(val)
        else:
            out[col] = val
    return out


def _select_columns(editable_columns: Sequence[str]) -> list[str]:
    return ['history_id', *_META_COLS, *editable_columns, *_TAIL_COLS]


def history_for_repcode(
    cursor, repcode_id: int, editable_columns: Sequence[str]
) -> list[dict]:
    """All history rows for one repcode_id, newest first."""
    cols = _select_columns(editable_columns)
    col_list = ', '.join(f'[{c}]' for c in cols)
    cursor.execute(
        f'SELECT {col_list} FROM {HISTORY_TABLE} '
        f'WHERE [repcode_id] = ? ORDER BY [history_id] DESC',
        (repcode_id,),
    )
    return [_serialize(r, cols) for r in cursor.fetchall()]


def recent_history(
    cursor, limit: int, editable_columns: Sequence[str]
) -> list[dict]:
    """The most recent change rows across all repcodes, newest first.

    Ordered by edit timestamp descending, with history_id as a stable tiebreaker
    for edits that share the same changed_at.
    """
    cols = _select_columns(editable_columns)
    col_list = ', '.join(f'[{c}]' for c in cols)
    cursor.execute(
        f'SELECT TOP (?) {col_list} FROM {HISTORY_TABLE} '
        f'ORDER BY [changed_at] DESC, [history_id] DESC',
        (limit,),
    )
    return [_serialize(r, cols) for r in cursor.fetchall()]


def get_history_row(
    cursor, history_id: int, editable_columns: Sequence[str]
) -> Optional[dict]:
    cols = _select_columns(editable_columns)
    col_list = ', '.join(f'[{c}]' for c in cols)
    cursor.execute(
        f'SELECT {col_list} FROM {HISTORY_TABLE} WHERE [history_id] = ?',
        (history_id,),
    )
    row = cursor.fetchone()
    return _serialize(row, cols) if row is not None else None


def prior_snapshot(
    cursor, repcode_id: int, before_history_id: int, editable_columns: Sequence[str]
) -> Optional[dict]:
    """The snapshot immediately preceding `before_history_id` for this row.

    Used to "undo" a change: revert the row to the state it had before the
    given history entry. None means the entry was the row's first appearance
    (i.e. undo = delete).
    """
    cols = _select_columns(editable_columns)
    col_list = ', '.join(f'[{c}]' for c in cols)
    cursor.execute(
        f'SELECT TOP 1 {col_list} FROM {HISTORY_TABLE} '
        f'WHERE [repcode_id] = ? AND [history_id] < ? ORDER BY [history_id] DESC',
        (repcode_id, before_history_id),
    )
    row = cursor.fetchone()
    return _serialize(row, cols) if row is not None else None


def batch_entries(
    cursor, batch_id: str, editable_columns: Sequence[str]
) -> list[dict]:
    """Every history row written under one bulk batch_id, oldest first."""
    cols = _select_columns(editable_columns)
    col_list = ', '.join(f'[{c}]' for c in cols)
    cursor.execute(
        f'SELECT {col_list} FROM {HISTORY_TABLE} '
        f'WHERE [batch_id] = ? ORDER BY [history_id] ASC',
        (batch_id,),
    )
    return [_serialize(r, cols) for r in cursor.fetchall()]
