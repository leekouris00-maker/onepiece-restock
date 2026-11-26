"""Evening streak reminder (streak_reminder.py): who gets one, gone phones removed, dry run, SQL missing."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import streak_reminder as sr


def test_streak_reminder(monkeypatch):
    calls = []
    def fake_sb(method, path, body=None, prefer=None):
        calls.append((method, path))
        if path == 'rpc/streak_reminders': return [{'user_id': 'u1-aaaa', 'streak': 5}, {'user_id': 'u2-bbbb', 'streak': 2}]
        if path.startswith('app_keys'): return [{'name': 'vapid_private', 'value': 'PEM'}]
        if path.startswith('push_subs?select'): return [{'endpoint': 'e1', 'user_id': 'u1-aaaa', 'sub': {}}, {'endpoint': 'e2', 'user_id': 'u2-bbbb', 'sub': {}}, {'endpoint': 'e3', 'user_id': 'u2-bbbb', 'sub': {}}]
        return None
    sent = []
    def fake_send(pem, sub, payload):
        sent.append(payload); return 'gone' if len(sent) == 3 else 'ok'
    monkeypatch.setattr(sr, 'sb', fake_sb); monkeypatch.setattr(sr, 'send', fake_send)
    monkeypatch.setenv('SUPABASE_URL', 'x'); monkeypatch.setenv('SUPABASE_SERVICE_KEY', 'y')
    assert sr.main([]) == 0
    assert len(sent) == 3 and sent[0]['title'] == 'Your 5-day streak ends at midnight', sent
    assert any(m == 'DELETE' and 'e3' in p for m, p in calls), calls
    sent.clear(); calls.clear()
    assert sr.main(['--dry']) == 0 and not sent
    def missing(*a, **k): raise RuntimeError('POST rpc/streak_reminders: 404')
    monkeypatch.setattr(sr, 'sb', missing)
    assert sr.main([]) == 0
