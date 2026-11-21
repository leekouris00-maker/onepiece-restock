import React, { useMemo, useState } from 'react';
import { FlatList, ScrollView, View } from 'react-native';
import { KINDS, useData } from '../../src/data';
import { CardRow, SetRow } from '../../src/rows';
import { Chip, Empty, SearchBar, T } from '../../src/ui';
import { BAR_SPACE, Title, useTop } from '../../src/screen';

const ORDER = ['all', 'booster', 'extra', 'premium', 'starter', 'promo', 'event', 'pre-release', 'other', 'mine'];

export default function Search() {
  const d = useData(), top = useTop();
  const [q, setQ] = useState('');
  const [kind, setKind] = useState('all');
  const s = q.trim().toLowerCase().replace(/\s+/g, ' ');
  const searching = s.length >= 2;
  const kindOf = x => (x.mine ? 'mine' : d.cat?.byId[x.g]?.kind || 'other');

  // every match across all sets; the chips then narrow it to one kind of set
  const matches = useMemo(() => {
    if (!searching || !d.cat) return [];
    return [...d.custom, ...d.cat.list].filter(x => (x.n + ' ' + x.num).toLowerCase().includes(s)).sort((a, b) => (b.m ?? -1) - (a.m ?? -1));
  }, [s, searching, d.cat, d.custom]);

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
    return ORDER.filter(v => v === 'all' || allSets.some(x => x.kind === v)).map(v => [v, names[v] || v]);
  }, [allSets, searching]);

  const results = searching ? (kind === 'all' ? matches : matches.filter(x => kindOf(x) === kind)).slice(0, 300) : [];
  const sets = searching ? [] : kind === 'all' ? allSets : allSets.filter(x => x.kind === kind);
  const label = (chips.find(([v]) => v === kind) || [, ''])[1];

  return (
    <FlatList data={searching ? results : sets} keyExtractor={x => (searching ? x.k : 'set:' + x.id)} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"
      style={{ width: '100%', maxWidth: 900, alignSelf: 'center' }}
      ListHeaderComponent={<View style={{ paddingTop: top, paddingBottom: 6, gap: 10 }}>
        <View style={{ paddingHorizontal: 18, gap: 10 }}>
          <Title>Search</Title>
          <SearchBar value={q} onChangeText={setQ} placeholder="Name or number: Sabo, P-105, OP13-120" />
        </View>
        {d.cat ? <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled" contentContainerStyle={{ gap: 8, paddingHorizontal: 18 }}>
          {chips.map(([v, l]) => <Chip key={v} on={kind === v} onPress={() => setKind(v)}>{`${l} ${counts[v] || 0}`}</Chip>)}
        </ScrollView> : null}
        <T mute size={13} style={{ paddingHorizontal: 18 }}>
          {searching
            ? `${results.length >= 300 ? 'First 300' : results.length} ${results.length === 1 ? 'match' : 'matches'}${kind === 'all' ? '' : ' in ' + label}, highest price first`
            : d.cat ? `${kind === 'all' ? 'Every set' : label} · ${sets.length} · tap a set to see its cards` : ''}
        </T>
      </View>}
      ListEmptyComponent={!d.cat ? <Empty>{d.catError || 'Loading prices…'}</Empty>
        : searching ? <Empty>{kind === 'all' ? `Nothing matches “${q}”.` : `Nothing in ${label} matches “${q}”. Try All sets.`}</Empty>
        : <Empty>No sets here yet.</Empty>}
      renderItem={({ item }) => (searching ? <CardRow card={item} showSet /> : <SetRow set={item} />)}
      contentContainerStyle={{ paddingBottom: BAR_SPACE }} />
  );
}
