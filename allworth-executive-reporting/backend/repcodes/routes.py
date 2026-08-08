"""Flask blueprint for the editable Rep Codes table.

Endpoints (mounted at /api/repcodes by app.py):
    GET    /                  - list all rows
    POST   /                  - insert a new row, returns the new repcode_id
    PUT    /<int:repcode_id>  - update a row (full replace of editable fields)
    DELETE /<int:repcode_id>  - delete a row

Auth: relies on the global JWT middleware in auth_middleware.py. The user
email (from the validated token) is read from request.environ['user.email']
and stamped into modified_by/modified_at on every write.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from . import history

bp = Blueprint('repcodes', __name__)

# Editable columns in display order. Keep in sync with create_repcodes_table.sql.
EDITABLE_COLUMNS: tuple[str, ...] = (
    'custodian',
    'actively_used',
    'wrap_fee_type',
    'for_employee_accounts',
    'fidelity_g_number',
    'g_number_usage',
    'description',
    'notes',
    'schwab_master_account',
    'master_account_type',
    'allworth_advisor',
    'allworth_office',
    'separate_account_manager',
    'sma_strategy',
    'other_third_party',
    'american_funds_rep_number',
    'american_funds_branch_number',
    'bloomwell_529_rep_code',
)

BIT_COLUMNS: frozenset[str] = frozenset({'actively_used', 'for_employee_accounts'})


def _err(msg: str, status: int = 500) -> Any:
    return jsonify({'success': False, 'error': msg}), status


def _user_email() -> str:
    """Return the validated email from the JWT, or 'unknown' if auth disabled."""
    email = request.environ.get('user.email')
    if email:
        return str(email)
    return 'unknown'


def _get_conn():
    """Lazy import to avoid circular dependency with app.py."""
    from app import get_database_connection  # type: ignore
    return get_database_connection()


def _ensure_history(conn) -> None:
    """Best-effort lazy create of tho.repcodes_history (own committed step).

    Mirrors app._ensure_analytics_table. Kept out of the data transaction so
    DDL never tangles with the live write. If this fails, the snapshot INSERT
    later in the same write transaction will fail loudly and roll the write
    back — by design, an edit to an audited table should not silently lose its
    history.
    """
    try:
        cur = conn.cursor()
        history.ensure_history_table(cur)
        cur.commit()
        cur.close()
    except Exception:  # pragma: no cover - surfaced on the snapshot write
        current_app.logger.exception('repcodes: ensure history table failed')


def _coerce_value(col: str, raw: Any) -> Any:
    """Validate + coerce a single inbound JSON value to a SQL parameter."""
    if raw is None or raw == '':
        return None
    if col in BIT_COLUMNS:
        if isinstance(raw, bool):
            return 1 if raw else 0
        if isinstance(raw, int):
            return 1 if raw else 0
        if isinstance(raw, str):
            v = raw.strip().lower()
            if v in ('1', 'true', 't', 'yes', 'y'):
                return 1
            if v in ('0', 'false', 'f', 'no', 'n'):
                return 0
            raise ValueError(f'Invalid boolean for {col}: {raw!r}')
        raise ValueError(f'Invalid boolean for {col}: {raw!r}')
    # All other columns are NVARCHAR; coerce to str and strip
    return str(raw).strip() or None


def _row_from_payload(payload: dict) -> dict:
    """Coerce + validate a JSON payload into {col: value} for SQL params."""
    if not isinstance(payload, dict):
        raise ValueError('Request body must be a JSON object')
    coerced: dict = {}
    for col in EDITABLE_COLUMNS:
        if col in payload:
            coerced[col] = _coerce_value(col, payload[col])
        else:
            coerced[col] = None
    return coerced


def _serialize_row(row: Any, columns: list[str]) -> dict:
    """Convert a pyodbc row to a plain dict (BIT -> bool, datetimes -> isoformat)."""
    out: dict = {}
    for i, col in enumerate(columns):
        val = row[i]
        if isinstance(val, datetime):
            out[col] = val.isoformat()
        elif col in BIT_COLUMNS and val is not None:
            out[col] = bool(val)
        else:
            out[col] = val
    return out


SELECT_COLS = ['repcode_id', *EDITABLE_COLUMNS, 'modified_by', 'modified_at']
SELECT_LIST = ', '.join(f'[{c}]' for c in SELECT_COLS)


@bp.route('/', methods=['GET'])
def list_rows() -> Any:
    """Return every row in tho.repcodes ordered by repcode_id."""
    try:
        conn = _get_conn()
        cursor = conn.cursor()
        cursor.execute(
            f'SELECT {SELECT_LIST} FROM tho.repcodes ORDER BY repcode_id'
        )
        rows = [_serialize_row(r, SELECT_COLS) for r in cursor.fetchall()]
        cursor.close()
        return jsonify({
            'success': True,
            'columns': SELECT_COLS,
            'editable_columns': list(EDITABLE_COLUMNS),
            'bit_columns': sorted(BIT_COLUMNS),
            'rows': rows,
        })
    except Exception as e:  # pragma: no cover - surface to client
        current_app.logger.exception('repcodes.list_rows failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/', methods=['POST'])
def create_row() -> Any:
    """Insert a single new row. Returns the generated repcode_id."""
    try:
        coerced = _row_from_payload(request.get_json(silent=True) or {})
    except ValueError as e:
        return _err(str(e), 400)

    cols = [*EDITABLE_COLUMNS, 'modified_by', 'modified_at']
    placeholders = ', '.join('?' for _ in cols)
    col_list = ', '.join(f'[{c}]' for c in cols)
    user_email = _user_email()
    now = datetime.utcnow()
    params: list = [coerced[c] for c in EDITABLE_COLUMNS]
    params.append(user_email)
    params.append(now)

    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        # Synapse dedicated SQL pool does NOT support OUTPUT INSERTED, @@IDENTITY
        # or SCOPE_IDENTITY() (the latter raises "SCOPE_IDENTITY is not a
        # recognized built-in function name"). The supported way to read back the
        # generated IDENTITY value is MAX([repcode_id]); writes on this pooled
        # connection are serialized within the request so this is safe here.
        cursor.execute(
            f'INSERT INTO tho.repcodes ({col_list}) VALUES ({placeholders})',
            params,
        )
        # Capture the new id BEFORE the history INSERT (which inserts into a
        # different table but keep the read tight to the insert above).
        cursor.execute('SELECT CAST(MAX([repcode_id]) AS INT) FROM tho.repcodes')
        new_id_row = cursor.fetchone()
        new_id = int(new_id_row[0]) if new_id_row and new_id_row[0] is not None else None
        if new_id is not None:
            history.record_snapshot(
                cursor, repcode_id=new_id, operation=history.OP_INSERT,
                values=coerced, changed_by=user_email,
                editable_columns=EDITABLE_COLUMNS, changed_at=now,
            )
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'repcode_id': new_id}), 201
    except Exception as e:
        current_app.logger.exception('repcodes.create_row failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/<int:repcode_id>', methods=['PUT'])
def update_row(repcode_id: int) -> Any:
    """Last-write-wins update of all editable columns."""
    try:
        coerced = _row_from_payload(request.get_json(silent=True) or {})
    except ValueError as e:
        return _err(str(e), 400)

    set_clause = ', '.join(f'[{c}] = ?' for c in EDITABLE_COLUMNS)
    set_clause += ', [modified_by] = ?, [modified_at] = ?'
    user_email = _user_email()
    now = datetime.utcnow()
    params: list = [coerced[c] for c in EDITABLE_COLUMNS]
    params.append(user_email)
    params.append(now)
    params.append(repcode_id)

    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        cursor.execute(
            f'UPDATE tho.repcodes SET {set_clause} WHERE [repcode_id] = ?',
            params,
        )
        affected = cursor.rowcount
        if affected == 0:
            conn.rollback()
            cursor.close()
            return _err(f'No row with repcode_id={repcode_id}', 404)
        # After-image snapshot in the same transaction as the live update.
        history.record_snapshot(
            cursor, repcode_id=repcode_id, operation=history.OP_UPDATE,
            values=coerced, changed_by=user_email,
            editable_columns=EDITABLE_COLUMNS, changed_at=now,
        )
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'repcode_id': repcode_id})
    except Exception as e:
        current_app.logger.exception('repcodes.update_row failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/<int:repcode_id>', methods=['DELETE'])
def delete_row(repcode_id: int) -> Any:
    user_email = _user_email()
    now = datetime.utcnow()
    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        # Snapshot the last-known state BEFORE the delete so it can be restored.
        last_values = history.fetch_live_values(cursor, repcode_id, EDITABLE_COLUMNS)
        if last_values is None:
            cursor.close()
            return _err(f'No row with repcode_id={repcode_id}', 404)
        cursor.execute(
            'DELETE FROM tho.repcodes WHERE [repcode_id] = ?', (repcode_id,)
        )
        affected = cursor.rowcount
        if affected == 0:
            conn.rollback()
            cursor.close()
            return _err(f'No row with repcode_id={repcode_id}', 404)
        history.record_snapshot(
            cursor, repcode_id=repcode_id, operation=history.OP_DELETE,
            values=last_values, changed_by=user_email,
            editable_columns=EDITABLE_COLUMNS, changed_at=now,
        )
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'repcode_id': repcode_id})
    except Exception as e:
        current_app.logger.exception('repcodes.delete_row failed')
        return _err(f'{type(e).__name__}: {e}', 500)


# Bulk upsert from CSV-like JSON payload. Match by Fidelity G # or Schwab Master Account.
BULK_MATCH_KEYS: frozenset[str] = frozenset({'fidelity_g_number', 'schwab_master_account'})
BULK_MAX_ROWS = 5000


@bp.route('/bulk', methods=['POST'])
def bulk_upsert() -> Any:
    body = request.get_json(silent=True) or {}
    match_key = body.get('match_key')
    rows = body.get('rows')

    if match_key not in BULK_MATCH_KEYS:
        return _err(f'match_key must be one of {sorted(BULK_MATCH_KEYS)}', 400)
    if not isinstance(rows, list) or not rows:
        return _err('rows must be a non-empty array', 400)
    if len(rows) > BULK_MAX_ROWS:
        return _err(f'rows exceeds max of {BULK_MAX_ROWS}', 400)

    coerced_rows: list[dict] = []
    for i, raw in enumerate(rows):
        try:
            coerced_rows.append(_row_from_payload(raw))
        except ValueError as e:
            return _err(f'Row {i}: {e}', 400)

    keys_to_lookup = sorted({r[match_key] for r in coerced_rows if r.get(match_key)})
    user_email = _user_email()
    now = datetime.utcnow()
    # All snapshots from this import share a batch_id so the whole upload can be
    # undone as a unit from the UI.
    batch_id = history.new_batch_id()
    inserted = 0
    updated = 0
    errors: list[dict] = []

    set_clause = ', '.join(f'[{c}] = ?' for c in EDITABLE_COLUMNS)
    set_clause += ', [modified_by] = ?, [modified_at] = ?'
    insert_cols = [*EDITABLE_COLUMNS, 'modified_by', 'modified_at']
    insert_col_list = ', '.join(f'[{c}]' for c in insert_cols)
    insert_placeholders = ', '.join('?' for _ in insert_cols)

    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        existing: dict[str, int] = {}
        if keys_to_lookup:
            CHUNK = 500
            for start in range(0, len(keys_to_lookup), CHUNK):
                chunk = keys_to_lookup[start:start + CHUNK]
                placeholders = ', '.join('?' for _ in chunk)
                cursor.execute(
                    f'SELECT [{match_key}], [repcode_id] FROM tho.repcodes '
                    f'WHERE [{match_key}] IN ({placeholders})',
                    chunk,
                )
                for k, rid in cursor.fetchall():
                    if k is not None:
                        existing[str(k)] = int(rid)

        for i, row in enumerate(coerced_rows):
            key_val = row.get(match_key)
            try:
                if key_val and key_val in existing:
                    rid = existing[key_val]
                    params = [row[c] for c in EDITABLE_COLUMNS] + [user_email, now, rid]
                    cursor.execute(
                        f'UPDATE tho.repcodes SET {set_clause} WHERE [repcode_id] = ?',
                        params,
                    )
                    history.record_snapshot(
                        cursor, repcode_id=rid, operation=history.OP_UPDATE,
                        values=row, changed_by=user_email,
                        editable_columns=EDITABLE_COLUMNS, source='bulk',
                        batch_id=batch_id, changed_at=now,
                    )
                    updated += 1
                else:
                    params = [row[c] for c in EDITABLE_COLUMNS] + [user_email, now]
                    cursor.execute(
                        f'INSERT INTO tho.repcodes ({insert_col_list}) VALUES ({insert_placeholders})',
                        params,
                    )
                    # Synapse has no SCOPE_IDENTITY(); read the generated id back
                    # with MAX([repcode_id]) (writes here are serialized).
                    cursor.execute('SELECT CAST(MAX([repcode_id]) AS INT) FROM tho.repcodes')
                    new_id_row = cursor.fetchone()
                    if new_id_row and new_id_row[0] is not None:
                        history.record_snapshot(
                            cursor, repcode_id=int(new_id_row[0]),
                            operation=history.OP_INSERT, values=row,
                            changed_by=user_email, editable_columns=EDITABLE_COLUMNS,
                            source='bulk', batch_id=batch_id, changed_at=now,
                        )
                    inserted += 1
            except Exception as e:  # noqa: BLE001 - per-row error capture
                errors.append({'row_index': i, 'error': f'{type(e).__name__}: {e}'})

        conn.commit()
        cursor.close()
        return jsonify({
            'success': True,
            'inserted': inserted,
            'updated': updated,
            'errors': errors,
            'total': len(coerced_rows),
            # Returned so the UI can offer "undo this entire import".
            'batch_id': batch_id if (inserted or updated) else None,
        })
    except Exception as e:
        current_app.logger.exception('repcodes.bulk_upsert failed')
        return _err(f'{type(e).__name__}: {e}', 500)


# ============================================================================
# Change history + rollback
# ============================================================================
HISTORY_FEED_LIMIT_DEFAULT = 50
HISTORY_FEED_LIMIT_MAX = 500


@bp.route('/history', methods=['GET'])
def recent_history() -> Any:
    """Recent changes across all rows (newest first) for the activity feed."""
    try:
        limit = int(request.args.get('limit', HISTORY_FEED_LIMIT_DEFAULT))
    except (TypeError, ValueError):
        limit = HISTORY_FEED_LIMIT_DEFAULT
    limit = max(1, min(limit, HISTORY_FEED_LIMIT_MAX))
    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        rows = history.recent_history(cursor, limit, EDITABLE_COLUMNS)
        cursor.close()
        return jsonify({'success': True, 'rows': rows, 'editable_columns': list(EDITABLE_COLUMNS)})
    except Exception as e:
        current_app.logger.exception('repcodes.recent_history failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/<int:repcode_id>/history', methods=['GET'])
def row_history(repcode_id: int) -> Any:
    """Full change timeline for a single rep code (newest first)."""
    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        rows = history.history_for_repcode(cursor, repcode_id, EDITABLE_COLUMNS)
        cursor.close()
        return jsonify({'success': True, 'rows': rows, 'editable_columns': list(EDITABLE_COLUMNS)})
    except Exception as e:
        current_app.logger.exception('repcodes.row_history failed')
        return _err(f'{type(e).__name__}: {e}', 500)


def _values_from_history(entry: dict) -> dict:
    """Pull just the editable column values out of a serialized history row."""
    return {c: entry.get(c) for c in EDITABLE_COLUMNS}


@bp.route('/<int:repcode_id>/restore/<int:history_id>', methods=['POST'])
def restore_version(repcode_id: int, history_id: int) -> Any:
    """Make the live row match a chosen history snapshot ("restore this version").

    Works whether the row currently exists (UPDATE) or was deleted (re-INSERT
    with its original id). The restore is itself journaled as a RESTORE row.
    """
    user_email = _user_email()
    now = datetime.utcnow()
    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        entry = history.get_history_row(cursor, history_id, EDITABLE_COLUMNS)
        if entry is None or int(entry['repcode_id']) != repcode_id:
            cursor.close()
            return _err(f'No history #{history_id} for repcode_id={repcode_id}', 404)
        values = _values_from_history(entry)
        outcome = history.apply_snapshot_values(
            cursor, repcode_id=repcode_id, values=values,
            changed_by=user_email, editable_columns=EDITABLE_COLUMNS, changed_at=now,
        )
        history.record_snapshot(
            cursor, repcode_id=repcode_id, operation=history.OP_RESTORE,
            values=values, changed_by=user_email,
            editable_columns=EDITABLE_COLUMNS, changed_at=now,
        )
        conn.commit()
        cursor.close()
        return jsonify({
            'success': True, 'repcode_id': repcode_id,
            'restored_from': history_id, 'outcome': outcome,
        })
    except Exception as e:
        current_app.logger.exception('repcodes.restore_version failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/history/<int:history_id>/undo', methods=['POST'])
def undo_change(history_id: int) -> Any:
    """Revert a single change: put the row back to its state *before* this entry.

    - If a prior snapshot exists, the row is reset to it.
    - If this entry was the row's first appearance (an INSERT with no prior),
      undo means deleting the row.
    """
    user_email = _user_email()
    now = datetime.utcnow()
    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        entry = history.get_history_row(cursor, history_id, EDITABLE_COLUMNS)
        if entry is None:
            cursor.close()
            return _err(f'No history #{history_id}', 404)
        repcode_id = int(entry['repcode_id'])
        prior = history.prior_snapshot(cursor, repcode_id, history_id, EDITABLE_COLUMNS)
        if prior is None:
            # First-ever appearance of this row -> undo = delete (if still present).
            existed = history.fetch_live_values(cursor, repcode_id, EDITABLE_COLUMNS)
            if existed is not None:
                history.delete_live(cursor, repcode_id)
                history.record_snapshot(
                    cursor, repcode_id=repcode_id, operation=history.OP_DELETE,
                    values=existed, changed_by=user_email,
                    editable_columns=EDITABLE_COLUMNS, changed_at=now,
                )
            outcome = 'deleted'
        else:
            values = _values_from_history(prior)
            outcome = history.apply_snapshot_values(
                cursor, repcode_id=repcode_id, values=values,
                changed_by=user_email, editable_columns=EDITABLE_COLUMNS, changed_at=now,
            )
            history.record_snapshot(
                cursor, repcode_id=repcode_id, operation=history.OP_RESTORE,
                values=values, changed_by=user_email,
                editable_columns=EDITABLE_COLUMNS, changed_at=now,
            )
        conn.commit()
        cursor.close()
        return jsonify({'success': True, 'repcode_id': repcode_id, 'outcome': outcome})
    except Exception as e:
        current_app.logger.exception('repcodes.undo_change failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/history/batch/<batch_id>/undo', methods=['POST'])
def undo_batch(batch_id: str) -> Any:
    """Undo an entire bulk import: revert every row it touched to its prior state."""
    user_email = _user_email()
    now = datetime.utcnow()
    try:
        conn = _get_conn()
        _ensure_history(conn)
        cursor = conn.cursor()
        entries = history.batch_entries(cursor, batch_id, EDITABLE_COLUMNS)
        if not entries:
            cursor.close()
            return _err(f'No changes found for batch {batch_id}', 404)
        reverted = 0
        deleted = 0
        for entry in entries:
            repcode_id = int(entry['repcode_id'])
            hid = int(entry['history_id'])
            prior = history.prior_snapshot(cursor, repcode_id, hid, EDITABLE_COLUMNS)
            if prior is None:
                existed = history.fetch_live_values(cursor, repcode_id, EDITABLE_COLUMNS)
                if existed is not None:
                    history.delete_live(cursor, repcode_id)
                    history.record_snapshot(
                        cursor, repcode_id=repcode_id, operation=history.OP_DELETE,
                        values=existed, changed_by=user_email,
                        editable_columns=EDITABLE_COLUMNS, changed_at=now,
                    )
                    deleted += 1
            else:
                values = _values_from_history(prior)
                history.apply_snapshot_values(
                    cursor, repcode_id=repcode_id, values=values,
                    changed_by=user_email, editable_columns=EDITABLE_COLUMNS, changed_at=now,
                )
                history.record_snapshot(
                    cursor, repcode_id=repcode_id, operation=history.OP_RESTORE,
                    values=values, changed_by=user_email,
                    editable_columns=EDITABLE_COLUMNS, changed_at=now,
                )
                reverted += 1
        conn.commit()
        cursor.close()
        return jsonify({
            'success': True, 'batch_id': batch_id,
            'reverted': reverted, 'deleted': deleted, 'total': len(entries),
        })
    except Exception as e:
        current_app.logger.exception('repcodes.undo_batch failed')
        return _err(f'{type(e).__name__}: {e}', 500)
