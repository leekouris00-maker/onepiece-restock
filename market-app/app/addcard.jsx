import React, { useState } from 'react';
import { ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { useData } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, Choice, Field, T } from '../src/ui';

export default function AddCard() {
  const d = useData(), c = useTheme();
  const sets = [...new Set(d.custom.map(x => x.setName))];
  const [f, setF] = useState({ lang: 'JP', num: '', name: '', set: '', rar: '', note: '' });
  const [msg, setMsg] = useState('');
  const set = (k, v) => setF(x => ({ ...x, [k]: v }));
  return (
    <ScrollView contentContainerStyle={{ padding: 20, gap: 14, maxWidth: 820, width: '100%', alignSelf: 'center' }} keyboardShouldPersistTaps="handled">
      <T mute>For Japanese cards and promos TCGplayer doesn’t list. Give it the set it belongs to and it shows up under My cards in Market.</T>
      {msg ? <T style={{ color: c.red }}>{msg}</T> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <Choice label="Language" value={f.lang} onChange={v => set('lang', v)} options={['JP', 'EN', 'CN']} />
        <Field label="Card number" value={f.num} onChangeText={v => set('num', v)} placeholder="P-069" autoCapitalize="characters" />
        <Field label="Rarity" value={f.rar} onChangeText={v => set('rar', v)} placeholder="P" />
        <Field label="Name and version" value={f.name} onChangeText={v => set('name', v)} placeholder="Monkey.D.Luffy (ONE PIECE DAY '24)" style={{ flexBasis: '100%' }} />
        <Field label="Set or release" value={f.set} onChangeText={v => set('set', v)} placeholder="Japanese promos" style={{ flexBasis: '100%' }} />
        {sets.length ? <Choice label="Your sets" value={f.set} onChange={v => set('set', v)} options={sets} /> : null}
        <Field label="Note" value={f.note} onChangeText={v => set('note', v)} placeholder="Where it came from, print run…" style={{ flexBasis: '100%' }} />
      </View>
      <Button onPress={async () => {
        try {
          if (!f.name.trim() || !f.set.trim()) throw new Error('Give it a name and a set');
          const card = await d.addCard({ ...f, num: f.num.trim().toUpperCase(), name: f.name.trim(), set: f.set.trim() });
          router.replace({ pathname: '/card/[k]', params: { k: 'u:' + card.id } });
        } catch (e) { setMsg(e.message || String(e)); }
      }}>Save card</Button>
    </ScrollView>
  );
}
