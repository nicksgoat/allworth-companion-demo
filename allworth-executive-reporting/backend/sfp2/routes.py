"""Flask blueprint for the SFP2 schema-manager page.

Endpoints (mounted at /api/sfp2 by app.py):
  GET    /tables                 - list bronze/sfp2/<Object> Delta tables
  GET    /sobjects               - list Salesforce SObjects (?custom=1 for custom only)
  GET    /describe?sobject=...   - describe a single SObject
  GET    /schema?table=...       - return Delta schema for a single table
  GET    /diff?table=...&sobject=...  - 3-bucket diff
  POST   /columns/preview        - dry-run: proposed Delta type + warnings
  POST   /columns                - queue a column add for the overnight refresh
  DELETE /columns                - queue a column drop for the overnight refresh
  GET    /schema-changes         - recent audit rows w/ derived state (pending/done/failed/canceled)
  DELETE /schema-changes/pending - cancel a queued drop

Access control: all routes require an email present in SFP2_ALLOWED_EMAILS.
The user's email is read from the Easy Auth header `X-MS-CLIENT-PRINCIPAL-NAME`
in production, or from the env var DEV_USER_EMAIL for local development.
"""
from __future__ import annotations

import os
from typing import Any

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint('sfp2', __name__)


def _allowed_emails() -> set[str]:
    raw = os.getenv('SFP2_ALLOWED_EMAILS', '')
    return {e.strip().lower() for e in raw.split(',') if e.strip()}


def _current_user_email() -> str | None:
    # App Service Easy Auth populates this header.
    header = request.headers.get('X-MS-CLIENT-PRINCIPAL-NAME')
    if header:
        return header.strip().lower()
    # ThoughtSpot / generic forwarders
    fwd = request.headers.get('X-User-Email') or request.headers.get('X-Forwarded-Email')
    if fwd:
        return fwd.strip().lower()
    # Local-dev fallback
    dev = os.getenv('DEV_USER_EMAIL')
    if dev:
        return dev.strip().lower()
    return None


@bp.before_request
def _enforce_allowlist() -> Any:
    if os.getenv('SFP2_DISABLE_AUTH', '').lower() in ('1', 'true', 'yes'):
        request.environ['sfp2.user_email'] = (
            os.getenv('DEV_USER_EMAIL') or 'auth-disabled@local'
        )
        return None
    allowed = _allowed_emails()
    if not allowed:
        return jsonify({
            'success': False,
            'error': 'SFP2_ALLOWED_EMAILS is not configured on the server.',
        }), 503
    email = _current_user_email()
    if not email:
        return jsonify({
            'success': False,
            'error': 'No user email available. Easy Auth or DEV_USER_EMAIL must be configured.',
        }), 401
    if email not in allowed:
        return jsonify({
            'success': False,
            'error': f'User {email} is not authorized for SFP2 schema management.',
        }), 403
    # Stash for downstream handlers (e.g. audit log)
    request.environ['sfp2.user_email'] = email
    return None


def _err(msg: str, status: int = 500) -> Any:
    return jsonify({'success': False, 'error': msg}), status


@bp.route('/whoami', methods=['GET'])
def whoami() -> Any:
    return jsonify({
        'success': True,
        'email': request.environ.get('sfp2.user_email'),
    })


