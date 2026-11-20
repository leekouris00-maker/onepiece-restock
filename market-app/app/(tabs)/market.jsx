import React, { useMemo } from 'react';
import { Pressable, RefreshControl, SectionList, View } from 'react-native';
import { router } from 'expo-router';
import { KINDS, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Empty, T } from '../../src/ui';

export default function Market() {
  const d = useData(), c = useTheme();
  const sections = useMemo(() => {
    if (!d.cat) return [];
    const mine = [...new Set(d.custom.map(x => x.setName || 'Other'))].sort().map(n => ({ id: 'mine:' + n, code: '★', name: n }));
    const out = mine.length ? [{ title: 'My cards (JP and others)', data: mine }] : [];
    for (const [k, l] of KINDS) { const s = d.cat.sets.filter(x => x.kind === k); if (s.length) out.push({ title: l, data: s }); }
    return out;
  }, [d.cat, d.custom]);
  if (!d.cat) return <Empty>{d.catError || 'Loading prices…'}</Empty>;
  return (
    <SectionList sections={sections} keyExtractor={s => s.id} stickySectionHeadersEnabled={false}
      refreshControl={<RefreshControl refreshing={false} onRefresh={() => d.loadCatalog(true)} tintColor={c.mute} />}
      ListHeaderComponent={<View style={{ padding: 18, paddingBottom: 4 }}>
        <T mute size={13}>TCGplayer prices of {d.cat.meta.updated} · US$1 = A${d.cat.meta.fx} · {d.cat.list.length.toLocaleString()} cards and products</T>
      </View>}
      renderSectionHeader={({ section }) => <T size={12.5} w="semi" style={{ color: c.gold, paddingHorizontal: 18, paddingTop: 22, paddingBottom: 6 }}>{section.title}</T>}
      renderItem={({ item }) => (
        <Pressable onPress={() => router.push({ pathname: '/set/[id]', params: { id: item.id } })} accessibilityRole="button"
          style={({ pressed }) => ({ flexDirection: 'row', gap: 14, paddingVertical: 12, paddingHorizontal: 18, backgroundColor: pressed ? c.soft : 'transparent', borderBottomWidth: 1, borderBottomColor: c.line })}>
          <T w="semi" mute size={13} style={{ width: 64 }}>{item.code}</T>
          <T size={15} style={{ flex: 1 }}>{item.name}</T>
        </Pressable>
      )}
      contentContainerStyle={{ paddingBottom: 40 }} />
  );
}
