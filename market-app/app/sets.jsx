// Every set you've started, with how close you are to finishing it
import React, { useMemo } from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { Chip, Empty, Panel, T } from '../src/ui';
import { Screen } from '../src/screen';
import { setProgress, startedSets } from '../src/sets';
import { usePref } from '../src/prefs';
import { Progress } from '../src/progress';

export default function Sets() {
  useTrack('sets');
  const d = useData(), c = useTheme();
  const [master, setMaster] = usePref('masterSet', false);
  const list = useMemo(() => (d.cat ? startedSets(d).map(s => ({ s, p: setProgress(d, s.id, master) })).filter(x => x.p.total)
    .sort((a, b) => b.p.have / b.p.total - a.p.have / a.p.total) : []), [d.cat, d.owned, master]);
  return (
    <Screen max={820}>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <Chip on={!master} onPress={() => setMaster(false)}>Each card once</Chip>
        <Chip on={!!master} onPress={() => setMaster(true)}>Every version</Chip>
      </View>
      <T mute size={12.5} style={{ marginTop: 8 }}>{master ? 'Master set: every alt art, SP and manga counts separately.' : 'Each card number counts once, whichever version you have.'} Tap a set to see what’s missing.</T>
      {!list.length ? <Empty>{d.cat ? 'Add some cards to your collection and your sets show up here.' : 'Loading…'}</Empty> : <Panel style={{ marginTop: 14, gap: 4 }}>
        {list.map(({ s, p }) => (
          <Pressable key={s.id} onPress={() => router.push({ pathname: '/set/[id]', params: { id: s.id } })} accessibilityRole="button"
            style={({ pressed }) => ({ paddingVertical: 10, gap: 6, opacity: pressed ? 0.6 : 1 })}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ width: 54, height: 30, borderRadius: 8, backgroundColor: c.soft, alignItems: 'center', justifyContent: 'center' }}>
                <T w="bold" size={11} style={{ color: c.accent }} numberOfLines={1}>{s.code}</T>
              </View>
              <T w="semi" size={14.5} style={{ flex: 1 }} numberOfLines={1}>{s.name}</T>
              <T w="bold" size={14}>{p.have}/{p.total}</T>
            </View>
            <Progress v={p.have / p.total} />
            <T mute size={12}>{p.missing.length ? `${p.missing.length} missing · about ${d.money(p.cost)} to finish` : 'Complete!'}</T>
          </Pressable>
        ))}
      </Panel>}
    </Screen>
  );
}
