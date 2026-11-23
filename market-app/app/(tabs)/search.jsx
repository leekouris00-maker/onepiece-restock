import React, { useDeferredValue, useEffect, useMemo, useRef, useState } from 'react';
import { FlatList, Pressable, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { searchCards } from '../../src/find';
import { usePref } from '../../src/prefs';
import { on } from '../../src/bus';
import { useTheme } from '../../src/theme';
import { KINDS, useData } from '../../src/data';
import { CardRow, SetRow } from '../../src/rows';
import { Chip, Empty, SearchBar, SkelRows, T } from '../../src/ui';
import { BAR_SPACE, ChipRow, IconBtn, Title, useTop } from '../../src/screen';
import { router } from 'expo-router';
import { useWide } from '../../src/layout';

const ORDER = ['all', 'booster', 'extra', 'premium', 'starter', 'promo', 'event', 'pre-release', 'other', 'mine'];

export default function Search() {
  const d = useData(), top = useTop(), wide = useWide(), px = wide ? 32 : 18;
  const c = useTheme();
  const [q, setQ] = useState('');
  const [kind, setKind] = useState('all');
  const [recent, setRecent] = usePref('recentSearches', []);
  const input = useRef(null);
  useEffect(() => on('focus-search', () => input.current && input.current.focus()), []);
  const remember = () => { const t = q.trim(); if (t.length >= 2) setRecent(r => [t, ...(r || []).filter(x => x.toLowerCase() !== t.toLowerCase())].slice(0, 8)); };
  const dq = useDeferredValue(q);
  const s = dq.trim().toLowerCase().replace(/\s+/g, ' ');
  const searching = s.length >= 2;
  const kindOf = x => (x.mine ? 'mine' : d.cat?.byId[x.g]?.kind || 'other');

  // every match across all sets; the chips then narrow it to one kind of set
  const matches = useMemo(() => {
    if (!searching || !d.cat) return [];
    return searchCards(d.index, s, 1000);
  }, [s, searching, d.index]);

  const allSets = useMemo(() => {
    if (!d.cat) return [];
    const mine = [...new Set(d.custom.map(x => x.setName || 'Other'))].sort().map(n => ({ id: 'mine:' + n, code: '★', name: n, kind: 'mine' }));
    return [...d.cat.sets].sort((a, b) => String(b.date || '').localeCompare(String(a.date || ''))).concat(mine);
  }, [d.cat, d.custom]);

  const counts = useMemo(() => {
    const n = { all: searching ? matches.length : allSets.length };
    for (const x of searching ? matches : allSets) { const k = searching ? kindOf(x) : x.kind; n[k] = (n[k] || 0) + 1; }
    return n;
  }, [searching, matches, allSets]);

  const chips = useMemo(() => {
    const names = Object.fromEntries([['all', searching ? 'All sets' : 'All'], ...KINDS, ['mine', 'My cards']]);
    return ORDER.filter(v => v === 'all' || v === kind || (allSets.some(x => x.kind === v) && (!searching || counts[v]))).map(v => [v, names[v] || v]);
  }, [allSets, searching, counts, kind]);

  const results = searching ? (kind === 'all' ? matches : matches.filter(x => kindOf(x) === kind)).slice(0, 300) : [];
  const sets = searching ? [] : kind === 'all' ? allSets : allSets.filter(x => x.kind === kind);
  const label = (chips.find(([v]) => v === kind) || [, ''])[1];

  return (
    <FlatList key={wide ? 'wide' : 'phone'} numColumns={wide ? 2 : 1} columnWrapperStyle={wide ? { paddingHorizontal: 14, gap: 12 } : undefined}
      data={searching ? results : sets} keyExtractor={x => (searching ? x.k : 'set:' + x.id)} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"
      style={{ width: '100%', maxWidth: wide ? 1100 : 900, alignSelf: 'center' }}
      ListHeaderComponent={<View style={{ paddingTop: top, paddingBottom: 6, gap: 10 }}>
        <View style={{ paddingHorizontal: px, gap: 10 }}>
          <Title>Search</Title>
          <SearchBar value={q} onChangeText={setQ} placeholder="Sabo, op13 120, chopper re, luffy alt…" inputRef={input} onSubmitEditing={remember}
            right={<IconBtn icon="scan" label="Scan a card" onPress={() => router.push('/scan')} />} />
          {!q && recent && recent.length ? <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <Ionicons name="time-outline" size={16} color={c.mute} />
            {recent.map(r => <Chip key={r} onPress={() => setQ(r)} style={{ minHeight: 34 }}>{r}</Chip>)}
            <Pressable onPress={() => setRecent([])} hitSlop={8}><T size={12.5} mute>Clear</T></Pressable>
          </View> : null}
        </View>
        {d.cat ? <ChipRow pad={px}>
          {chips.map(([v, l]) => <Chip key={v} on={kind === v} onPress={() => setKind(v)}>{`${l} ${counts[v] || 0}`}</Chip>)}
        </ChipRow> : null}
        <T mute size={13} style={{ paddingHorizontal: px }}>
          {searching
            ? `${results.length >= 300 ? 'First 300' : results.length} ${results.length === 1 ? 'match' : 'matches'}${kind === 'all' ? '' : ' in ' + label}, best match first`
            : d.cat ? `${kind === 'all' ? 'Every set' : label} · ${sets.length} · tap a set to see its cards` : ''}
        </T>
      </View>}
      ListEmptyComponent={!d.cat ? (d.catError ? <Empty>{d.catError}</Empty> : <View style={{ paddingHorizontal: px }}><SkelRows n={8} /></View>)
        : searching ? <Empty>{kind === 'all' ? `Nothing matches “${q}”.` : `Nothing in ${label} matches “${q}”. Try All sets.`}</Empty>
        : <Empty>No sets here yet.</Empty>}
      renderItem={({ item }) => {
        const row = searching ? <CardRow card={item} showSet onOpen={remember} /> : <SetRow set={item} />;
        return wide ? <View style={{ flex: 1, maxWidth: '50%' }}>{row}</View> : row;
      }}
      contentContainerStyle={{ paddingBottom: BAR_SPACE }} />
  );
}
