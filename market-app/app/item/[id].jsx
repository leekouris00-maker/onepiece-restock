import React, { useState } from 'react';
import { ScrollView, View, useWindowDimensions } from 'react-native';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { clean, newId, today, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { pickPhoto } from '../../src/photo';
import { Button, CardArt, Chip, Choice, Empty, Field, T } from '../../src/ui';

const num = v => (v === '' || v == null ? null : Number(String(v).replace(',', '.')));

export default function ItemScreen() {
  const { id, card: cardKey, lang: langParam } = useLocalSearchParams();
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const existing = id !== 'new' ? d.owned.find(o => o.id === id) : null;
  const card = d.card(existing?.card || cardKey);
  const groups = [...new Set(d.owned.map(o => o.group || 'Other'))];
  const [f, setF] = useState(() => {
    const o = existing || {};
    return {
      name: o.name || (card ? clean(card.n) : ''), qty: String(o.qty || 1),
      kind: o.kind || (card ? (card.t === 'sealed' ? 'Sealed' : card.t === 'don' ? 'DON!!' : 'Card') : 'Sealed'),
      cond: o.cond || (card && card.t !== 'sealed' ? 'Raw' : 'Sealed'), lang: o.lang || langParam || card?.lang || 'EN', group: o.group || '',
      paid: o.paid ?? '', value: o.value ?? '', notes: o.notes || '', status: o.status || 'owned', soldFor: o.soldFor ?? '',
    };
  });
  const [msg, setMsg] = useState(''); const [confirm, setConfirm] = useState(false);
  if (id !== 'new' && !existing) return <Empty>{d.busy ? 'Loading…' : 'This item isn’t in your collection any more.'}</Empty>;
  const set = (k, v) => setF(x => ({ ...x, [k]: String(v) }));
  const draft = { ...(existing || {}), card: card?.k || null, value: num(f.value), lang: f.lang };
  const v = d.ownVal(draft), photo = existing ? d.ownPhoto(existing) : card ? d.photoOf(card.k) : null, artW = Math.min(150, width * 0.32);
  const run = async (fn, ok) => { try { setMsg(''); await fn(); if (ok) setMsg(ok); } catch (e) { setMsg(e.message || String(e)); } };
  const save = () => run(async () => {
    if (!f.name.trim()) throw new Error('Give it a name');
    await d.saveOwned({ ...(existing || {}), id: existing?.id || newId(), card: card?.k || existing?.card || null, name: f.name.trim(), qty: Math.max(1, parseInt(f.qty, 10) || 1),
      kind: f.kind, cond: f.cond, lang: f.lang, group: f.group.trim() || 'Other', paid: num(f.paid), value: num(f.value), notes: f.notes.trim(),
      status: f.status, soldFor: num(f.soldFor), added: existing?.added || today() });
    router.back();
  });
  return (
    <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 60, maxWidth: 820, width: '100%', alignSelf: 'center', gap: 14 }} keyboardShouldPersistTaps="handled">
      <Stack.Screen options={{ title: existing ? 'Edit item' : 'Add to collection' }} />
      <View style={{ flexDirection: 'row', gap: 18 }}>
        <View style={{ gap: 8, width: artW }}>
          <CardArt k={card?.k} photo={photo} num={card?.num || existing?.num || (f.kind === 'Sealed' ? 'Sealed' : '')} width={artW} big />
          {existing || card ? <Chip onPress={() => pickPhoto(uri => run(() => d.addPhoto(card ? { card: card.k } : { owned: existing.id }, uri), 'Photo saved'))}>{photo ? 'Change photo' : 'Add photo'}</Chip>
            : <T mute size={12.5}>Save first, then add a photo</T>}
        </View>
        <View style={{ flex: 1, gap: 6 }}>
          <T mute size={13}>{existing ? 'In your collection' : 'Add to my collection'}</T>
          <T serif size={f.name.length > 38 ? 20 : 25} style={{ lineHeight: f.name.length > 38 ? 24 : 29 }}>{f.name || 'New item'}</T>
          <T size={13.5} mute>Worth <T w="semi" size={13.5}>{d.aud(v.a)}</T> each · {v.src}</T>
          {card ? <Chip onPress={() => router.push({ pathname: '/card/[k]', params: { k: card.k } })} style={{ alignSelf: 'flex-start' }}>Card prices</Chip> : null}
        </View>
      </View>
      {msg ? <T size={14} style={{ color: c.down }}>{msg}</T> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <Field label="Name" value={f.name} onChangeText={x => set('name', x)} style={{ flexBasis: '100%' }} />
        <Field label="Quantity" value={f.qty} onChangeText={x => set('qty', x)} keyboardType="number-pad" />
        <Field label="Group" value={f.group} onChangeText={x => set('group', x)} placeholder="Binder, Sabo deck…" />
        {groups.length ? <Choice label="Your groups" value={f.group} onChange={x => set('group', x)} options={groups} /> : null}
        <Choice label="Kind" value={f.kind} onChange={x => set('kind', x)} options={['Card', 'Promo', 'DON!!', 'Sealed', 'Other']} />
        <Choice label="Condition" value={f.cond} onChange={x => set('cond', x)} options={['Raw', 'Sealed', 'PSA 10', 'PSA 9', 'Other graded', 'Opened']} />
        <Choice label="Language" value={f.lang} onChange={x => set('lang', x)} options={['EN', 'JP', 'CN', 'KR']} />
        <Field label="Paid each (A$)" value={String(f.paid)} onChangeText={x => set('paid', x)} keyboardType="decimal-pad" />
        <Field label="Your value each (A$)" value={String(f.value)} onChangeText={x => set('value', x)} keyboardType="decimal-pad" placeholder={card ? 'blank = automatic' : 'needed for a value'} />
        <Field label="Notes" value={f.notes} onChangeText={x => set('notes', x)} style={{ flexBasis: '100%' }} multiline />
        <Choice label="Status" value={f.status} onChange={x => set('status', x)} options={[['owned', 'Own it'], ['sold', 'Sold']]} />
        {f.status === 'sold' ? <Field label="Sold for each (A$)" value={String(f.soldFor)} onChangeText={x => set('soldFor', x)} keyboardType="decimal-pad" /> : null}
      </View>
      <Button onPress={save}>{existing ? 'Save' : 'Add to my collection'}</Button>
      {existing ? <Button ghost danger={confirm} onPress={() => (confirm ? run(async () => { await d.removeOwned(existing.id); router.back(); }) : setConfirm(true))}>{confirm ? 'Tap again to remove' : 'Remove from collection'}</Button> : null}
    </ScrollView>
  );
}
