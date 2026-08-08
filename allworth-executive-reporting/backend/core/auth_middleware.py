"""JWT validation middleware for Entra-issued ID tokens.

Verifies that incoming requests carry a Bearer token signed by the configured
Entra tenant (issuer) and intended for the configured audience (this app's
client ID).  This is a defense-in-depth layer: the SPA frontend gates access
client-side via MSAL, but the backend MUST also reject any unauthenticated
API request because the SPA shell is served unauthenticated by nginx.

Configuration (env vars):
    ENTRA_TENANT_ID   - required.  Tenant GUID.
    ENTRA_CLIENT_ID   - required.  Application (client) ID.  Used as the
                        default accepted audience (also matches the access-
                        token form ``api://<client-id>``).
    ENTRA_AUDIENCE    - optional.  Comma-separated list of additional accepted
                        ``aud`` values (e.g. a custom App ID URI).
    AUTH_DISABLE      - optional.  Set to "1" / "true" to bypass auth entirely
                        (local dev only).  Ignored when AUTH_REQUIRED=1.
    AUTH_REQUIRED     - optional.  Set to "1" / "true" to FAIL STARTUP if the
                        tenant/client are not configured (or AUTH_DISABLE is
                        set).  Use this in production deploys to prevent a
                        misconfigured container from serving unauthenticated.
    AUTH_ALLOWED_EMAILS - optional.  Comma-separated allowlist of user emails
                        / UPNs.  When set, the token's preferred_username /
                        upn / email must match (case-insensitive).
    AUTH_REQUIRED_ROLES - optional.  Comma-separated app roles.  When set,
                        the token's ``roles`` claim must contain at least one.
    AUTH_REQUIRED_GROUPS - optional.  Comma-separated group object IDs.  When
                        set, the token's ``groups`` claim must contain at
                        least one.
    AUTH_LEEWAY_SECONDS - optional.  Clock-skew tolerance for exp/nbf.
                        Defaults to 60.

Bypass paths (always allowed without a token):
    /api/health, OPTIONS preflight requests.
"""
from __future__ import annotations

import os
import time
from threading import Lock
from typing import Any

import jwt
import requests
from flask import jsonify, request


def _truthy(val: str | None) -> bool:
    return (val or '').strip().lower() in ('1', 'true', 'yes', 'on')


def _csv(val: str | None) -> list[str]:
    return [s.strip() for s in (val or '').split(',') if s.strip()]


_TENANT_ID = os.getenv('ENTRA_TENANT_ID') or os.getenv('AZURE_TENANT_ID', '')
_CLIENT_ID = os.getenv('ENTRA_CLIENT_ID', '')
# Accept both the ID-token audience (bare client-id GUID) and the access-token
# audience (api://<client-id>) by default, plus any explicit overrides.
_AUDIENCES: list[str] = []
if _CLIENT_ID:
    _AUDIENCES.extend([_CLIENT_ID, f'api://{_CLIENT_ID}'])
_AUDIENCES.extend(
    a for a in _csv(os.getenv('ENTRA_AUDIENCE')) if a not in _AUDIENCES
)
_DISABLED = _truthy(os.getenv('AUTH_DISABLE'))
_REQUIRED = _truthy(os.getenv('AUTH_REQUIRED'))
_ALLOWED_EMAILS = {e.lower() for e in _csv(os.getenv('AUTH_ALLOWED_EMAILS'))}
_REQUIRED_ROLES = set(_csv(os.getenv('AUTH_REQUIRED_ROLES')))
_REQUIRED_GROUPS = set(_csv(os.getenv('AUTH_REQUIRED_GROUPS')))
try:
    _LEEWAY = int(os.getenv('AUTH_LEEWAY_SECONDS', '60'))
except ValueError:
    _LEEWAY = 60

# Allowed issuer values – v2.0 endpoint plus the legacy sts.windows.net form
# that some MSAL flows still emit.
_ISSUERS = (
    f'https://login.microsoftonline.com/{_TENANT_ID}/v2.0',
    f'https://sts.windows.net/{_TENANT_ID}/',
)
_JWKS_URL = (
    f'https://login.microsoftonline.com/{_TENANT_ID}/discovery/v2.0/keys'
)

# Paths that bypass auth entirely.
_BYPASS_PATHS = {'/api/health'}

