import React, { useMemo, useState } from 'react';
import { FlatList, TextInput, View } from 'react-native';
import { useData } from '../../src/data';
import { F, useTheme } from '../../src/theme';
import { CardRow } from '../../src/rows';
import { Empty, T } from '../../src/ui';

export default function Search() {
  const d = useData(), c = useTheme();
  const [q, setQ] = useState('');
  const results = useMemo(() => {
    const s = q.trim().toLowerCase().replace(/\s+/g, ' ');
    if (s.length < 2 || !d.cat) return [];
    return [...d.custom, ...d.cat.list].filter(x => (x.n + ' ' + x.num).toLowerCase().includes(s)).sort((a, b) => (b.m ?? -1) - (a.m ?? -1)).slice(0, 300);
  }, [q, d.cat, d.custom]);
  return (
    <FlatList data={results} keyExtractor={x => x.k} keyboardShouldPersistTaps="handled"
      ListHeaderComponent={<View style={{ padding: 18, gap: 8 }}>
        <TextInput value={q} onChangeText={setQ} placeholder="Name or number: P-105, Sabo, OP13-120" placeholderTextColor={c.mute} autoCorrect={false} autoCapitalize="none" clearButtonMode="while-editing" returnKeyType="search"
          style={{ minHeight: 48, borderRadius: 999, borderWidth: 1, borderColor: c.line, paddingHorizontal: 18, color: c.ink, fontFamily: F.text, fontSize: 16, backgroundColor: c.soft }} />
        {q.trim().length >= 2 ? <T mute size={13}>{results.length >= 300 ? 'First 300 matches, highest price first' : `${results.length} matches, highest price first`}</T> : null}
      </View>}
      ListEmptyComponent={q.trim().length >= 2 ? <Empty>Nothing matches “{q}”.</Empty> : <Empty>Search every set at once, promos and your own cards included.</Empty>}
      renderItem={({ item }) => <CardRow card={item} showSet />} contentContainerStyle={{ paddingBottom: 40 }} />
  );
}
