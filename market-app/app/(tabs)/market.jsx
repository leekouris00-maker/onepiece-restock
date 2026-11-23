import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { KINDS, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Chip, Empty, Panel, Skel, T } from '../../src/ui';
import { ChipRow, Heading, Screen, TileRail, Title } from '../../src/screen';
import { useTiles } from '../../src/layout';
import { CardTile } from '../../src/tiles';

function Rail({ title, cards, onMore }) {
  const t = useTiles();
  if (!cards.length) return null;
  // computer: one full row of tiles (See all for more); phone: the sideways carousel
  const shown = t.wide ? cards.slice(0, t.cols) : cards;
  return <>
    <Heading style={{ marginTop: t.wide ? 30 : 24 }} onMore={onMore}>{title}</Heading>
    <TileRail>{shown.map(x => <CardTile key={x.k} card={x} width={t.width} />)}</TileRail>
  </>;
}

export default function Market() {
  const d = useData(), c = useTheme(), wide = useTiles().wide;
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
      up: moving.filter(x => d.move(x) > 0).sort((a, b) => d.move(b) - d.move(a)).slice(0, 15),
      down: moving.filter(x => d.move(x) < 0).sort((a, b) => d.move(a) - d.move(b)).slice(0, 15),
      newest, newestTop: newest ? cards.filter(x => x.g === newest.id).sort((a, b) => b.m - a.m).slice(0, 15) : [],
    };
  }, [d.cat]);
  const kinds = useMemo(() => {
    const order = ['booster', 'extra', 'premium', 'starter', 'promo', 'event', 'pre-release', 'other'];
    const k = d.cat ? KINDS.filter(([v]) => d.cat.sets.some(s => s.kind === v)).sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0])) : [];
    return d.custom.length ? [...k, ['mine', 'My cards']] : k;
  }, [d.cat, d.custom]);
  const counts = useMemo(() => {
    const n = {};
    for (const st of d.cat ? d.cat.sets : []) n[st.kind] = (n[st.kind] || 0) + 1;
    n.mine = new Set(d.custom.map(x => x.setName || 'Other')).size;
    return n;
  }, [d.cat, d.custom]);
  const sets = !d.cat ? [] : kind === 'mine'
    ? [...new Set(d.custom.map(x => x.setName || 'Other'))].sort().map(n => ({ id: 'mine:' + n, code: '★', name: n }))
    : d.cat.sets.filter(s => s.kind === kind).sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));

  if (!d.cat) return <Screen><Title>Market</Title>{d.catError ? <Empty>{d.catError}</Empty> : <View style={{ gap: 14, marginTop: 10 }}>
    <Skel h={48} r={14} />{[0, 1].map(i => <View key={i} style={{ gap: 10, marginTop: 14 }}><Skel w={140} h={16} />
      <View style={{ flexDirection: 'row', gap: 14 }}>{[0, 1, 2].map(j => <Skel key={j} w={120} h={168} r={8} />)}</View></View>)}</View>}</Screen>;
  const favCards = d.favs.map(f => d.card(f.card)).filter(Boolean);
  return (
    <Screen onRefresh={() => d.loadCatalog(true)}>
      <Title sub={`TCGplayer prices of ${d.cat.meta.updated} · US$1 = A$${d.cat.meta.fx}`}>Market</Title>
      <Pressable onPress={() => router.push('/search')} accessibilityRole="search"
        style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 48, borderRadius: 14, backgroundColor: c.soft, paddingHorizontal: 14, marginTop: 10 }}>
        <Ionicons name="search" size={19} color={c.mute} />
        <T mute size={15.5} w="medium">Search {d.cat.list.length.toLocaleString()} cards</T>
      </Pressable>

      <Rail title="Your watchlist" cards={favCards} onMore={() => router.push('/watchlist')} />
      <Rail title="Top promos" cards={r.promos} />
      <Rail title="Rising this week" cards={r.up} onMore={() => router.push('/movers')} />
      <Rail title="Falling this week" cards={r.down} onMore={() => router.push('/movers')} />
      {r.newest ? <Rail title={`Newest: ${r.newest.code || r.newest.name}`} cards={r.newestTop} onMore={() => router.push({ pathname: '/set/[id]', params: { id: r.newest.id } })} /> : null}

      <Heading style={{ marginTop: 28 }}>Sets</Heading>
      <ChipRow pad={wide ? 0 : 18} style={wide ? { marginVertical: 12 } : { marginHorizontal: -18, paddingVertical: 12 }}>
        {kinds.map(([v, l]) => <Chip key={v} on={kind === v} onPress={() => setKind(v)}>{`${l} ${counts[v] || 0}`}</Chip>)}
      </ChipRow>
      <Panel style={{ gap: 0 }}>
        <T mute size={12.5} w="semi">{(kinds.find(([v]) => v === kind) || [, 'Sets'])[1]} · {sets.length} {sets.length === 1 ? 'set' : 'sets'}</T>
        <View style={[{ marginTop: 4 }, wide && { flexDirection: 'row', flexWrap: 'wrap', columnGap: 28 }]}>
          {sets.map(s => (
            <Pressable key={s.id} onPress={() => router.push({ pathname: '/set/[id]', params: { id: s.id } })} accessibilityRole="button"
              style={({ pressed, hovered }) => ({ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, opacity: pressed ? 0.6 : hovered ? 0.8 : 1, ...(wide ? { flexBasis: '40%', flexGrow: 1, maxWidth: '50%' } : null) })}>
              <View style={{ width: 54, height: 36, borderRadius: 10, backgroundColor: c.soft, alignItems: 'center', justifyContent: 'center' }}>
                <T w="bold" size={11.5} style={{ color: c.accent }} numberOfLines={1}>{s.code}</T>
              </View>
              <View style={{ flex: 1 }}>
                <T w="semi" size={14.5} numberOfLines={1}>{s.name}</T>
                {s.date ? <T size={12} mute>{s.date}</T> : null}
              </View>
              <Ionicons name="chevron-forward" size={16} color={c.mute} />
            </Pressable>
          ))}
        </View>
      </Panel>
    </Screen>
  );
}
