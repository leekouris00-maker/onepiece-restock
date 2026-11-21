import React, { useMemo, useState } from 'react';
import { Pressable, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData, clean } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Bounty, Button, Chip, Empty, SearchBar, T } from '../../src/ui';
import { Screen, Title } from '../../src/screen';
import { OwnedRow, OwnedTile } from '../../src/tiles';

const SORTS = [['value', 'Value'], ['move', 'Change'], ['name', 'Name'], ['new', 'Newest']];

export default function Collection() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const [q, setQ] = useState('');
  const [sold, setSold] = useState(false);
  const [grid, setGrid] = useState(false);
  const [sort, setSort] = useState('value');
  const [shut, setShut] = useState({});
  const pad = 18, gap = 14, cols = width >= 1000 ? 6 : width >= 760 ? 5 : width >= 540 ? 4 : 3;

  const live = d.owned.filter(o => o.status !== 'sold');
  const tot = o => (d.unitAt(o, 0) || 0) * (Number(o.qty) || 1);
  const worth = useMemo(() => live.reduce((n, o) => n + tot(o), 0), [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const units = live.reduce((n, o) => n + (Number(o.qty) || 1), 0);

  const groups = useMemo(() => {
    const s = q.trim().toLowerCase();
    let l = sold ? d.owned.filter(o => o.status === 'sold') : live;
    if (s) l = l.filter(o => { const k = d.card(o.card); return (clean(o.name) + ' ' + (k?.num || o.num || '') + ' ' + (o.group || '')).toLowerCase().includes(s); });
    const chg = o => { const a = d.unitAt(o, 0), b = d.unitAt(o, 7); return a && b ? (a - b) / b : 0; };
    const by = { value: (a, b) => tot(b) - tot(a), move: (a, b) => Math.abs(chg(b)) - Math.abs(chg(a)), name: (a, b) => clean(a.name).localeCompare(clean(b.name)), new: (a, b) => String(b.added || '').localeCompare(String(a.added || '')) };
    const m = {}; for (const o of l) (m[sold ? 'Sold' : o.group || 'Other'] ??= []).push(o);
    return Object.entries(m).map(([g, items]) => ({ g, items: items.sort(by[sort]), total: items.reduce((n, o) => n + (sold ? (Number(o.soldFor) || 0) * (Number(o.qty) || 1) : tot(o)), 0) }))
      .sort((a, b) => b.total - a.total);
  }, [q, sold, sort, d.owned, d.cat, d.comps]);

  if (!d.configured || (d.authReady && !d.session)) return (
    <Screen><Title>Collection</Title><View style={{ gap: 14, marginTop: 16 }}>
      <T mute>{d.configured ? 'Sign in to see everything you own.' : 'Saving isn’t set up in this build yet.'}</T>
      {d.configured ? <Button onPress={() => router.push('/account')} style={{ alignSelf: 'flex-start' }}>Sign in</Button> : null}
    </View></Screen>
  );

  const Toggle = ({ icon, on, onPress, label }) => (
    <Pressable onPress={onPress} accessibilityLabel={label} accessibilityState={{ selected: on }} hitSlop={6}
      style={{ width: 40, height: 36, borderRadius: 6, alignItems: 'center', justifyContent: 'center', backgroundColor: on ? c.accent : 'transparent', borderWidth: 1, borderColor: on ? c.accent : c.line }}>
      <Ionicons name={icon} size={18} color={on ? c.bg : c.ink} />
    </Pressable>
  );

  return (
    <Screen onRefresh={() => { d.refresh(); d.loadCatalog(true); }} refreshing={d.busy}>
      <Title sub={`${units} items in ${groups.length} ${groups.length === 1 ? 'group' : 'groups'}`}
        right={<Bounty size={20}>{d.cat ? d.aud(worth) : '…'}</Bounty>}>Collection</Title>

      <View style={{ marginTop: 12 }}>
        <SearchBar value={q} onChangeText={setQ} placeholder="Search your collection"
          right={<Pressable onPress={() => router.push('/item/new')} accessibilityLabel="Add item"
            style={{ width: 50, height: 50, borderRadius: 10, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="add" size={28} color={c.bg} /></Pressable>} />
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 14, flexWrap: 'wrap' }}>
        {SORTS.map(([v, l]) => <Chip key={v} on={sort === v} onPress={() => setSort(v)} style={{ minHeight: 32, paddingHorizontal: 11 }}>{l}</Chip>)}
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 }}>
        <Pressable onPress={() => setSold(!sold)} hitSlop={6} style={{ flex: 1 }} accessibilityRole="button">
          <T size={13.5} style={{ color: c.accent }}>{sold ? '‹ Back to what you own' : 'Show what you’ve sold ›'}</T>
        </Pressable>
        <Toggle icon="list" on={!grid} onPress={() => setGrid(false)} label="List view" />
        <Toggle icon="grid" on={grid} onPress={() => setGrid(true)} label="Grid view" />
      </View>

      {!groups.length ? <Empty>{q ? `Nothing in your collection matches “${q}”.` : sold ? 'Nothing sold yet.' : 'Nothing here yet. Tap + to add something, or open any card and add it.'}</Empty> : null}
      {groups.map(({ g, items, total }) => {
        const closed = shut[g] && !q;
        return (
          <View key={g} style={{ marginTop: 18, borderRadius: 12, borderWidth: 1, borderColor: c.line, backgroundColor: c.panel, overflow: 'hidden' }}>
            <Pressable onPress={() => setShut(s => ({ ...s, [g]: !s[g] }))} accessibilityRole="button" accessibilityState={{ expanded: !closed }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, backgroundColor: c.soft, borderLeftWidth: 3, borderLeftColor: c.accent }}>
              <View style={{ flex: 1 }}>
                <T head caps size={16} numberOfLines={1} style={{ letterSpacing: 1 }}>{g}</T>
                <T size={12} mute>{items.length} {items.length === 1 ? 'entry' : 'entries'}</T>
              </View>
              <T head size={17} style={{ color: c.accent }}>{d.aud(total)}</T>
              <Ionicons name={closed ? 'chevron-down' : 'chevron-up'} size={18} color={c.mute} />
            </Pressable>
            {closed ? null : grid ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap, rowGap: 18, padding: 12 }}>
                {items.map(o => <OwnedTile key={o.id} o={o} width={Math.floor((Math.min(width, 1100) - pad * 2 - 26 - gap * (cols - 1)) / cols)} />)}
              </View>
            ) : (
              <View style={{ paddingHorizontal: 12 }}>
                {items.map((o, i) => <OwnedRow key={o.id} o={o} last={i === items.length - 1} />)}
              </View>
            )}
          </View>
        );
      })}
      <T mute size={12} style={{ marginTop: 24 }}>Each item is valued by your own estimate if you set one, otherwise the eBay median for cards you track, then your logged sales, then TCGplayer. Changes are over 7 days. Tap a group to fold it.</T>
    </Screen>
  );
}
