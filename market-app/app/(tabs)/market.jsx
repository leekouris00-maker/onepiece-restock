import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { KINDS, useData, clean } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Chip, Empty, T } from '../../src/ui';
import { Heading, Screen, Title } from '../../src/screen';
import { CardTile } from '../../src/tiles';

function Rail({ title, cards, onMore }) {
  if (!cards.length) return null;
  return <>
    <Heading style={{ marginTop: 24 }} onMore={onMore}>{title}</Heading>
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingVertical: 12, paddingHorizontal: 18 }} style={{ marginHorizontal: -18 }}>
      {cards.map(x => <CardTile key={x.k} card={x} />)}
    </ScrollView>
  </>;
}

export default function Market() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const [kind, setKind] = useState('booster');
  const cols = width >= 900 ? 4 : width >= 600 ? 3 : 2, gap = 12;
  const setW = Math.floor((Math.min(width, 1100) - 36 - gap * (cols - 1)) / cols);
  const r = useMemo(() => {
    if (!d.cat) return null;
    const cards = d.cat.list.filter(x => x.t === 'card' && x.m != null);
    const promoSets = new Set(d.cat.sets.filter(s => s.kind === 'promo' || s.kind === 'event').map(s => s.id));
    // skip moves over 75%: those are nearly always a bad TCGplayer data point, not a real swing
    const moving = cards.filter(x => x.m >= 5 && d.move(x) != null && Math.abs(d.move(x)) <= 75);
    const newest = d.cat.sets.filter(s => s.kind === 'booster' && s.date).sort((a, b) => b.date.localeCompare(a.date))[0];
    const topOf = {}; for (const x of cards) if (!topOf[x.g] || x.m > topOf[x.g].m) topOf[x.g] = x;
    return {
      topOf,
      promos: cards.filter(x => promoSets.has(x.g)).sort((a, b) => b.m - a.m).slice(0, 15),
      up: moving.filter(x => d.move(x) > 0).sort((a, b) => d.move(b) - d.move(a)).slice(0, 15),
      down: moving.filter(x => d.move(x) < 0).sort((a, b) => d.move(a) - d.move(b)).slice(0, 15),
      newest, newestTop: newest ? cards.filter(x => x.g === newest.id).sort((a, b) => b.m - a.m).slice(0, 15) : [],
    };
  }, [d.cat]);
  const kinds = useMemo(() => {
    const k = d.cat ? KINDS.filter(([v]) => d.cat.sets.some(s => s.kind === v)) : [];
    return d.custom.length ? [...k, ['mine', 'My cards']] : k;
  }, [d.cat, d.custom]);
  const sets = !d.cat ? [] : kind === 'mine'
    ? [...new Set(d.custom.map(x => x.setName || 'Other'))].sort().map(n => ({ id: 'mine:' + n, code: '★', name: n }))
    : d.cat.sets.filter(s => s.kind === kind).sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));

  if (!d.cat) return <Screen><Title>Market</Title><Empty>{d.catError || 'Loading prices…'}</Empty></Screen>;
  return (
    <Screen onRefresh={() => d.loadCatalog(true)}>
      <Title sub={`TCGplayer prices of ${d.cat.meta.updated} · US$1 = A$${d.cat.meta.fx}`}
        right={<Ionicons name="compass-outline" size={28} color={c.accent} />}>Market</Title>
      <Pressable onPress={() => router.push('/search')} accessibilityRole="search"
        style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 50, borderRadius: 10, backgroundColor: c.soft, borderWidth: 1, borderColor: c.line, paddingHorizontal: 16, marginTop: 14 }}>
        <Ionicons name="search" size={20} color={c.accent} />
        <T mute size={16}>Search {d.cat.list.length.toLocaleString()} cards</T>
      </Pressable>

      <Rail title="Top promos" cards={r.promos} />
      <Rail title="Rising this week" cards={r.up} onMore={() => router.push('/movers')} />
      <Rail title="Falling this week" cards={r.down} onMore={() => router.push('/movers')} />
      {r.newest ? <Rail title={`Newest · ${r.newest.code || r.newest.name}`} cards={r.newestTop} onMore={() => router.push({ pathname: '/set/[id]', params: { id: r.newest.id } })} /> : null}

      <Heading style={{ marginTop: 28 }}>Every set</Heading>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 12, paddingHorizontal: 18 }} style={{ marginHorizontal: -18 }}>
        {kinds.map(([v, l]) => <Chip key={v} on={kind === v} onPress={() => setKind(v)}>{l}</Chip>)}
      </ScrollView>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap }}>
        {sets.map(s => {
          const t = r.topOf[s.id];
          return (
            <Pressable key={s.id} onPress={() => router.push({ pathname: '/set/[id]', params: { id: s.id } })} accessibilityRole="button"
              style={({ pressed }) => ({ width: setW, minHeight: 128, padding: 14, borderRadius: 12, borderWidth: 1, borderColor: c.line, backgroundColor: pressed ? c.raise : c.panel, gap: 4 })}>
              <T head size={24} style={{ color: c.accent, letterSpacing: 0.5 }} numberOfLines={1}>{s.code}</T>
              <T w="semi" size={14} numberOfLines={2}>{s.name}</T>
              <View style={{ flex: 1 }} />
              {t ? <T size={12} mute numberOfLines={1}>Top: {clean(t.n)} · {d.money(t.m)}</T> : null}
              {s.date ? <T size={11.5} mute>{s.date}</T> : null}
            </Pressable>
          );
        })}
      </View>
    </Screen>
  );
}
