"""Tests for the Executive Brief blueprint (auth disabled — gating is covered
in test_auth_middleware.py).

Run from the backend/ directory:

    python -m pytest tests/test_brief.py -v
"""
from __future__ import annotations

import pytest
from flask import Flask

from brief.routes import bp as brief_bp


@pytest.fixture
def client():
    app = Flask(__name__)
    app.testing = True
    app.register_blueprint(brief_bp, url_prefix='/brief')
    return app.test_client()


def test_health(client):
    rv = client.get('/brief/api/health')
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['success'] is True
    assert body['tool'] == 'brief'


def test_me_without_identity(client):
    rv = client.get('/brief/api/me')
    assert rv.status_code == 200
    assert rv.get_json()['email'] is None


def test_me_with_identity(client):
    # The auth middleware stashes the identity in request.environ; simulate it.
    rv = client.get(
        '/brief/api/me',
        environ_overrides={'user.email': 'ceo@allworthfinancial.com'},
    )
    assert rv.status_code == 200
    assert rv.get_json()['email'] == 'ceo@allworthfinancial.com'


def test_status_reports_mock_mode(client):
    rv = client.get('/brief/api/status')
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['success'] is True
    assert body['mode'] == 'mock'
    assert body['mock_mode'] is True
    assert body['graph_token_available'] is False


def test_status_detects_graph_token(client):
    rv = client.get(
        '/brief/api/status',
        headers={'X-MS-TOKEN-AAD-ACCESS-TOKEN': 'dummy-token'},
    )
    assert rv.get_json()['graph_token_available'] is True


def test_status_mock_when_flag_off_even_with_token(client):
    # Token present but USE_LIVE_MAIL not set → still mock (flag-gated).
    rv = client.get(
        '/brief/api/status',
        headers={'X-MS-TOKEN-AAD-ACCESS-TOKEN': 'dummy-token'},
    )
    assert rv.get_json()['mode'] == 'mock'


def test_messages_mock_mode_returns_empty_live_set(client):
    # In mock mode /messages yields no live emails; the frontend uses bundled data.
    rv = client.get('/brief/api/messages')
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['mode'] == 'mock'
    assert body['emails'] == []


def test_detail_requires_live_mode(client):
    rv = client.get('/brief/api/messages/whatever')
    assert rv.status_code == 409


def test_analyze_requires_live_mode(client):
    rv = client.post('/brief/api/analyze', json={'id': 'x'})
    assert rv.status_code == 409


def test_save_draft_mock_mode_is_local(client):
    rv = client.post('/brief/api/save-draft', json={'id': 'x', 'text': 'hi'})
    assert rv.status_code == 200
    assert rv.get_json()['saved'] == 'local'


def test_live_messages_triages_via_graph(client, monkeypatch):
    """With the flag on + a token, /messages reads Graph and triages."""
    monkeypatch.setenv('USE_LIVE_MAIL', '1')
    from brief import graph, analyze

    fake_inbox = [{
        'id': 'm1', 'threadId': 'c1', 'senderName': 'Sarah Lee',
        'senderEmail': 's@x.com', 'subject': 'Approve plan',
        'receivedAt': '2026-07-22T10:00:00Z', 'bodyPreview': 'please approve',
        'attachmentCount': 1, 'unread': True, 'importance': 'high',
    }]
    monkeypatch.setattr(graph, 'get_inbox_messages', lambda token, top=50: fake_inbox)
    monkeypatch.setattr(analyze, 'triage_messages', lambda msgs: {
        'm1': {'category': 'needs_decision', 'priority': 'high',
               'summary': 'Approve the plan', 'request': 'Approve by Fri',
               'recommended_action': 'Review then approve', 'confidence': 0.9},
    })

    rv = client.get('/brief/api/messages', headers={'X-MS-TOKEN-AAD-ACCESS-TOKEN': 'tok'})
    assert rv.status_code == 200
    body = rv.get_json()
    assert body['mode'] == 'live'
    assert len(body['emails']) == 1
    e = body['emails'][0]
    assert e['category'] == 'needs_decision'
    assert e['priority'] == 'high'
    assert e['recommendedAction'] == 'Review then approve'
    assert e['completed'] is False


