// Trade calculator: what you give vs what you get, at today's prices. Optionally applies the trade to
// your collection (your cards out, theirs in, with Undo).
import React, { useMemo, useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, newId, today, useData } from '../src/data';
import { F, useTheme } from '../src/theme';
import { Button, CardArt, Chip, Panel, SearchBar, T } from '../src/ui';
import { Screen } from '../src/screen';
import { searchCards, versionTag } from '../src/find';
import { usePref } from '../src/prefs';
import { toast } from '../src/toast';
import { haptic } from '../src/haptic';
import { Progress } from '../src/progress';

const EMPTY = { give: [], get: [], pct: 100 };

export default function Trade() {
  const d = useData(), c = useTheme();
  const [t, setT] = usePref('trade', EMPTY);
  const tr = t || EMPTY;
  const [busy, setBusy] = useState(false);
  const each = l => {
    if (l.over != null && l.over !== '') return Number(l.over) || 0;
    const o = l.owned ? d.owned.find(x => x.id === l.owned) : null;
    if (o) return d.unitAt(o, 0) || 0;
    const r = d.refPrice(d.card(l.k)); return r.usd == null ? 0 : r.usd * d.fx;
  };
  const sum = side => tr[side].reduce((n, l) => n + each(l) * l.qty, 0);
  const give = sum('give'), getRaw = sum('get'), get = (getRaw * (tr.pct || 100)) / 100;
  const diff = get - give, big = Math.max(give, get) || 1;
  const upd = (side, f) => setT(x => ({ ...(x || EMPTY), [side]: f((x || EMPTY)[side]) }));

  const apply = async () => {
    setBusy(true);
    try {
      const before = [], changed = [], removed = [], added = [];
      for (const l of tr.give) {
        const o = l.owned ? d.owned.find(x => x.id === l.owned) : d.owned.find(x => x.card === l.k && x.status !== 'sold');
        if (!o) continue;
        before.push({ ...o });
        const q = (Number(o.qty) || 1) - l.qty;
        if (q > 0) changed.push({ ...o, qty: q }); else removed.push(o.id);
      }
      for (const l of tr.get) {
        const x = d.card(l.k); if (!x) continue;
        added.push({ id: newId(), card: x.k, name: clean(x.n), qty: l.qty, kind: x.t === 'sealed' ? 'Sealed' : x.t === 'don' ? 'DON!!' : 'Card', cond: x.t === 'sealed' ? 'Sealed' : 'Raw',
          lang: 'EN', group: 'Trades', paid: Math.round(each(l) * (tr.pct || 100)) / 100, value: null, notes: `Traded ${today()}`, status: 'owned', soldFor: null, added: today() });
      }
      await d.saveMany([...changed, ...added]);
      await d.removeMany(removed);
      haptic('success');
      const saved = tr;
      setT(EMPTY);
      toast(`Trade done: ${before.length} out, ${added.length} in (group Trades)`, { action: { label: 'Undo', onPress: async () => {
        try { await d.removeMany(added.map(a => a.id)); await d.saveMany(before); setT(saved); } catch (e) { toast(e.message); }
      } } });
    } catch (e) { toast(e.message || String(e)); } finally { setBusy(false); }
  };

  return (
    <Screen max={900}>
      <Panel style={{ gap: 10 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <View><T mute size={12.5}>You give</T><T w="bold" size={20}>{d.aud(give)}</T></View>
          <View style={{ alignItems: 'flex-end' }}><T mute size={12.5}>You get{tr.pct !== 100 ? ` (at ${tr.pct}%)` : ''}</T><T w="bold" size={20}>{d.aud(get)}</T></View>
        </View>
        <View style={{ flexDirection: 'row', gap: 4 }}>
          <View style={{ flex: give / big || 0.001 }}><Progress v={1} h={10} /></View>
          <View style={{ flex: get / big || 0.001, height: 10, borderRadius: 5, backgroundColor: '#4fc3f7' }} />
        </View>
        <T w="bold" size={16} style={{ color: !give && !get ? c.mute : Math.abs(diff) < Math.max(give, get) * 0.05 ? c.accent : diff > 0 ? c.up : c.down }}>
          {!give && !get ? 'Add cards to both sides' : Math.abs(diff) < Math.max(give, get) * 0.05 ? `Fair trade (within 5%)` : diff > 0 ? `You get ${d.aud(diff)} more` : `You give ${d.aud(-diff)} more`}
        </T>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
          <T mute size={12.5}>Value their cards at</T>
          {[100, 90, 80, 70].map(p => <Chip key={p} on={(tr.pct || 100) === p} onPress={() => setT({ ...tr, pct: p })} style={{ minHeight: 32 }}>{`${p}%`}</Chip>)}
        </View>
        <T mute size={11.5}>Prices: eBay sold median where there are enough sales, else TCGplayer market; your own value for cards from your collection. Tap a price to change it.</T>
      </Panel>

      <Side title="You give" side="give" lines={tr.give} upd={upd} each={each} mineFirst />
      <Side title="You get" side="get" lines={tr.get} upd={upd} each={each} />

      <View style={{ gap: 10, marginTop: 16 }}>
        {d.session ? <Button disabled={busy || (!tr.give.length && !tr.get.length)} onPress={apply} icon="swap-horizontal">{busy ? 'Saving…' : 'Do this trade in my collection'}</Button> : null}
        <Button ghost onPress={() => setT(EMPTY)}>Clear</Button>
        {d.session ? <T mute size={12}>Doing the trade takes your cards out of your collection and adds theirs to a “Trades” group, with today’s value as the price paid.</T> : null}
      </View>
    </Screen>
  );
}

function Side({ title, side, lines, upd, each, mineFirst }) {
  const d = useData(), c = useTheme();
  const [q, setQ] = useState('');
  const hits = useMemo(() => {
    if (q.trim().length < 2) return [];
    const s = q.trim().toLowerCase();
    const own = mineFirst ? d.owned.filter(o => o.status !== 'sold' && (clean(o.name) + ' ' + (d.card(o.card)?.num || o.num || '')).toLowerCase().includes(s)).slice(0, 4).map(o => ({ o })) : [];
    const cards = searchCards(d.index, q, 6).filter(x => !own.some(y => y.o.card === x.k)).slice(0, 6 - own.length).map(x => ({ x }));
    return [...own, ...cards];
  }, [q, d.index, d.owned]);
  const add = h => {
    upd(side, l => {
      const key = h.o ? 'o:' + h.o.id : h.x.k;
      const i = l.findIndex(y => (y.owned ? 'o:' + y.owned : y.k) === key);
      if (i >= 0) return l.map((y, j) => (j === i ? { ...y, qty: y.qty + 1 } : y));
      return [...l, h.o ? { id: newId(), k: h.o.card, owned: h.o.id, name: clean(h.o.name), qty: 1 } : { id: newId(), k: h.x.k, name: clean(h.x.n), qty: 1 }];
    });
    haptic(); setQ('');
  };
  return (
    <Panel title={title} right={<T w="bold" size={15}>{d.aud(lines.reduce((n, l) => n + each(l) * l.qty, 0))}</T>} style={{ marginTop: 14, gap: 8 }}>
      {lines.map(l => {
        const x = d.card(l.k), o = l.owned ? d.owned.find(y => y.id === l.owned) : null;
        return (
          <View key={l.id} style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 4 }}>
            <Pressable onPress={() => l.k && router.push({ pathname: '/card/[k]', params: { k: l.k } })}>
              <CardArt k={l.k} photo={o ? d.ownPhoto(o) : d.photoOf(l.k)} num={x?.num || o?.num} width={34} />
            </Pressable>
            <View style={{ flex: 1, minWidth: 0, gap: 6 }}>
              <View>
                <T w="semi" size={14} numberOfLines={1}>{l.name}</T>
                <T mute size={12} numberOfLines={1}>{[x?.num, x ? versionTag(d.cat, x) : null, o ? 'from your collection' : null].filter(Boolean).join(' · ')}</T>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <PriceBox value={l.over ?? ''} auto={each({ ...l, over: null })} onChange={v => upd(side, a => a.map(y => (y.id === l.id ? { ...y, over: v === '' ? null : v } : y)))} />
                <T mute size={12}>each</T>
                <View style={{ flex: 1 }} />
                <Step icon="remove" onPress={() => upd(side, a => a.map(y => (y.id === l.id ? { ...y, qty: y.qty - 1 } : y)).filter(y => y.qty > 0))} />
                <T w="bold" size={14} style={{ width: 18, textAlign: 'center' }}>{l.qty}</T>
                <Step icon="add" onPress={() => upd(side, a => a.map(y => (y.id === l.id ? { ...y, qty: y.qty + 1 } : y)))} />
              </View>
            </View>
          </View>
        );
      })}
      <SearchBar value={q} onChangeText={setQ} placeholder={mineFirst ? 'Add from your collection or any card' : 'Add a card: name or number'} />
      {hits.map((h, i) => {
        const x = h.x || d.card(h.o.card);
        return (
          <Pressable key={i} onPress={() => add(h)} accessibilityRole="button" style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 6, borderRadius: 10, backgroundColor: pressed ? c.soft : 'transparent' })}>
            <Ionicons name="add-circle" size={22} color={c.accent} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <T size={13.5} w="semi" numberOfLines={1}>{h.o ? clean(h.o.name) : clean(x.n)}</T>
              <T mute size={12} numberOfLines={1}>{[x?.num || h.o?.num, x ? versionTag(d.cat, x) : null, h.o ? `yours ×${h.o.qty}` : null].filter(Boolean).join(' · ')}</T>
            </View>
            <T size={13} w="semi">{h.o ? d.aud(d.unitAt(h.o, 0)) : d.money(d.refPrice(x).usd)}</T>
          </Pressable>
        );
      })}
    </Panel>
  );
}

function PriceBox({ value, auto, onChange }) {
  const c = useTheme();
  return (
    <View style={{ width: 96, flexDirection: 'row', alignItems: 'center', borderRadius: 10, backgroundColor: c.soft, paddingHorizontal: 6 }}>
      <T mute size={12}>A$</T>
      <TextInput value={String(value)} onChangeText={onChange} placeholder={auto ? auto.toFixed(auto >= 100 ? 0 : 2) : '0'} placeholderTextColor={c.ink} keyboardType="decimal-pad"
        accessibilityLabel="Price each" style={{ flex: 1, minWidth: 0, height: 36, textAlign: 'right', color: c.accent, fontFamily: F.semi, fontSize: 13.5, outlineStyle: 'none' }} />
    </View>
  );
}

function Step({ icon, onPress }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} hitSlop={4} accessibilityRole="button" accessibilityLabel={icon === 'add' ? 'One more' : 'One fewer'}
      style={({ pressed }) => ({ width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed ? c.raise : c.soft })}>
      <Ionicons name={icon} size={16} color={c.ink} />
    </Pressable>
  );
}
