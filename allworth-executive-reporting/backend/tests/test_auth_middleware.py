"""Smoke tests for auth_middleware.

These tests exercise the JWT-enforcement before_request hook end-to-end
against a minimal Flask app, with the JWKS fetch monkey-patched to return a
locally-generated RS256 keypair so we can mint tokens that validate without
touching Entra.

Run from the backend/ directory:

    python -m pytest tests/test_auth_middleware.py -v
"""
from __future__ import annotations

import importlib
import os
import time
from typing import Any
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask, jsonify


TENANT_ID = '00000000-0000-0000-0000-000000000001'
CLIENT_ID = '11111111-1111-1111-1111-111111111111'
KID = 'test-kid-1'


# ---------------------------------------------------------------------------
# Keypair / token helpers
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def rsa_keypair() -> tuple[Any, Any]:
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _mint_token(
    private_key: Any,
    *,
    aud: str | list[str] = CLIENT_ID,
    iss: str | None = None,
    exp_offset: int = 600,
    nbf_offset: int = -10,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        'aud': aud,
        'iss': iss or f'https://login.microsoftonline.com/{TENANT_ID}/v2.0',
        'iat': now,
        'nbf': now + nbf_offset,
        'exp': now + exp_offset,
        'preferred_username': 'tester@allworthfinancial.com',
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(
        claims, private_key, algorithm='RS256', headers={'kid': KID}
    )


# ---------------------------------------------------------------------------
# Module loading: auth_middleware reads env at import time, so each test set
# that needs different env must reload the module after setting env vars.
# ---------------------------------------------------------------------------
def _load_middleware(monkeypatch, env: dict[str, str], public_key: Any):
    # Wipe any prior auth env so previous tests can't leak in
    for k in list(os.environ):
        if k.startswith(('ENTRA_', 'AUTH_', 'AZURE_TENANT_ID')):
            monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    # Reload to pick up new env
    import auth_middleware  # noqa: WPS433 - intentional late import
    importlib.reload(auth_middleware)

    # Stub the JWKS fetch so no network call is made
    monkeypatch.setattr(
        auth_middleware,
        '_fetch_jwks',
        lambda: {KID: public_key},
    )
    return auth_middleware


def _build_app(auth_middleware) -> Flask:
    app = Flask(__name__)
    app.testing = True
    auth_middleware.install(app)

    @app.get('/api/health')
    def _health():  # type: ignore[reportUnusedFunction]
        return jsonify(ok=True)

    @app.get('/api/protected')
    def _protected():  # type: ignore[reportUnusedFunction]
        from flask import request as _req
        return jsonify(email=_req.environ.get('user.email'))

    # Register fee-calculator blueprint to test auth coverage
    from fee_calculator.routes import bp as fee_calc_bp
    app.register_blueprint(fee_calc_bp, url_prefix='/fee-calculator')

    # Register pipeline-review blueprint to test auth coverage
    from pipeline_review.routes import bp as pipeline_review_bp
    app.register_blueprint(pipeline_review_bp, url_prefix='/pipeline-review')

    # Register Executive Brief blueprint to test auth coverage
    from brief.routes import bp as brief_bp
    app.register_blueprint(brief_bp, url_prefix='/brief')

    # Register Executive Report blueprint to test auth coverage
    from executive_report.routes import bp as executive_report_bp
    app.register_blueprint(executive_report_bp, url_prefix='/executive-report')

    # Register Mailer blueprint to test auth coverage
    from mailer.routes import bp as mailer_bp
    app.register_blueprint(mailer_bp, url_prefix='/mailer')

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestEnforcementEnabled:
    @pytest.fixture
    def client(self, monkeypatch, rsa_keypair):
        priv, pub = rsa_keypair
        mw = _load_middleware(
            monkeypatch,
            {'ENTRA_TENANT_ID': TENANT_ID, 'ENTRA_CLIENT_ID': CLIENT_ID},
            pub,
        )
        app = _build_app(mw)
        return app.test_client(), priv

    def test_health_bypass(self, client):
        c, _ = client
        assert c.get('/api/health').status_code == 200

    def test_options_preflight_bypass(self, client):
        c, _ = client
        # Flask's test client builds a real OPTIONS request
        rv = c.options('/api/protected')
        assert rv.status_code != 401

    def test_missing_token_rejected(self, client):
        c, _ = client
        rv = c.get('/api/protected')
        assert rv.status_code == 401
        assert 'Missing Bearer token' in rv.get_json()['error']

    def test_garbage_token_rejected(self, client):
        c, _ = client
        rv = c.get(
            '/api/protected',
            headers={'Authorization': 'Bearer not.a.real.jwt'},
        )
        assert rv.status_code == 401

    def test_valid_id_token_accepted(self, client):
        c, priv = client
        tok = _mint_token(priv, aud=CLIENT_ID)
        rv = c.get(
            '/api/protected',
            headers={'Authorization': f'Bearer {tok}'},
        )
        assert rv.status_code == 200
        assert rv.get_json()['email'] == 'tester@allworthfinancial.com'

    def test_valid_access_token_audience_accepted(self, client):
        c, priv = client
        tok = _mint_token(priv, aud=f'api://{CLIENT_ID}')
        rv = c.get(
            '/api/protected',
            headers={'Authorization': f'Bearer {tok}'},
        )
        assert rv.status_code == 200

    def test_wrong_audience_rejected(self, client):
        c, priv = client
        tok = _mint_token(priv, aud='some-other-app')
        rv = c.get(
            '/api/protected',
            headers={'Authorization': f'Bearer {tok}'},
        )
        assert rv.status_code == 401
        assert 'audience' in rv.get_json()['error'].lower()

    def test_wrong_issuer_rejected(self, client):
        c, priv = client
        tok = _mint_token(
            priv, iss='https://login.microsoftonline.com/other/v2.0'
        )
        rv = c.get(
            '/api/protected',
            headers={'Authorization': f'Bearer {tok}'},
        )
        assert rv.status_code == 401
        assert 'issuer' in rv.get_json()['error'].lower()

    def test_expired_token_rejected(self, client):
        c, priv = client
        # Past leeway window (default 60s)
        tok = _mint_token(priv, exp_offset=-300)
        rv = c.get(
            '/api/protected',
            headers={'Authorization': f'Bearer {tok}'},
        )
        assert rv.status_code == 401
        assert 'expired' in rv.get_json()['error'].lower()

    def test_fee_calculator_requires_auth(self, client):
        """Fee Calculator API routes MUST be gated by JWT."""
        c, _ = client
        # No token → 401 on fee-calculator endpoints
        rv = c.get('/fee-calculator/api/schedules')
        assert rv.status_code == 401
        assert 'Missing Bearer token' in rv.get_json()['error']

    def test_fee_calculator_valid_token_accepted(self, client):
        """Fee Calculator API works with a valid token."""
        c, priv = client
        tok = _mint_token(priv, aud=CLIENT_ID)
        rv = c.get(
            '/fee-calculator/api/schedules',
            headers={'Authorization': f'Bearer {tok}'},
        )
        assert rv.status_code == 200

    def test_pipeline_review_requires_auth(self, client):
        """Pipeline Review API routes MUST be gated by JWT."""
        c, _ = client
        rv = c.get('/pipeline-review/api/weeks')
        assert rv.status_code == 401
        assert 'Missing Bearer token' in rv.get_json()['error']

    def test_pipeline_review_valid_token_accepted(self, client):
        """Pipeline Review API passes auth with a valid token (DB mocked)."""
        c, priv = client
        tok = _mint_token(priv, aud=CLIENT_ID)
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value = cursor
        with patch('pipeline_review.routes._get_db_connection', return_value=conn):
            rv = c.get(
                '/pipeline-review/api/weeks',
                headers={'Authorization': f'Bearer {tok}'},
            )
        assert rv.status_code == 200
        assert rv.get_json()['success'] is True

    def test_brief_requires_auth(self, client):
        """Executive Brief API routes MUST be gated by JWT."""
        c, _ = client
        for path in ('/brief/api/health', '/brief/api/me', '/brief/api/status'):
            rv = c.get(path)
            assert rv.status_code == 401, path
            assert 'Missing Bearer token' in rv.get_json()['error']

    def test_brief_valid_token_accepted(self, client):
        """Executive Brief API works with a valid token and echoes identity."""
        c, priv = client
        tok = _mint_token(priv, aud=CLIENT_ID)
        rv = c.get('/brief/api/me', headers={'Authorization': f'Bearer {tok}'})
        assert rv.status_code == 200
        assert rv.get_json()['email'] == 'tester@allworthfinancial.com'

    def test_executive_report_requires_auth(self, client):
        """Executive Report API routes MUST be gated by JWT."""
        c, _ = client
        for path in ('/executive-report/api/health', '/executive-report/api/report'):
            rv = c.get(path)
            assert rv.status_code == 401, path
            assert 'Missing Bearer token' in rv.get_json()['error']

    def test_executive_report_valid_token_accepted(self, client):
        """Executive Report health endpoint passes auth with a valid token."""
        c, priv = client
        tok = _mint_token(priv, aud=CLIENT_ID)
        rv = c.get('/executive-report/api/health', headers={'Authorization': f'Bearer {tok}'})
        assert rv.status_code == 200
        assert rv.get_json()['success'] is True

    def test_mailer_send_requires_auth(self, client):
        """Mailer send MUST be JWT-gated — a pipeline needs a valid token."""
        c, _ = client
        rv = c.post('/mailer/api/send', json={'to': 'a@x.com', 'subject': 's', 'body': 'b'})
        assert rv.status_code == 401
        assert 'Missing Bearer token' in rv.get_json()['error']

    def test_mailer_send_valid_token_accepted(self, client, monkeypatch):
        """With a valid token (e.g. a Synapse managed-identity token) the send
        is authorized; the Graph call itself is mocked."""
        c, priv = client
        monkeypatch.setattr('mailer.send_email', lambda *a, **k: None)
        tok = _mint_token(priv, aud=CLIENT_ID)
        rv = c.post('/mailer/api/send',
                    json={'to': 'a@x.com', 'subject': 's', 'body': 'b'},
                    headers={'Authorization': f'Bearer {tok}'})
        assert rv.status_code == 200
        assert rv.get_json()['sent'] is True


class TestAllowlists:
    @pytest.fixture
    def make_client(self, monkeypatch, rsa_keypair):
        priv, pub = rsa_keypair

        def _make(extra_env: dict[str, str]):
            env = {
                'ENTRA_TENANT_ID': TENANT_ID,
                'ENTRA_CLIENT_ID': CLIENT_ID,
                **extra_env,
            }
            mw = _load_middleware(monkeypatch, env, pub)
            app = _build_app(mw)
            return app.test_client(), priv

        return _make

    def test_email_allowlist_allows_match(self, make_client):
        c, priv = make_client(
            {'AUTH_ALLOWED_EMAILS': 'tester@allworthfinancial.com'}
        )
        tok = _mint_token(priv)
        rv = c.get(
            '/api/protected', headers={'Authorization': f'Bearer {tok}'}
        )
        assert rv.status_code == 200

    def test_email_allowlist_denies_nonmatch(self, make_client):
        c, priv = make_client(
            {'AUTH_ALLOWED_EMAILS': 'someone-else@allworthfinancial.com'}
        )
        tok = _mint_token(priv)
        rv = c.get(
            '/api/protected', headers={'Authorization': f'Bearer {tok}'}
        )
        assert rv.status_code == 403
        assert 'allowlist' in rv.get_json()['error'].lower()

    def test_required_role_allows_match(self, make_client):
        c, priv = make_client({'AUTH_REQUIRED_ROLES': 'Reader,Admin'})
        tok = _mint_token(priv, extra_claims={'roles': ['Reader']})
        rv = c.get(
            '/api/protected', headers={'Authorization': f'Bearer {tok}'}
        )
        assert rv.status_code == 200

    def test_required_role_denies_missing(self, make_client):
        c, priv = make_client({'AUTH_REQUIRED_ROLES': 'Admin'})
        tok = _mint_token(priv, extra_claims={'roles': ['Reader']})
        rv = c.get(
            '/api/protected', headers={'Authorization': f'Bearer {tok}'}
        )
        assert rv.status_code == 403
        assert 'role' in rv.get_json()['error'].lower()

    def test_required_group_denies_missing(self, make_client):
        c, priv = make_client({'AUTH_REQUIRED_GROUPS': 'group-guid-1'})
        tok = _mint_token(priv, extra_claims={'groups': ['other-group']})
        rv = c.get(
            '/api/protected', headers={'Authorization': f'Bearer {tok}'}
        )
        assert rv.status_code == 403


class TestStartupSafety:
    def test_auth_required_with_disable_raises(self, monkeypatch, rsa_keypair):
        _, pub = rsa_keypair
        mw = _load_middleware(
            monkeypatch,
            {
                'ENTRA_TENANT_ID': TENANT_ID,
                'ENTRA_CLIENT_ID': CLIENT_ID,
                'AUTH_DISABLE': '1',
                'AUTH_REQUIRED': '1',
            },
            pub,
        )
        with pytest.raises(RuntimeError, match='AUTH_REQUIRED'):
            mw.install(Flask(__name__))

    def test_auth_required_without_config_raises(
        self, monkeypatch, rsa_keypair
    ):
        _, pub = rsa_keypair
        mw = _load_middleware(
            monkeypatch, {'AUTH_REQUIRED': '1'}, pub
        )
        with pytest.raises(RuntimeError, match='AUTH_REQUIRED'):
            mw.install(Flask(__name__))

    def test_disable_bypasses_when_not_required(
        self, monkeypatch, rsa_keypair
    ):
        _, pub = rsa_keypair
        mw = _load_middleware(monkeypatch, {'AUTH_DISABLE': '1'}, pub)
        app = _build_app(mw)
        c = app.test_client()
        # No token, but disabled -> protected route still passes
        assert c.get('/api/protected').status_code == 200

    def test_unconfigured_bypasses_when_not_required(
        self, monkeypatch, rsa_keypair
    ):
        _, pub = rsa_keypair
        mw = _load_middleware(monkeypatch, {}, pub)
        app = _build_app(mw)
        c = app.test_client()
        assert c.get('/api/protected').status_code == 200