@bp.route('/credcheck', methods=['GET'])
def credcheck_route() -> Any:
    """TEMPORARY diagnostic: report what each Salesforce credential source
    contains and whether Key Vault is reachable — WITHOUT exposing secret
    values (only length, an 8-char SHA-256 prefix, and whitespace flags).

    Hit this on both dev and prod and compare. If a password/token `sha8`
    differs between the working slot and the failing slot, that slot is using
    a different/stale value. If they match, the credential value is not the
    problem (look at domain/IP/lockout instead).

    Pass ?login=1 to also attempt a *single* fresh Salesforce login and report
    the result. Omitted by default so repeated page loads don't hammer (and
    risk locking) the Salesforce user. Remove this route once diagnosed.
    """
    import hashlib
    from . import salesforce_client as sc

    def fp(v: Any) -> dict[str, Any]:
        if not v:
            return {'present': False}
        b = str(v).encode('utf-8', 'replace')
        return {
            'present': True,
            'len': len(str(v)),
            'sha8': hashlib.sha256(b).hexdigest()[:8],
            'leading_ws': str(v) != str(v).lstrip(),
            'trailing_ws': str(v) != str(v).rstrip(),
        }

    out: dict[str, Any] = {
        'sfp2_available': sc.SFP2_AVAILABLE,
        'import_error': sc.SFP2_IMPORT_ERROR,
        'sf_domain': sc.SF_DOMAIN,
        'allow_env_fallback': sc.ALLOW_ENV_SF_CREDS,
        'key_vault_url': sc.KEY_VAULT_URL,
        'secret_names': {
            'username': sc.SECRET_USERNAME,
            'password': sc.SECRET_PASSWORD,
            'token': sc.SECRET_TOKEN,
        },
    }

    # Source 1: env vars (SF_USERNAME / SF_PASSWORD / SF_TOKEN)
    env = sc._env_credentials()
    if env is not None:
        out['env'] = {
            'available': True,
            'username': env[0],
            'password': fp(env[1]),
            'token': fp(env[2]),
        }
    else:
        out['env'] = {'available': False}

    # Source 2: Key Vault — reveals whether THIS slot can reach the vault.
    try:
        kv = sc._fetch_from_key_vault()
        out['key_vault'] = {
            'reachable': True,
            'username': kv[0],
            'password': fp(kv[1]),
            'token': fp(kv[2]),
        }
    except Exception as e:
        out['key_vault'] = {
            'reachable': False,
            'error': f'{type(e).__name__}: {e}',
        }

    # Which source would get_salesforce() actually use right now?
    if out['key_vault'].get('reachable'):
        out['effective_source'] = 'key_vault'
    elif sc.ALLOW_ENV_SF_CREDS and out['env'].get('available'):
        out['effective_source'] = 'env_fallback'
    else:
        out['effective_source'] = 'none (would raise)'

    # Optional: one real login attempt (clears the cache to force a fresh auth).
    if request.args.get('login', '').lower() in ('1', 'true', 'yes'):
        try:
            sc._sf_cache['sf'] = None
            sc._sf_cache['fetched_at'] = 0.0
            sf = sc.get_salesforce()
            _ = sf.session_id  # touch to confirm the session is live
            out['login'] = {'ok': True}
        except Exception as e:
            out['login'] = {'ok': False, 'error': f'{type(e).__name__}: {e}'}

    return jsonify(out)


@bp.route('/tables', methods=['GET'])
def list_tables_route() -> Any:
    try:
        from .delta_admin import list_tables  # local import: defensive
        tables = list_tables()
        return jsonify({'success': True, 'tables': tables})
    except Exception as e:  # pragma: no cover - surface to client
        current_app.logger.exception('sfp2.list_tables failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/schema', methods=['GET'])
def get_schema_route() -> Any:
    table = request.args.get('table', '').strip()
    if not table:
        return _err('Missing required query param: table', 400)
    try:
        from .delta_admin import get_table_schema
        cols = get_table_schema(table)
        return jsonify({'success': True, 'table': table, 'columns': cols})
    except Exception as e:
        current_app.logger.exception('sfp2.get_schema failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/sobjects', methods=['GET'])
def list_sobjects_route() -> Any:
    custom_only = request.args.get('custom', '').lower() in ('1', 'true', 'yes')
    try:
        from .salesforce_client import list_sobjects
        return jsonify({'success': True, 'sobjects': list_sobjects(custom_only=custom_only)})
    except Exception as e:
        current_app.logger.exception('sfp2.list_sobjects failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/describe', methods=['GET'])
def describe_route() -> Any:
    sobject = request.args.get('sobject', '').strip()
    if not sobject:
        return _err('Missing required query param: sobject', 400)
    try:
        from .salesforce_client import describe_object
        fields = describe_object(sobject)
        return jsonify({'success': True, 'sobject': sobject, 'fields': fields})
    except Exception as e:
        current_app.logger.exception('sfp2.describe failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/diff', methods=['GET'])
