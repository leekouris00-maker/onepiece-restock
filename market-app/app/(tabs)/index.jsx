import React, { useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, CardArt, Chip, Empty, T } from '../../src/ui';

export default function Collection() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const [filter, setFilter] = useState('all');
  const pad = 18, gap = 14, cols = width >= 900 ? 5 : width >= 640 ? 4 : width >= 430 ? 3 : 2;
  const tileW = Math.floor((Math.min(width, 1100) - pad * 2 - gap * (cols - 1)) / cols);

  const live = d.owned.filter(o => o.status !== 'sold');
  const tot = o => (d.ownVal(o).a || 0) * (Number(o.qty) || 1);
  const stats = useMemo(() => {
    let worth = 0, paid = 0, paidN = 0, priced = 0, units = 0;
    for (const o of live) { const q = Number(o.qty) || 1, v = d.ownVal(o).a; units += q; if (v != null) { worth += v * q; priced++; } if (o.paid != null) { paid += Number(o.paid) * q; paidN++; } }
    const sold = d.owned.filter(o => o.status === 'sold').reduce((n, o) => n + (Number(o.soldFor) || 0) * (Number(o.qty) || 1), 0);
    return { worth, paid, paidN, priced, units, sold };
  }, [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const groups = useMemo(() => {
    const m = {}; for (const o of live) { const g = o.group || 'Other'; m[g] = (m[g] || 0) + tot(o); }
    return Object.entries(m).sort((a, b) => b[1] - a[1]);
  }, [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const gmax = Math.max(1, ...groups.map(g => g[1]));

  if (!d.configured) return <Empty>Saving isn’t set up in this build yet. You can still browse prices in Market and Search.</Empty>;
  if (d.authReady && !d.session) return (
    <View style={{ padding: 24, gap: 14 }}>
      <T serif size={30}>Your collection lives here</T>
      <T mute>Sign in to see what you own, what it’s worth and your photos, on every device.</T>
      <Button onPress={() => router.push('/account')}>Sign in</Button>
    </View>
  );

  const list = filter === 'sold' ? d.owned.filter(o => o.status === 'sold') : live.filter(o => filter === 'all' || (o.group || 'Other') === filter);
  const byG = {}; for (const o of list) (byG[filter === 'sold' ? 'Sold' : o.group || 'Other'] ??= []).push(o);
  const order = filter === 'sold' ? ['Sold'] : groups.map(g => g[0]).filter(g => byG[g]);

  return (
    <ScrollView contentContainerStyle={{ padding: pad, paddingBottom: 60, maxWidth: 1100, width: '100%', alignSelf: 'center' }}
      refreshControl={<RefreshControl refreshing={d.busy} onRefresh={() => { d.refresh(); d.loadCatalog(true); }} tintColor={c.mute} />}>
      <T size={13} w="semi" style={{ color: c.gold }}>Worth now</T>
      <T serif size={Math.min(64, width / 6.2)} style={{ letterSpacing: -1, marginTop: 2 }}>{d.cat ? d.aud(stats.worth) : '…'}</T>
      <T mute size={14} style={{ marginTop: 8 }}>
        <T w="semi" size={14}>{stats.units}</T> items · {stats.priced} of {live.length} priced
        {stats.paidN ? <> · paid <T w="semi" size={14}>{d.aud(stats.paid)}</T></> : null}
        {stats.sold ? <> · sold <T w="semi" size={14}>{d.aud(stats.sold)}</T></> : null}
      </T>

      <View style={{ gap: 9, marginTop: 22, paddingBottom: 20, borderBottomWidth: 1, borderBottomColor: c.line }}>
        {groups.map(([g, w]) => (
          <Pressable key={g} onPress={() => setFilter(filter === g ? 'all' : g)} accessibilityRole="button"
            style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <T size={13.5} numberOfLines={1} w={filter === g ? 'bold' : undefined} style={{ width: 118 }}>{g}</T>
            <View style={{ flex: 1 }}><View style={{ height: 10, borderRadius: 999, backgroundColor: c.red, width: `${Math.max(1, (w / gmax) * 100)}%`, opacity: filter === 'all' || filter === g ? 1 : 0.35 }} /></View>
            <T size={13.5} style={{ fontVariant: ['tabular-nums'] }}>{d.aud(w)}</T>
          </Pressable>
        ))}
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginTop: 16 }}>
        <Chip on={filter === 'all'} onPress={() => setFilter('all')}>Everything</Chip>
        <Chip on={filter === 'sold'} onPress={() => setFilter('sold')}>Sold</Chip>
        {filter !== 'all' && filter !== 'sold' ? <Chip on onPress={() => setFilter('all')}>{filter} ✕</Chip> : null}
        <View style={{ flex: 1 }} />
        <Button onPress={() => router.push('/item/new')} style={{ minHeight: 40 }}>Add item</Button>
      </View>

      {!list.length ? <Empty>Nothing here yet. Open any card and tap “Add to my collection”, or use Add item for sealed product and anything else.</Empty> : null}
      {order.map(g => (
        <View key={g}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 28, marginBottom: 14 }}>
            <T serif size={22}>{g}</T>
            <T mute size={13.5}>{byG[g].length}{filter === 'sold' ? '' : ' · ' + d.aud(byG[g].reduce((n, o) => n + tot(o), 0))}</T>
          </View>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap }}>
            {byG[g].sort((a, b) => tot(b) - tot(a)).map(o => {
              const v = d.ownVal(o), q = Number(o.qty) || 1, sold = o.status === 'sold', card = d.card(o.card);
              return (
                <Pressable key={o.id} onPress={() => router.push({ pathname: '/item/[id]', params: { id: o.id } })} style={{ width: tileW, gap: 7 }} accessibilityRole="button">
                  <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num || (o.kind === 'Sealed' ? 'Sealed' : '')} label={o.lang && o.lang !== 'EN' ? o.lang : ''} width={tileW} qty={q} />
                  <T size={14} w="semi" numberOfLines={2}>{o.name}</T>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: 6 }}>
                    <T size={12} mute numberOfLines={1} style={{ flexShrink: 1 }}>{sold ? 'sold' : v.src}</T>
                    <T serif size={16}>{sold ? d.aud((Number(o.soldFor) || 0) * q) : d.aud(v.a == null ? null : v.a * q)}</T>
                  </View>
                </Pressable>
              );
            })}
          </View>
        </View>
      ))}
      <T mute size={12.5} style={{ marginTop: 30 }}>Each item is valued by your own estimate if you set one, otherwise the automatic eBay median, then your logged sales, then TCGplayer. Pull down to refresh.</T>
    </ScrollView>
  );
}
