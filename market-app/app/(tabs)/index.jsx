import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData } from '../../src/data';
import { F, useTheme } from '../../src/theme';
import { ActionTile, Button, Empty, PosterChart, Stat, T } from '../../src/ui';
import { Heading, Screen } from '../../src/screen';
import { CardTile, OwnedRow, OwnedTile } from '../../src/tiles';

const RANGES = [['1D', 1, 'today'], ['7D', 7, 'this week'], ['1M', 30, 'this month']];

// The parchment "wanted poster" that holds the collection's value
function Poster({ d, values, words, range, setRange }) {
  const c = useTheme();
  const [w, setW] = useState(0);
  const now = values[values.length - 1], then = values[0];
  const diff = now != null && then ? now - then : null, pct = diff != null ? (diff / then) * 100 : null;
  const tone = diff == null || Math.abs(pct) < 0.05 ? c.paperMute : diff > 0 ? '#2f7a46' : '#b23a2a';
  return (
    <View style={{ backgroundColor: c.paper, borderRadius: 6, padding: 6, marginTop: 18 }}>
      <View style={{ borderWidth: 1.5, borderColor: c.paperLine, borderRadius: 3, paddingVertical: 16, paddingHorizontal: 14, alignItems: 'center' }}>
        <T head caps size={13} style={{ color: c.paperMute, letterSpacing: 4 }}>Collection bounty</T>
        <T head size={52} style={{ color: c.paperInk, letterSpacing: 0.5, marginTop: 2 }}>{d.cat ? d.aud(now ?? 0) : '…'}</T>
        <T w="semi" size={14} style={{ color: tone }}>
          {diff == null || Math.abs(pct) < 0.05 ? `No change ${words}` : `${diff > 0 ? '▲ +' : '▼ -'}${d.aud(Math.abs(diff))} (${Math.abs(pct).toFixed(2)}%) ${words}`}
        </T>
        <View onLayout={e => setW(e.nativeEvent.layout.width)} style={{ alignSelf: 'stretch', marginTop: 12 }}>
          <PosterChart values={values} width={w} height={110} />
        </View>
        <View style={{ flexDirection: 'row', gap: 22, marginTop: 10 }}>
          {RANGES.map(([l], i) => (
            <Pressable key={l} onPress={() => setRange(i)} hitSlop={8} accessibilityRole="button" accessibilityState={{ selected: range === i }}>
              <T head size={15} style={{ color: range === i ? c.paperInk : c.paperMute, borderBottomWidth: 2, borderBottomColor: range === i ? c.paperInk : 'transparent', paddingBottom: 2 }}>{l}</T>
            </Pressable>
          ))}
        </View>
      </View>
    </View>
  );
}

