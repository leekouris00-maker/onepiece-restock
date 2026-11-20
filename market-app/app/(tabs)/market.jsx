import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { KINDS, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Chip, Empty, T } from '../../src/ui';
import { Heading, Screen } from '../../src/screen';
import { CardTile } from '../../src/tiles';

function Rail({ title, cards, right }) {
  if (!cards.length) return null;
  return <>
    <Heading style={{ marginTop: 26 }} right={right}>{title}</Heading>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingVertical: 12, paddingHorizontal: 18 }} style={{ marginHorizontal: -18 }}>
      {cards.map(x => <CardTile key={x.k} card={x} />)}
    </ScrollView>
  </>;
}

export default function Market() {
  const d = useData(), c = useTheme();
  const [kind, setKind] = useState('booster');
  const r = useMemo(() => {
    if (!d.cat) return null;
    const cards = d.cat.list.filter(x => x.t === 'card' && x.m != null);
    const promoSets = new Set(d.cat.sets.filter(s => s.kind === 'promo' || s.kind === 'event').map(s => s.id));
    // skip moves over 75%: those are nearly always a bad TCGplayer data point, not a real swing
    const moving = cards.filter(x => x.m >= 5 && d.move(x) != null && Math.abs(d.move(x)) <= 75);
    const newest = d.cat.sets.filter(s => s.kind === 'booster' && s.date).sort((a, b) => b.date.localeCompare(a.date))[0];
    return {
      promos: cards.filter(x => promoSets.has(x.g)).sort((a, b) => b.m - a.m).slice(0, 15),
      up: [...moving].sort((a, b) => d.move(b) - d.move(a)).filter(x => d.move(x) > 0).slice(0, 15),
      down: [...moving].sort((a, b) => d.move(a) - d.move(b)).filter(x => d.move(x) < 0).slice(0, 15),
      newest, newestTop: newest ? cards.filter(x => x.g === newest.id).sort((a, b) => b.m - a.m).slice(0, 15) : [],
    };
  }, [d.cat]);
  const kinds = useMemo(() => {
    const k = d.cat ? KINDS.filter(([v]) => d.cat.sets.some(s => s.kind === v)) : [];
    return d.custom.length ? [['mine', 'My cards'], ...k] : k;
  }, [d.cat, d.custom]);
  const sets = !d.cat ? [] : kind === 'mine'
    ? [...new Set(d.custom.map(x => x.setName || 'Other'))].sort().map(n => ({ id: 'mine:' + n, code: '★', name: n }))
    : d.cat.sets.filter(s => s.kind === kind).sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));

  if (!d.cat) return <Screen><Empty>{d.catError || 'Loading prices…'}</Empty></Screen>;
  return (
    <Screen onRefresh={() => d.loadCatalog(true)}>
      <T w="bold" size={28}>Market</T>
      <T mute size={13} style={{ marginTop: 4 }}>TCGplayer prices of {d.cat.meta.updated} · US$1 = A${d.cat.meta.fx}</T>
      <Pressable onPress={() => router.push('/search')} accessibilityRole="search"
        style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 50, borderRadius: 999, borderWidth: 1, borderColor: c.line, paddingHorizontal: 18, marginTop: 16 }}>
        <Ionicons name="search" size={22} color={c.ink} />
        <T mute size={17}>Search {d.cat.list.length.toLocaleString()} cards</T>
      </Pressable>

      <Rail title="Top promos" cards={r.promos} />
      <Rail title="Rising this week" cards={r.up} />
      <Rail title="Falling this week" cards={r.down} />
      {r.newest ? <Rail title={`Newest: ${r.newest.code || r.newest.name}`} cards={r.newestTop}
        right={<Pressable onPress={() => router.push({ pathname: '/set/[id]', params: { id: r.newest.id } })} hitSlop={10}><T size={15} style={{ color: c.accent }}>View all</T></Pressable>} /> : null}

      <Heading style={{ marginTop: 28 }}>Every set</Heading>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 12, paddingHorizontal: 18 }} style={{ marginHorizontal: -18 }}>
        {kinds.map(([v, l]) => <Chip key={v} on={kind === v} onPress={() => setKind(v)}>{l}</Chip>)}
      </ScrollView>
      <View style={{ borderRadius: 18, borderWidth: 1, borderColor: c.line, backgroundColor: c.panel, overflow: 'hidden' }}>
        {sets.map((s, i) => (
          <Pressable key={s.id} onPress={() => router.push({ pathname: '/set/[id]', params: { id: s.id } })} accessibilityRole="button"
            style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 14, paddingHorizontal: 16, backgroundColor: pressed ? c.raise : 'transparent', borderTopWidth: i ? 1 : 0, borderTopColor: c.line })}>
            <T w="bold" size={13} style={{ color: c.accent, width: 64 }} numberOfLines={1}>{s.code}</T>
            <View style={{ flex: 1 }}>
              <T size={15} numberOfLines={2}>{s.name}</T>
              {s.date ? <T size={12.5} mute>{s.date}</T> : null}
            </View>
            <Ionicons name="chevron-forward" size={18} color={c.mute} />
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}
