import React, { useMemo, useState } from 'react';
import { ScrollView, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { useData, clean } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, Chip, Empty, RoundAction, SearchBar, T } from '../../src/ui';
import { Screen } from '../../src/screen';
import { OwnedTile } from '../../src/tiles';

const SORTS = [['value', 'Value'], ['move', 'Change'], ['name', 'Name'], ['new', 'Newest']];

export default function Portfolio() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const [q, setQ] = useState('');
  const [group, setGroup] = useState('all');
  const [sort, setSort] = useState('value');
  const pad = 18, gap = 16, cols = width >= 1000 ? 5 : width >= 760 ? 4 : width >= 540 ? 3 : 2;
  const tileW = Math.floor((Math.min(width, 1100) - pad * 2 - gap * (cols - 1)) / cols);

  const live = d.owned.filter(o => o.status !== 'sold');
  const unit = o => d.unitAt(o, 0) || 0, tot = o => unit(o) * (Number(o.qty) || 1);
  const groups = useMemo(() => {
    const m = {}; for (const o of live) { const g = o.group || 'Other'; m[g] = (m[g] || 0) + tot(o); }
    return Object.entries(m).sort((a, b) => b[1] - a[1]).map(g => g[0]);
  }, [d.owned, d.cat, d.comps]);
  const stats = useMemo(() => {
    let worth = 0, paid = 0, units = 0;
    for (const o of live) { const n = Number(o.qty) || 1; units += n; worth += tot(o); if (o.paid != null && o.paid !== '') paid += Number(o.paid) * n; }
    return { worth, paid, units };
  }, [d.owned, d.cat, d.comps, d.sales, d.watch]);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    let l = group === 'sold' ? d.owned.filter(o => o.status === 'sold') : live.filter(o => group === 'all' || (o.group || 'Other') === group);
    if (s) l = l.filter(o => { const k = d.card(o.card); return (clean(o.name) + ' ' + (k?.num || o.num || '') + ' ' + (o.group || '')).toLowerCase().includes(s); });
    const chg = o => { const a = d.unitAt(o, 0), b = d.unitAt(o, 7); return a && b ? (a - b) / b : 0; };
    const by = { value: (a, b) => tot(b) - tot(a), move: (a, b) => Math.abs(chg(b)) - Math.abs(chg(a)), name: (a, b) => clean(a.name).localeCompare(clean(b.name)), new: (a, b) => String(b.added || '').localeCompare(String(a.added || '')) };
    return [...l].sort(by[sort]);
  }, [q, group, sort, d.owned, d.cat, d.comps]);

  if (!d.configured || (d.authReady && !d.session)) return (
    <Screen><View style={{ gap: 14, marginTop: 20 }}>
      <T w="bold" size={28}>Portfolio</T>
      <T mute>{d.configured ? 'Sign in to see everything you own.' : 'Saving isn’t set up in this build yet.'}</T>
      {d.configured ? <Button onPress={() => router.push('/account')} style={{ alignSelf: 'flex-start' }}>Sign in</Button> : null}
    </View></Screen>
  );

  return (
    <Screen onRefresh={() => { d.refresh(); d.loadCatalog(true); }} refreshing={d.busy}>
      <T w="bold" size={28}>Portfolio</T>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginTop: 4 }}>
        <T w="bold" size={22}>{d.cat ? d.aud(stats.worth) : '…'}</T>
        <T mute size={14}>{stats.units} items{stats.paid ? ` · paid ${d.aud(stats.paid)}` : ''}</T>
      </View>

      <View style={{ marginTop: 16 }}>
        <SearchBar value={q} onChangeText={setQ} placeholder="Search your collection" />
      </View>

      <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginTop: 18 }}>
        <RoundAction icon="trending-up" label="Movers" onPress={() => router.push('/movers')} />
        <RoundAction icon="add" label="Add item" onPress={() => router.push('/item/new')} />
        <RoundAction icon="create-outline" label="Add card" onPress={() => router.push('/addcard')} />
        <RoundAction icon="cash-outline" label={group === 'sold' ? 'Owned' : 'Sold'} ring={group === 'sold'} onPress={() => setGroup(group === 'sold' ? 'all' : 'sold')} />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingTop: 20, paddingBottom: 6 }} style={{ marginHorizontal: -pad }}>
        <View style={{ width: pad - 8 }} />
        <Chip on={group === 'all'} onPress={() => setGroup('all')}>Everything</Chip>
        {groups.map(g => <Chip key={g} on={group === g} onPress={() => setGroup(group === g ? 'all' : g)}>{g}</Chip>)}
        <View style={{ width: pad - 8 }} />
      </ScrollView>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <T mute size={13.5}>Sort</T>
        {SORTS.map(([v, l]) => <Chip key={v} on={sort === v} onPress={() => setSort(v)} style={{ minHeight: 30, paddingHorizontal: 12 }}>{l}</Chip>)}
      </View>

      {!list.length ? <Empty>{q ? `Nothing in your collection matches “${q}”.` : 'Nothing here yet. Tap Add item, or open any card and add it.'}</Empty> : null}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap, rowGap: 26, marginTop: 18 }}>
        {list.map(o => <OwnedTile key={o.id} o={o} width={tileW} />)}
      </View>
      <T mute size={12.5} style={{ marginTop: 30 }}>Each item is valued by your own estimate if you set one, otherwise the eBay median for cards you track, then your logged sales, then TCGplayer. Changes are over 7 days.</T>
    </Screen>
  );
}
