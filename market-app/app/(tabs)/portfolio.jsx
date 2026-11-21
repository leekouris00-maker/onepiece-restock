import React, { useCallback, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData, clean } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, ChangePill, Empty, Panel, SearchBar, Select, T } from '../../src/ui';
import { IconBtn, Screen, Title } from '../../src/screen';
import { OwnedRow, OwnedTile } from '../../src/tiles';
import { useLayout } from '../../src/layout';

const SORTS = [['value', 'Highest value'], ['move', 'Biggest change'], ['name', 'Name'], ['new', 'Newest']];
const SHOW = [['owned', 'Owned'], ['sold', 'Sold']];

export default function Collection() {
  const d = useData(), c = useTheme();
  const [q, setQ] = useState('');
  const [show, setShow] = useState('owned');
  const [grid, setGrid] = useState(false);
  const [sort, setSort] = useState('value');
  const [shut, setShut] = useState({});
  const sold = show === 'sold';
  useFocusEffect(useCallback(() => { if (d.session) d.refresh(); }, [d.session]));
  // tiles fill the panel: about 130px each on a computer, 3–5 across on a phone
  const { inner } = useLayout(), avail = inner - 32, gap = 12;
  const cols = Math.max(3, Math.min(8, Math.floor((avail + gap) / (130 + gap))));
  const tileW = Math.floor((avail - gap * (cols - 1)) / cols);

  const live = d.owned.filter(o => o.status !== 'sold');
  const tot = o => (d.unitAt(o, 0) || 0) * (Number(o.qty) || 1);
  const sumAt = a => live.reduce((n, o) => n + (d.unitAt(o, a) || 0) * (Number(o.qty) || 1), 0);
  const worth = useMemo(() => [sumAt(0), sumAt(7)], [d.owned, d.cat, d.comps, d.sales, d.watch]);
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
    <Screen><Title>Collection</Title><View style={{ gap: 14, marginTop: 10 }}>
      <T mute>{d.configured ? 'Sign in to see everything you own.' : 'Saving isn’t set up in this build yet.'}</T>
      {d.configured ? <Button onPress={() => router.push('/account')}>Sign in</Button> : null}
    </View></Screen>
  );

  return (
    <Screen onRefresh={() => { d.refresh(); d.loadCatalog(true); }} refreshing={d.busy}>
      <Title right={<View style={{ flexDirection: 'row', gap: 8 }}>
        <IconBtn icon="refresh" label="Reload" onPress={() => { d.refresh(); d.loadCatalog(true); }} />
        <IconBtn icon={grid ? 'list' : 'grid-outline'} label={grid ? 'List view' : 'Grid view'} onPress={() => setGrid(!grid)} />
        <IconBtn icon="add" label="Add item" onPress={() => router.push('/item/new')} />
      </View>}>Collection</Title>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 2 }}>
        <T head size={32} style={{ letterSpacing: -1 }}>{d.cat ? d.aud(worth[0]) : '…'}</T>
        <ChangePill now={worth[0]} then={worth[1]} />
      </View>
      <T mute size={13}>{units} items · change over 7 days</T>

      {d.loadError ? <View style={{ marginTop: 14, padding: 14, borderRadius: 14, backgroundColor: 'rgba(255,91,91,0.14)' }}>
        <T w="semi" size={14} style={{ color: c.down }}>Couldn’t load your collection</T>
        <T size={13} mute style={{ marginTop: 2 }}>{d.loadError}</T>
      </View> : null}
      <View style={{ marginTop: 16 }}><SearchBar value={q} onChangeText={setQ} placeholder="Search your collection" /></View>
      <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
        <Select value={sort} onChange={setSort} options={SORTS} label="Sort by" />
        <Select value={show} onChange={setShow} options={SHOW} label="Show" />
      </View>

      {!groups.length ? <Empty>{q ? `Nothing in your collection matches “${q}”.` : sold ? 'Nothing sold yet.' : 'Nothing here yet. Tap + to add something.'}</Empty> : null}
      {groups.map(({ g, items, total }) => {
        const closed = shut[g] && !q;
        return (
          <Panel key={g} style={{ marginTop: 14, gap: closed ? 0 : 6 }}>
            <Pressable onPress={() => setShut(s => ({ ...s, [g]: !s[g] }))} accessibilityRole="button" accessibilityState={{ expanded: !closed }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ flex: 1 }}>
                <T w="bold" size={15.5} numberOfLines={1}>{g}</T>
                <T size={12} mute>{items.length} {items.length === 1 ? 'entry' : 'entries'}</T>
              </View>
              <T w="bold" size={15}>{d.aud(total)}</T>
              <Ionicons name={closed ? 'chevron-down' : 'chevron-up'} size={16} color={c.mute} />
            </Pressable>
            {closed ? null : grid ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap, rowGap: 16, marginTop: 6 }}>
                {items.map(o => <OwnedTile key={o.id} o={o} width={tileW} />)}
              </View>
            ) : items.map(o => <OwnedRow key={o.id} o={o} />)}
          </Panel>
        );
      })}
      <T mute size={12} style={{ marginTop: 22 }}>Values use your own estimate first, then the eBay median for cards you track, then your logged sales, then TCGplayer.</T>
    </Screen>
  );
}