export default function Home() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const [range, setRange] = useState(1);
  const live = d.owned.filter(o => o.status !== 'sold');
  const [, days, words] = RANGES[range];
  const values = useMemo(() => (d.cat ? d.series(days) : []), [d.owned, d.cat, d.comps, d.sales, d.watch, days]);
  const tot = o => (d.unitAt(o, 0) || 0) * (Number(o.qty) || 1);
  const stats = useMemo(() => {
    let worth = 0, paid = 0, paidWorth = 0, units = 0;
    for (const o of live) { const q = Number(o.qty) || 1; units += q; worth += tot(o); if (o.paid != null && o.paid !== '') { paid += Number(o.paid) * q; paidWorth += tot(o); } }
    return { worth, paid, profit: paidWorth - paid, units };
  }, [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const top = useMemo(() => [...live].sort((a, b) => tot(b) - tot(a)).slice(0, 6), [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const movers = useMemo(() => live.map(o => ({ o, a: d.unitAt(o, 0), b: d.unitAt(o, 7) }))
    .filter(x => x.a && x.b && Math.abs(x.a - x.b) / x.b >= 0.005)
    .sort((x, y) => Math.abs(y.a - y.b) / y.b - Math.abs(x.a - x.b) / x.b).slice(0, 5).map(x => x.o), [d.owned, d.cat]);
  const hot = useMemo(() => (d.cat ? d.cat.list.filter(x => x.t === 'card' && x.m >= 5 && d.move(x) != null && Math.abs(d.move(x)) <= 75).sort((a, b) => d.move(b) - d.move(a)).slice(0, 12) : []), [d.cat]);
  const podW = Math.floor((Math.min(width, 1100) - 36 - 28) / 3);
  const signedOut = !d.configured || (d.authReady && !d.session);

  return (
    <Screen onRefresh={() => { d.refresh(); d.loadCatalog(true); }} refreshing={d.busy}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Ionicons name="compass" size={24} color={c.accent} />
          <T head caps size={19} style={{ letterSpacing: 2 }}>One Piece <T head caps size={19} style={{ color: c.accent, letterSpacing: 2 }}>Market</T></T>
        </View>
        <Pressable onPress={() => router.push('/account')} accessibilityLabel="Profile" hitSlop={10}>
          <View style={{ width: 36, height: 36, borderRadius: 18, borderWidth: 1.5, borderColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
            <T head size={16} style={{ color: c.accent }}>{(d.session?.user?.email || 'OP')[0].toUpperCase()}</T>
          </View>
        </Pressable>
      </View>

      {signedOut ? (
        <View style={{ marginTop: 28, gap: 12 }}>
          <T head caps size={32} style={{ lineHeight: 38 }}>What's your collection's bounty?</T>
          <T mute>{d.configured ? 'Sign in to see your collection, its value over time and your photos on every device.' : 'Saving isn’t set up in this build yet. You can still browse prices.'}</T>
          {d.configured ? <Button onPress={() => router.push('/account')} style={{ alignSelf: 'flex-start' }}>Sign in</Button> : null}
        </View>
      ) : (
        <>
          <Poster d={d} values={values} words={words} range={range} setRange={setRange} />
          <T mute size={11.5} style={{ textAlign: 'center', marginTop: 8 }}>Only items priced by TCGplayer have history (about 5 weeks). eBay-priced and your own estimates stay flat.</T>

          <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
            <Stat label="Items" value={String(stats.units)} />
            <Stat label="Paid" value={stats.paid ? d.aud(stats.paid) : '–'} />
            <Stat label="Profit" value={stats.paid ? (stats.profit >= 0 ? '+' : '-') + d.aud(Math.abs(stats.profit)) : '–'} tone={stats.paid ? (stats.profit >= 0 ? c.up : c.down) : null} />
          </View>

          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 }}>
            <ActionTile icon="add-circle-outline" label="Add item" sub="Card, pack or box" onPress={() => router.push('/item/new')} />
            <ActionTile icon="create-outline" label="Add card" sub="JP and promos" onPress={() => router.push('/addcard')} />
            <ActionTile icon="pulse-outline" label="Movers" sub="This week" onPress={() => router.push('/movers')} />
            <ActionTile icon="albums-outline" label="Collection" sub={`${live.length} entries`} onPress={() => router.push('/portfolio')} />
          </View>

          <Heading style={{ marginTop: 28 }} onMore={() => router.push('/portfolio')}>Top bounties</Heading>
          {top.length ? <>
            <View style={{ flexDirection: 'row', gap: 14, marginTop: 14 }}>
              {top.slice(0, 3).map((o, i) => <OwnedTile key={o.id} o={o} width={podW} rank={i + 1} />)}
            </View>
            <View style={{ marginTop: 10 }}>
              {top.slice(3).map((o, i, a) => <OwnedRow key={o.id} o={o} rank={i + 4} last={i === a.length - 1} />)}
            </View>
          </> : <Empty>Nothing in your collection yet. Tap Add item, or open any card and add it.</Empty>}

          {movers.length ? <>
            <Heading style={{ marginTop: 24 }} onMore={() => router.push('/movers')} more="All">Your movers this week</Heading>
            <View style={{ marginTop: 4 }}>{movers.map((o, i) => <OwnedRow key={o.id} o={o} last={i === movers.length - 1} />)}</View>
          </> : null}
        </>
      )}

      {hot.length ? <>
        <Heading style={{ marginTop: 24 }} onMore={() => router.push('/market')} more="Market">Rising this week</Heading>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingVertical: 12, paddingHorizontal: 18 }} style={{ marginHorizontal: -18 }}>
          {hot.map(x => <CardTile key={x.k} card={x} />)}
        </ScrollView>
      </> : null}
    </Screen>
  );
}