def diff_route() -> Any:
    table = request.args.get('table', '').strip()
    sobject = request.args.get('sobject', '').strip() or table
    if not table:
        return _err('Missing required query param: table', 400)
    try:
        from .delta_admin import get_table_schema
        from .salesforce_client import describe_object
        from . import notebook_refs
        delta_cols = get_table_schema(table)
        sf_fields = describe_object(sobject)

        delta_by_lower = {c['name'].lower(): c for c in delta_cols}
        sf_by_lower = {f['name'].lower(): f for f in sf_fields}

        in_both: list[dict[str, Any]] = []
        only_in_delta: list[dict[str, Any]] = []
        only_in_sf: list[dict[str, Any]] = []

        for key, dcol in delta_by_lower.items():
            sf = sf_by_lower.get(key)
            refs = notebook_refs.references_for(dcol['name'])
            if sf is not None:
                row: dict[str, Any] = {
                    'name': dcol['name'],
                    'delta_type': dcol['type'],
                    'sf_type': sf.get('type'),
                    'sf_label': sf.get('label'),
                    'custom': sf.get('custom'),
                }
                if refs:
                    row['referenced_in'] = refs
                in_both.append(row)
            else:
                row = {
                    'name': dcol['name'],
                    'delta_type': dcol['type'],
                }
                if refs:
                    row['referenced_in'] = refs
                only_in_delta.append(row)
        for key, sf in sf_by_lower.items():
            if key in delta_by_lower:
                continue
            only_in_sf.append({
                'name': sf.get('name'),
                'label': sf.get('label'),
                # Provide both keys: `type` for SfField shape (used when adding
                # back to Delta), `sf_type` for display parity with in_both rows.
                'type': sf.get('type'),
                'sf_type': sf.get('type'),
                'length': sf.get('length'),
                'precision': sf.get('precision'),
                'scale': sf.get('scale'),
                'nillable': sf.get('nillable'),
                'custom': sf.get('custom'),
            })

        in_both.sort(key=lambda r: r['name'].lower())
        only_in_delta.sort(key=lambda r: r['name'].lower())
        only_in_sf.sort(key=lambda r: (r['name'] or '').lower())

        return jsonify({
            'success': True,
            'table': table,
            'sobject': sobject,
            'counts': {
                'delta': len(delta_cols),
                'sf': len(sf_fields),
                'in_both': len(in_both),
                'only_in_delta': len(only_in_delta),
                'only_in_sf': len(only_in_sf),
            },
            'in_both': in_both,
            'only_in_delta': only_in_delta,
            'only_in_sf': only_in_sf,
        })
    except Exception as e:
        current_app.logger.exception('sfp2.diff failed')
        return _err(f'{type(e).__name__}: {e}', 500)


def _user_email() -> str | None:
    return request.environ.get('sfp2.user_email')


def _request_id() -> str | None:
    return (
        request.headers.get('X-Request-ID')
        or request.headers.get('X-Request-Id')
        or request.headers.get('X-Correlation-ID')
    )


@bp.route('/columns/preview', methods=['POST'])
def preview_column_route() -> Any:
    """Return the proposed Delta type + warnings for an add. Read-only."""
    body = request.get_json(silent=True) or {}
    table = (body.get('table') or '').strip()
    column = (body.get('column') or '').strip()
    sf_field = body.get('sf_field') or {}
    if not table or not column:
        return _err('Missing required body fields: table, column', 400)
    try:
        from .delta_admin import preview_add_column
        result = preview_add_column(table, column, sf_field)
        status = result.get('status', 200)
        return jsonify(result), status
    except ValueError as e:
        # Type-mapping / validation failures are 400, not 500.
        return jsonify({
            'success': False,
            'status': 400,
            'error': str(e),
            'object': table,
            'column': column,
        }), 400
    except Exception as e:
        current_app.logger.exception('sfp2.preview_column failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/columns', methods=['POST'])