# JWKS cache: refresh once per hour
_JWKS_TTL_SECONDS = 3600
_jwks_lock = Lock()
_jwks_cache: dict[str, Any] = {'fetched_at': 0.0, 'keys': {}}


def is_configured() -> bool:
    return bool(_TENANT_ID and _CLIENT_ID)


def _fetch_jwks() -> dict[str, Any]:
    """Return the {kid: PyJWK-key} map, refreshing from the IdP as needed."""
    with _jwks_lock:
        now = time.time()
        if (
            _jwks_cache['keys']
            and (now - _jwks_cache['fetched_at']) < _JWKS_TTL_SECONDS
        ):
            return _jwks_cache['keys']
        resp = requests.get(_JWKS_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        keys: dict[str, Any] = {}
        for jwk_dict in data.get('keys', []):
            kid = jwk_dict.get('kid')
            if not kid:
                continue
            try:
                keys[kid] = jwt.PyJWK(jwk_dict).key
            except Exception:  # pragma: no cover - defensive
                continue
        _jwks_cache['keys'] = keys
        _jwks_cache['fetched_at'] = now
        return keys


def _validate_token(token: str) -> dict[str, Any]:
    """Validate the bearer token and return its decoded claims, or raise."""
    unverified = jwt.get_unverified_header(token)
    kid = unverified.get('kid')
    if not kid:
        raise jwt.InvalidTokenError('Token missing kid header')
    keys = _fetch_jwks()
    key = keys.get(kid)
    if key is None:
        # Force a refresh in case the signing key rotated
        _jwks_cache['fetched_at'] = 0.0
        keys = _fetch_jwks()
        key = keys.get(kid)
    if key is None:
        raise jwt.InvalidTokenError(f'Unknown signing key kid={kid}')
    return jwt.decode(
        token,
        key=key,
        algorithms=['RS256'],
        audience=_AUDIENCES,
        issuer=list(_ISSUERS),
        leeway=_LEEWAY,
        options={'require': ['exp', 'iss', 'aud']},
    )


def _email_from_claims(claims: dict[str, Any]) -> str | None:
    return (
        claims.get('preferred_username')
        or claims.get('upn')
        or claims.get('email')
        or claims.get('unique_name')
    )


def _easyauth_identity(req: Any) -> str | None:
    """Return the user identity injected by App Service Authentication.

    App Service ("Easy Auth") authenticates the request at the platform edge
    and injects ``X-MS-CLIENT-PRINCIPAL-NAME`` / ``X-MS-CLIENT-PRINCIPAL``.
    These headers are trustworthy inside the app because the platform strips
    any client-supplied versions before forwarding.  Returns the user's
    email/UPN, or None if no Easy Auth identity is present.
    """
    name = req.headers.get('X-MS-CLIENT-PRINCIPAL-NAME')
    if name:
        return name
    blob = req.headers.get('X-MS-CLIENT-PRINCIPAL')
    if not blob:
        return None
    try:
        import base64
        import json

        decoded = base64.b64decode(blob)
        data = json.loads(decoded)
        claims = {
            c.get('typ'): c.get('val')
            for c in data.get('claims', [])
            if c.get('typ')
        }
    except Exception:  # pragma: no cover - defensive
        return None
    return (
        claims.get('preferred_username')
        or claims.get('upn')
        or claims.get('email')
        or claims.get(
            'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress'
        )
        or claims.get('name')
    )


def _dev_user() -> dict[str, str | None] | None:
    """Synthetic signed-in user for local dev (AUTH_DEV_EMAIL / AUTH_DEV_NAME).

    Ignored whenever real Entra SSO is configured, so it can never impersonate
    a user in a production deployment.
    """
    email = (os.getenv('AUTH_DEV_EMAIL') or '').strip()
    if not email or is_configured():
        return None
    name = (os.getenv('AUTH_DEV_NAME') or '').strip() or (
        email.split('@')[0].replace('.', ' ').title()
    )
    return {'email': email, 'name': name}


def easy_auth_user(req: Any = None) -> dict[str, str | None] | None:
    """Return {'email', 'name'} for the Easy Auth identity, or None.

    Accepts any request-like object with ``.headers`` (defaults to the active
    Flask request). Falls back to a local dev identity (``AUTH_DEV_EMAIL``)
    when no Easy Auth header is present and real Entra SSO is not configured.
    """
    req = req if req is not None else request
    identity = _easyauth_identity(req)
    if not identity:
        return _dev_user()
    name = identity.split('@')[0].replace('.', ' ').title() if '@' in identity else identity
    return {'email': identity, 'name': name}


def _authorize(claims: dict[str, Any]) -> str | None:
    """Return None if claims pass the configured allowlists, else an error string."""
    if _ALLOWED_EMAILS:
        email = (_email_from_claims(claims) or '').lower()
        if email not in _ALLOWED_EMAILS:
            return 'User not in allowlist'
    if _REQUIRED_ROLES:
        roles = set(claims.get('roles') or [])
        if roles.isdisjoint(_REQUIRED_ROLES):
            return 'Missing required role'
    if _REQUIRED_GROUPS:
        groups = set(claims.get('groups') or [])
        if groups.isdisjoint(_REQUIRED_GROUPS):
            return 'Missing required group'
    return None


def _bypass(path: str) -> bool:
    return path in _BYPASS_PATHS


def install(app) -> None:
    """Register the JWT-enforcing before_request hook on the Flask app."""
    if _DISABLED:
        if _REQUIRED:
            raise RuntimeError(
                'AUTH_REQUIRED=1 but AUTH_DISABLE is set – refusing to start '
                'with auth bypassed.'
            )
        app.logger.warning('🔓 AUTH_DISABLE=1 – JWT validation BYPASSED')
        return
    if not is_configured():
        if _REQUIRED:
            raise RuntimeError(
                'AUTH_REQUIRED=1 but ENTRA_TENANT_ID / ENTRA_CLIENT_ID are '
                'not configured – refusing to start without SSO gating.'
            )
        app.logger.warning(
            '🔓 ENTRA_TENANT_ID / ENTRA_CLIENT_ID not configured – '
            'JWT validation BYPASSED (set them to enable SSO gating)'
        )
        return

    app.logger.info(
        f'🔐 JWT validation enabled (tenant={_TENANT_ID}, '
        f'audiences={_AUDIENCES}, leeway={_LEEWAY}s)'
    )
    if _ALLOWED_EMAILS:
        app.logger.info(
            f'🔐 Email allowlist active ({len(_ALLOWED_EMAILS)} entries)'
        )
    if _REQUIRED_ROLES:
        app.logger.info(f'🔐 Required roles: {sorted(_REQUIRED_ROLES)}')
    if _REQUIRED_GROUPS:
        app.logger.info(f'🔐 Required groups: {sorted(_REQUIRED_GROUPS)}')

    @app.before_request
    def _enforce_jwt() -> Any:  # type: ignore[reportUnusedFunction]
        # CORS preflight: never gated.
        if request.method == 'OPTIONS':
            return None
        if _bypass(request.path):
            return None
        auth = request.headers.get('Authorization', '')
        if not auth.lower().startswith('bearer '):
            # No Bearer token.  Fall back to the App Service Authentication
            # ("Easy Auth") identity injected by the platform edge, which is
            # the SSO mechanism actually fronting this app.  nginx forwards the
            # X-MS-CLIENT-PRINCIPAL* headers to the backend sidecar.
            easyauth_email = _easyauth_identity(request)
            if easyauth_email is not None:
                if _ALLOWED_EMAILS and easyauth_email.lower() not in _ALLOWED_EMAILS:
                    return jsonify({
                        'success': False,
                        'error': 'User not in allowlist',
                    }), 403
                request.environ['user.email'] = easyauth_email
                return None
            return jsonify({
                'success': False,
                'error': 'Missing Bearer token',
            }), 401
        token = auth[7:].strip()
        try:
            claims = _validate_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({'success': False, 'error': 'Token expired'}), 401
        except jwt.InvalidAudienceError:
            return jsonify({'success': False, 'error': 'Invalid audience'}), 401
        except jwt.InvalidIssuerError:
            return jsonify({'success': False, 'error': 'Invalid issuer'}), 401
        except jwt.InvalidTokenError as e:
            return jsonify({
                'success': False,
                'error': f'Invalid token: {e}',
            }), 401
        # Allowlist / role / group enforcement (if configured).
        deny = _authorize(claims)
        if deny is not None:
            return jsonify({'success': False, 'error': deny}), 403
        # Stash the user identity for downstream handlers / audit logs.
        request.environ['user.email'] = _email_from_claims(claims)
        request.environ['user.claims'] = claims
        return None
