// Your binders (26 Nov 2026): Collection → Binders. Each binder shows as a cover with its first cards.
import React, { useState } from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, CardArt, Panel, T } from '../src/ui';
import { Screen } from '../src/screen';
import { useWide } from '../src/layout';
import { binderPockets, binderStats, colorOf, useBinders } from '../src/binders';
import { toast } from '../src/toast';

export default function Binders() {
  const d = useData(), c = useTheme(), wide = useWide();
  const b = useBinders();
  useTrack('binders');
  const [busy, setBusy] = useState(false);
  const groups = [...new Set((d.owned || []).filter(o => o.status !== 'sold').map(o => o.group || 'Other'))];
  const make = async init => {
    if (busy) return; setBusy(true);
    try { const x = await b.create(init); router.push({ pathname: '/binder/[id]', params: { id: x.id, edit: init ? '' : '1' } }); }
    catch (e) { toast(e.message || String(e)); } finally { setBusy(false); }
  };
  return (
    <Screen max={900}>
      <T mute size={14} style={{ marginBottom: 12 }}>Your cards page by page, like a real binder. Fill one from a group, a whole set, or pick the cards yourself.</T>
      {b.local && d.session ? <T mute size={12} style={{ marginBottom: 10 }}>Binders are on this device until the binders database update (supabase/2026-11-26-binders.sql) is run.</T> : null}
      {!b.ready ? <T mute>Loading…</T> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 14 }}>
        {b.binders.map(x => {
          const pockets = binderPockets(d, x), st = binderStats(pockets), col = colorOf(x.color);
          const peek = pockets.filter(p => p && p.have).slice(0, 3);
          return (
            <Pressable key={x.id} onPress={() => router.push({ pathname: '/binder/[id]', params: { id: x.id } })} accessibilityRole="button" accessibilityLabel={x.name}
              style={({ pressed }) => ({ width: wide ? 260 : '100%', borderRadius: 18, overflow: 'hidden', backgroundColor: c.panel, opacity: pressed ? 0.8 : 1, borderWidth: 1, borderColor: c.line })}>
              <View style={{ flexDirection: 'row' }}>
                <View style={{ width: 14, backgroundColor: col }} />
                <View style={{ flex: 1, padding: 14, gap: 10 }}>
                  <View style={{ flexDirection: 'row', gap: 6 }}>
                    {peek.length ? peek.map(p => <CardArt key={p.key} k={p.card?.k || p.own?.card} photo={p.own ? d.ownPhoto(p.own) : null} num={p.num} width={52} />)
                      : <View style={{ height: 72, justifyContent: 'center' }}><Ionicons name="book-outline" size={30} color={col} /></View>}
                  </View>
                  <View>
                    <T w="bold" size={16.5} numberOfLines={1}>{x.name}</T>
                    <T mute size={12.5}>{x.source?.kind === 'set' ? `${st.have} of ${st.total} cards` : `${st.total} ${st.total === 1 ? 'card' : 'cards'}`}{st.value ? ` · ${d.aud(st.value)}` : ''}</T>
                  </View>
                </View>
              </View>
            </Pressable>
          );
        })}
      </View>
      <Panel style={{ marginTop: 16 }} title="New binder">
        <Button icon="add" disabled={busy} onPress={() => make()}>Start an empty binder</Button>
        {groups.length ? <View style={{ gap: 6 }}>
          <T mute size={12.5}>Or make one from a collection group</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
            {groups.slice(0, 8).map(g => (
              <Pressable key={g} onPress={() => make({ name: g, source: { kind: 'group', group: g } })} style={{ paddingHorizontal: 14, minHeight: 38, justifyContent: 'center', borderRadius: 999, backgroundColor: c.soft }}>
                <T size={13.5}>{g}</T>
              </Pressable>
            ))}
          </View>
        </View> : null}
        <T mute size={12}>Set binders (every card in a set, missing ones faded) are made from a new binder’s Customise sheet.</T>
      </Panel>
    </Screen>
  );
}
