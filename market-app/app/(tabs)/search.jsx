import React, { useMemo, useState } from 'react';
import { FlatList, View } from 'react-native';
import { useData } from '../../src/data';
import { CardRow } from '../../src/rows';
import { Empty, SearchBar, T } from '../../src/ui';
import { BAR_SPACE, Title, useTop } from '../../src/screen';

export default function Search() {
  const d = useData(), top = useTop();
  const [q, setQ] = useState('');
  const results = useMemo(() => {
    const s = q.trim().toLowerCase().replace(/\s+/g, ' ');
    if (s.length < 2 || !d.cat) return [];
    return [...d.custom, ...d.cat.list].filter(x => (x.n + ' ' + x.num).toLowerCase().includes(s)).sort((a, b) => (b.m ?? -1) - (a.m ?? -1)).slice(0, 300);
  }, [q, d.cat, d.custom]);
  return (
    <FlatList data={results} keyExtractor={x => x.k} keyboardShouldPersistTaps="handled" keyboardDismissMode="on-drag"
      style={{ width: '100%', maxWidth: 900, alignSelf: 'center' }}
      ListHeaderComponent={<View style={{ paddingHorizontal: 18, paddingTop: top, paddingBottom: 8, gap: 10 }}>
        <Title sub="Every set, promos and your own cards">Search</Title>
        <SearchBar value={q} onChangeText={setQ} placeholder="Name or number: Sabo, P-105, OP13-120" />
        {q.trim().length >= 2 ? <T mute size={13}>{results.length >= 300 ? 'First 300 matches, highest price first' : `${results.length} matches, highest price first`}</T> : null}
      </View>}
      ListEmptyComponent={q.trim().length >= 2 ? <Empty>Nothing matches “{q}”.</Empty> : <Empty>Search every set at once, promos and your own cards included.</Empty>}
      renderItem={({ item }) => <CardRow card={item} showSet />} contentContainerStyle={{ paddingBottom: BAR_SPACE }} />
  );
}
