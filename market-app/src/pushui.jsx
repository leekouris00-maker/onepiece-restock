// Profile section: turn phone notifications for price alerts on or off
import React, { useEffect, useState } from 'react';
import { View } from 'react-native';
import { useData } from './data';
import { Button, Note, Section, T } from './ui';
import { currentSub, pushState, turnOff, turnOn } from './push';
import { toast } from './toast';
import { haptic } from './haptic';

export function PushSection() {
  const d = useData();
  const [st] = useState(pushState());
  const [on, setOn] = useState(null), [busy, setBusy] = useState(false), [err, setErr] = useState('');
  useEffect(() => { if (st === 'ok') currentSub().then(s => setOn(!!s)); }, [st]);
  if (!d.session) return null;
  const go = async () => {
    setBusy(true); setErr('');
    try {
      if (on) { await turnOff(d); setOn(false); toast('Notifications off'); }
      else { await turnOn(d); setOn(true); haptic('success'); toast('Notifications on'); }
    } catch (e) { setErr(e.message === 'NOT_SET_UP' ? 'One database step first: run supabase/2026-11-24.sql in Supabase.' : e.message || String(e)); }
    finally { setBusy(false); }
  };
  return (
    <Section title="Phone notifications">
      <T mute size={14}>Get a notification when a card on your watchlist passes your alert price. Checked each morning after prices update.</T>
      {st === 'homescreen' ? <Note title="Open the app from your home screen">On iPhone, notifications only work in the home-screen app: in Safari tap Share → Add to Home Screen, open it from there, then come back here.</Note>
        : st === 'denied' ? <Note tone="warn" title="Notifications are blocked">Allow them for this app in your phone’s Settings → Notifications, then come back.</Note>
        : st === 'unsupported' ? <Note>This browser can’t show notifications.</Note>
        : <View style={{ gap: 8 }}>
          <Button ghost={!!on} disabled={busy || on === null} icon={on ? 'notifications-off-outline' : 'notifications-outline'} onPress={go}>{busy ? 'One moment…' : on ? 'Turn notifications off' : 'Turn notifications on'}</Button>
          {on ? <T mute size={12.5}>On for this device. Set alerts on any card’s page (Price alert).</T> : null}
        </View>}
      {err ? <Note tone="warn">{err}</Note> : null}
    </Section>
  );
}
