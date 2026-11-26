// Settings (26 Nov 2026): moved out of Profile. Currency, phone notifications, feedback button, owner stats, reset.
import React, { useEffect, useState } from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { PushSection } from '../src/pushui';
import { usePref, resetPrefs, restorePrefs } from '../src/prefs';
import { supabase, useData } from '../src/data';
import { Choice, MenuItem, Section } from '../src/ui';
import { Screen } from '../src/screen';
import { toast } from '../src/toast';

export default function Settings() {
  const d = useData();
  const [fbBtn, setFbBtn] = usePref('fbButton', true);
  const [owner, setOwner] = useState(null);
  useEffect(() => { setOwner(null); if (supabase && d.session) supabase.rpc('am_owner').then(r => setOwner(r.error ? null : r.data), () => {}); }, [d.session]);
  const reset = async () => {
    const before = await resetPrefs();
    toast(before.length ? `Reset ${before.length} saved ${before.length === 1 ? 'setting' : 'settings'} on this device` : 'Nothing to reset',
      before.length ? { action: { label: 'Undo', onPress: () => restorePrefs(before) } } : {});
  };
  return (
    <Screen max={720}><View style={{ gap: 12 }}>
      <Section title="Prices">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Choice label="Currency" value={d.cur} onChange={d.setCur} options={[['AUD', 'A$ Australian'], ['USD', 'US$ American']]} />
        </View>
      </Section>
      <PushSection />
      <Section title="This device">
        <MenuItem icon="eye-outline" label={fbBtn ? 'Hide the feedback button' : 'Show the feedback button'} sub="The small round button in the corner" onPress={() => setFbBtn(!fbBtn)} />
        <MenuItem icon="refresh-circle-outline" label="Reset this device’s settings" sub="Sort orders, views, recent searches, calculator setups. Your collection isn’t touched; Undo for a few seconds." onPress={reset} />
      </Section>
      {owner && (owner.owner || owner.claimable) ? <Section title="Owner">
        <MenuItem icon="stats-chart-outline" label="Owner stats" sub={owner.owner ? 'Sign-ups, who comes back, points owed, swaps to send' : 'No owner yet: open to make this account the owner'} onPress={() => router.push('/stats')} />
      </Section> : null}
    </View></Screen>
  );
}