def test_live_messages_defaults_when_triage_empty(client, monkeypatch):
    """Graph works but Claude triage is unavailable → neutral defaults, never a crash."""
    monkeypatch.setenv('USE_LIVE_MAIL', '1')
    from brief import graph, analyze

    monkeypatch.setattr(graph, 'get_inbox_messages', lambda token, top=50: [{
        'id': 'm2', 'threadId': 'c2', 'senderName': 'X', 'senderEmail': 'x@x.com',
        'subject': 'Hi', 'receivedAt': '2026-07-22T10:00:00Z',
        'bodyPreview': 'fallback body', 'attachmentCount': 0, 'unread': False,
        'importance': 'normal',
    }])
    monkeypatch.setattr(analyze, 'triage_messages', lambda msgs: {})

    rv = client.get('/brief/api/messages', headers={'X-MS-TOKEN-AAD-ACCESS-TOKEN': 'tok'})
    body = rv.get_json()
    assert body['mode'] == 'live'
    assert body['emails'][0]['summary'] == 'fallback body'
    assert body['emails'][0]['category'] == 'needs_response'


def test_send_reply_requires_live_mode(client):
    rv = client.post('/brief/api/send-reply', json={'id': 'x', 'text': 'hi'})
    assert rv.status_code == 409


def test_send_reply_requires_text(client, monkeypatch):
    monkeypatch.setenv('USE_LIVE_MAIL', '1')
    rv = client.post('/brief/api/send-reply', json={'id': 'x', 'text': '   '},
                     headers={'X-MS-TOKEN-AAD-ACCESS-TOKEN': 'tok'})
    assert rv.status_code == 400


def test_send_reply_calls_graph_and_reports_sent(client, monkeypatch):
    monkeypatch.setenv('USE_LIVE_MAIL', '1')
    from brief import graph

    sent = {}

    def fake_send(token, message_id, text):
        sent['id'] = message_id
        sent['text'] = text

    monkeypatch.setattr(graph, 'send_reply', fake_send)
    rv = client.post('/brief/api/send-reply', json={'id': 'm9', 'text': 'Approved.'},
                     headers={'X-MS-TOKEN-AAD-ACCESS-TOKEN': 'tok'})
    assert rv.status_code == 200
    assert rv.get_json()['sent'] is True
    assert sent == {'id': 'm9', 'text': 'Approved.'}


def test_send_reply_surfaces_scope_error(client, monkeypatch):
    monkeypatch.setenv('USE_LIVE_MAIL', '1')
    from brief import graph

    def fake_send(token, message_id, text):
        raise graph.GraphError('Send denied (403) — Mail.Send scope not granted', 403)

    monkeypatch.setattr(graph, 'send_reply', fake_send)
    rv = client.post('/brief/api/send-reply', json={'id': 'm9', 'text': 'hi'},
                     headers={'X-MS-TOKEN-AAD-ACCESS-TOKEN': 'tok'})
    assert rv.status_code == 403
    assert 'Mail.Send' in rv.get_json()['error']


def test_triage_chunks_and_merges_batches(monkeypatch):
    """triage_messages splits >1 batch and merges every batch's result, so a
    large inbox is fully classified rather than truncated into defaults."""
    from brief import analyze

    monkeypatch.setattr(analyze, '_client', lambda: object())
    monkeypatch.setattr(analyze, '_TRIAGE_BATCH', 12)
    # Record batch sizes and return a classification per id in each batch.
    seen_batches = []

    def fake_batch(client, batch):
        seen_batches.append(len(batch))
        return {m['id']: {'category': 'important', 'priority': 'low',
                          'summary': 's', 'request': 'r',
                          'recommended_action': 'a', 'confidence': 0.5}
                for m in batch}

    monkeypatch.setattr(analyze, '_triage_batch', fake_batch)
    msgs = [{'id': f'm{i}', 'subject': 's', 'senderName': 'n', 'bodyPreview': 'b'}
            for i in range(30)]
    out = analyze.triage_messages(msgs)
    assert len(out) == 30                      # every message classified
    assert sorted(seen_batches) == [6, 12, 12]  # 30 → 12 + 12 + 6
    assert out['m17']['category'] == 'important'