def add_column_route() -> Any:
    """Queue a column add for the overnight refresh worker.

    Adds are deferred (not inline) because (a) delta-rs can't write to tables
    that have column mapping enabled, which is true of any table that has been
    through a drop, and (b) a new column would be empty until the next
    overnight Salesforce ingestion backfills it anyway. Returns 202 on success.
    """
    body = request.get_json(silent=True) or {}
    table = (body.get('table') or '').strip()
    column = (body.get('column') or '').strip()
    sf_field = body.get('sf_field') or {}
    if not table or not column:
        return _err('Missing required body fields: table, column', 400)
    from . import audit
    sf_type = (sf_field or {}).get('type') if isinstance(sf_field, dict) else None
    try:
        if audit.has_pending_add(table, column):
            return jsonify({
                'success': False, 'status': 409,
                'error': (
                    f"Column {column!r} on {table} already has a pending add. "
                    "Cancel it first, or wait for the next overnight refresh."
                ),
                'object': table, 'column': column,
            }), 409

        from .delta_admin import add_column
        try:
            result = add_column(table, column, sf_field)
        except ValueError as ve:
            audit.record_change(
                action=audit.ACTION_ADD_QUEUED, table=table, column=column,
                user_email=_user_email(), success=False,
                sf_type=sf_type, error=str(ve),
                request_id=_request_id(),
            )
            return jsonify({
                'success': False, 'status': 400, 'error': str(ve),
                'object': table, 'column': column,
            }), 400
        if not result.get('success'):
            audit.record_change(
                action=audit.ACTION_ADD_QUEUED, table=table, column=column,
                user_email=_user_email(), success=False,
                sf_type=sf_type, error=result.get('error'),
                request_id=_request_id(),
            )
            return jsonify(result), result.get('status', 400)

        # `delta_type` carries the Spark DDL type the worker will use, so the
        # overnight cell does not need to re-run the SF describe.
        audit.record_change(
            action=audit.ACTION_ADD_QUEUED, table=table,
            column=result.get('column') or column,
            user_email=_user_email(), success=True,
            sf_type=sf_type, delta_type=result.get('spark_ddl_type'),
            request_id=_request_id(),
        )
        return jsonify(result), result.get('status', 202)
    except Exception as e:
        current_app.logger.exception('sfp2.add_column failed')
        audit.record_change(
            action=audit.ACTION_ADD_QUEUED, table=table, column=column,
            user_email=_user_email(), success=False,
            sf_type=sf_type, error=f'{type(e).__name__}: {e}',
            request_id=_request_id(),
        )
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/columns', methods=['DELETE'])
def drop_column_route() -> Any:
    """Queue a column drop for the overnight refresh worker.

    delta-rs's Python bindings can't drop columns, so this endpoint validates
    the request and writes a `drop_queued` audit row. The actual ALTER runs in
    the Synapse `overnight_refresh` notebook. Returns 202 on success.
    """
    body = request.get_json(silent=True) or {}
    table = (body.get('table') or '').strip()
    column = (body.get('column') or '').strip()
    if not table or not column:
        return _err('Missing required body fields: table, column', 400)
    from . import audit
    try:
        if audit.has_pending_drop(table, column):
            return jsonify({
                'success': False, 'status': 409,
                'error': (
                    f"Column {column!r} on {table} already has a pending drop. "
                    "Cancel it first, or wait for the next overnight refresh."
                ),
                'object': table, 'column': column,
            }), 409

        from .delta_admin import drop_column
        try:
            result = drop_column(table, column)
        except ValueError as ve:
            audit.record_change(
                action=audit.ACTION_DROP_QUEUED, table=table, column=column,
                user_email=_user_email(), success=False,
                error=str(ve), request_id=_request_id(),
            )
            return jsonify({
                'success': False, 'status': 400, 'error': str(ve),
                'object': table, 'column': column,
            }), 400
        if not result.get('success'):
            # Validation failure (404, 400) — record so failures are auditable.
            audit.record_change(
                action=audit.ACTION_DROP_QUEUED, table=table, column=column,
                user_email=_user_email(), success=False,
                error=result.get('error'), request_id=_request_id(),
            )
            return jsonify(result), result.get('status', 400)

        audit.record_change(
            action=audit.ACTION_DROP_QUEUED, table=table,
            column=result.get('column') or column,
            user_email=_user_email(), success=True,
            request_id=_request_id(),
        )
        return jsonify(result), result.get('status', 202)
    except Exception as e:
        current_app.logger.exception('sfp2.drop_column failed')
        audit.record_change(
            action=audit.ACTION_DROP_QUEUED, table=table, column=column,
            user_email=_user_email(), success=False,
            error=f'{type(e).__name__}: {e}', request_id=_request_id(),
        )
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/schema-changes', methods=['GET'])
def schema_changes_route() -> Any:
    """Return recent audit rows (newest first) with a derived `state` field.

    Query params:
      - table : optional table-name filter (case-insensitive)
      - limit : max rows to return (default 200)
    """
    table = (request.args.get('table') or '').strip() or None
    try:
        limit = int(request.args.get('limit') or 200)
    except ValueError:
        limit = 200
    limit = max(1, min(limit, 1000))
    try:
        from . import audit
        rows = audit.read_recent(table_filter=table, limit=limit)
        return jsonify({'success': True, 'rows': rows})
    except Exception as e:
        current_app.logger.exception('sfp2.schema_changes failed')
        return _err(f'{type(e).__name__}: {e}', 500)


@bp.route('/schema-changes/pending', methods=['DELETE'])
def cancel_pending_drop_route() -> Any:
    """Cancel a queued add or drop by writing a `*_canceled` audit row.

    Body: {"table": "...", "column": "..."}
    """
    body = request.get_json(silent=True) or {}
    table = (body.get('table') or '').strip()
    column = (body.get('column') or '').strip()
    if not table or not column:
        return _err('Missing required body fields: table, column', 400)
    try:
        from . import audit
        if audit.has_pending_drop(table, column):
            cancel_action = audit.ACTION_DROP_CANCELED
        elif audit.has_pending_add(table, column):
            cancel_action = audit.ACTION_ADD_CANCELED
        else:
            return jsonify({
                'success': False, 'status': 404,
                'error': f"No pending change for {column!r} on {table}.",
                'object': table, 'column': column,
            }), 404
        audit.record_change(
            action=cancel_action, table=table, column=column,
            user_email=_user_email(), success=True,
            request_id=_request_id(),
        )
        return jsonify({
            'success': True, 'status': 200,
            'object': table, 'column': column, 'action': cancel_action,
        })
    except Exception as e:
        current_app.logger.exception('sfp2.cancel_pending_drop failed')
        return _err(f'{type(e).__name__}: {e}', 500)

