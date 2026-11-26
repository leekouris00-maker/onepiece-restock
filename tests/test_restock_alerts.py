"""Restock alerts (restock_alerts.py): matching people get one notification per post, gone phones removed,
nothing sent when the database finds nobody, SQL missing is a notice."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import restock_alerts as ra


def setup(monkeypatch, targets):
    calls, sent = [], []
    posts = [{'id': 'p1-aaaa', 'source': 'sighting', 'title': 'OP-14 booster box', 'price': 179.0, 'store': 'Kmart', 'suburb': 'Box Hill', 'state': 'VIC', 'kind': 'box', 'user_id': 'u0'},
             {'id': 'p2-bbbb', 'source': 'bot', 'title': 'OP-15 booster box', 'price': None, 'store': 'Shop X', 'suburb': None, 'state': 'ONLINE', 'kind': 'box', 'user_id': None}]

    def fake_sb(method, path, body=None, prefer=None):
        calls.append((method, path, body))
        if path.startswith('app_keys'): return [{'name': 'vapid_private', 'value': 'PEM'}]
        if path.startswith('restock_posts'): return posts
        if path == 'rpc/restock_targets': return [{'user_id': u} for u in targets.get(body['pid'], [])]
        if path.startswith('push_subs?select'):
            ids = path.split('in.(')[1].rstrip(')').split(',')
            return [{'endpoint': 'e-' + u, 'user_id': u, 'sub': {}} for u in ids] + ([{'endpoint': 'e-dead', 'user_id': ids[0], 'sub': {}}] if 'u1' in ids else [])
        return None

    def fake_send(pem, sub, payload):
        sent.append(payload)
        return 'gone' if sub is not None and len(sent) == 2 else 'ok'

    monkeypatch.setattr(ra, 'sb', fake_sb)
    monkeypatch.setattr(ra, 'send', fake_send)
    monkeypatch.setenv('SUPABASE_URL', 'x')
    monkeypatch.setenv('SUPABASE_SERVICE_KEY', 'y')
    return calls, sent


def test_sends_to_matching_people(monkeypatch):
    calls, sent = setup(monkeypatch, {'p1-aaaa': ['u1', 'u2'], 'p2-bbbb': []})
    assert ra.main([]) == 0
    assert len(sent) == 3
    assert sent[0]['title'] == 'OP-14 booster box · A$179'
    assert sent[0]['body'] == 'Kmart Box Hill VIC · seen by a collector'
    assert sent[0]['url'].endswith('market?tab=restocks')
    assert any(m == 'DELETE' for m, _, _ in calls)
    assert not any('p2' in str(p) and 'push_subs?select' in p for _, p, _ in calls if p)


def test_online_post_wording():
    m = ra.message({'id': 'x', 'title': 'OP-15 box', 'price': None, 'store': 'Shop X', 'suburb': None, 'state': 'ONLINE', 'source': 'bot'})
    assert m['title'] == 'OP-15 box' and m['body'] == 'Shop X Online · found by our watcher'


def test_dry_marks_nothing(monkeypatch):
    calls, sent = setup(monkeypatch, {'p1-aaaa': ['u1']})
    assert ra.main(['--dry']) == 0
    assert not sent and not any(p == 'rpc/restock_targets' for _, p, _ in calls)


def test_not_set_up(monkeypatch):
    setup(monkeypatch, {})
    def boom(*a, **k): raise RuntimeError('GET restock_posts: 404')
    monkeypatch.setattr(ra, 'sb', boom)
    assert ra.main([]) == 0
