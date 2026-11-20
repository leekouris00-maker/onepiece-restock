import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { AreaChart, Button, Change, Chip, Empty, RoundAction, T } from '../../src/ui';
import { Heading, Screen } from '../../src/screen';
import { CardTile, OwnedRow, OwnedTile } from '../../src/tiles';

const RANGES = [['1D', 1, 'today'], ['7D', 7, 'in the last 7 days'], ['1M', 30, 'in the last 30 days']];

export default function Home() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const [range, setRange] = useState(2);
  const [chartW, setChartW] = useState(0);
  const live = d.owned.filter(o => o.status !== 'sold');
  const [, days, words] = RANGES[range];
  const values = useMemo(() => (d.cat ? d.series(days) : []), [d.owned, d.cat, d.comps, d.sales, d.watch, days]);
  const now = values[values.length - 1], then = values[0];
  const tot = o => (d.unitAt(o, 0) || 0) * (Number(o.qty) || 1);
  const top = useMemo(() => [...live].sort((a, b) => tot(b) - tot(a)).slice(0, 5), [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const movers = useMemo(() => live.map(o => ({ o, now: d.unitAt(o, 0), then: d.unitAt(o, 7) }))
    .filter(x => x.now && x.then && Math.abs(x.now - x.then) / x.then >= 0.005)
    .sort((a, b) => Math.abs(b.now - b.then) / b.then - Math.abs(a.now - a.then) / a.then).slice(0, 10), [d.owned, d.cat]);
  const hot = useMemo(() => (d.cat ? d.cat.list.filter(x => x.t === 'card' && x.m >= 5 && d.move(x) != null && Math.abs(d.move(x)) <= 75).sort((a, b) => d.move(b) - d.move(a)).slice(0, 12) : []), [d.cat]);
  const big = Math.min(54, width / 7.4);

  const signedOut = !d.configured || (d.authReady && !d.session);

  return (
    <Screen onRefresh={() => { d.refresh(); d.loadCatalog(true); }} refreshing={d.busy}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <T w="bold" size={17}>One Piece Market</T>
        <Pressable onPress={() => router.push('/account')} accessibilityLabel="Profile" hitSlop={10}>
          <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: c.raise, alignItems: 'center', justifyContent: 'center' }}>
            <T w="bold" size={15} style={{ color: c.accent }}>{(d.session?.user?.email || 'OP')[0].toUpperCase()}</T>
          </View>
        </Pressable>
      </View>

      {signedOut ? (
        <View style={{ marginTop: 28, gap: 12 }}>
          <T w="bold" size={30}>Track what your One Piece cards are worth</T>
          <T mute>{d.configured ? 'Sign in to see your portfolio, its value over time and your photos on every device.' : 'Saving isn’t set up in this build yet. You can still browse prices.'}</T>
          {d.configured ? <Button onPress={() => router.push('/account')} style={{ alignSelf: 'flex-start' }}>Sign in</Button> : null}
        </View>
      ) : (
        <>
          <T mute size={15} style={{ marginTop: 26 }}>Portfolio value</T>
          <T w="bold" size={big} style={{ letterSpacing: -1, marginTop: 2 }}>{d.cat ? d.aud(now ?? 0) : '…'}</T>
          {now != null && then ? (
            <View style={{ flexDirection: 'row', gap: 6, alignItems: 'baseline', flexWrap: 'wrap', marginTop: 2 }}>
              <Change now={now} then={then} aud={d.aud} size={16} /><T mute size={16}>{words}</T>
            </View>
          ) : null}
          <View onLayout={e => setChartW(e.nativeEvent.layout.width)} style={{ marginTop: 14, marginHorizontal: -18 }}>
            <AreaChart values={values} width={chartW} height={Math.min(260, width * 0.55)} />
          </View>
          <View style={{ flexDirection: 'row', gap: 8, justifyContent: 'center', marginTop: 12 }}>
            {RANGES.map(([l], i) => <Chip key={l} on={range === i} onPress={() => setRange(i)}>{l}</Chip>)}
          </View>
          <T mute size={12} style={{ textAlign: 'center', marginTop: 8 }}>TCGplayer price history covers about 5 weeks. Items valued by eBay, your sales or your own estimate stay flat.</T>

          <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginTop: 24 }}>
            <RoundAction icon="trending-up" label="Movers" onPress={() => router.push('/movers')} />
            <RoundAction icon="add" label="Add item" onPress={() => router.push('/item/new')} />
            <RoundAction icon="create-outline" label="Add card" onPress={() => router.push('/addcard')} />
            <RoundAction icon="albums-outline" label="Portfolio" onPress={() => router.push('/portfolio')} />
          </View>

          <Heading style={{ marginTop: 30 }} right={<Pressable onPress={() => router.push('/portfolio')} hitSlop={10}><T size={15} style={{ color: c.accent }}>View all</T></Pressable>}>Most valuable</Heading>
          <View style={{ marginTop: 8 }}>
            {top.length ? top.map((o, i) => <OwnedRow key={o.id} o={o} rank={i + 1} />) : <Empty>Nothing in your portfolio yet. Tap Add item, or open any card and add it.</Empty>}
          </View>

          {movers.length ? <>
            <Heading style={{ marginTop: 26 }}>Your movers this week</Heading>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingVertical: 12 }}>
              {movers.map(({ o }) => <OwnedTile key={o.id} o={o} width={150} />)}
            </ScrollView>
          </> : null}
        </>
      )}

      {hot.length ? <>
        <Heading style={{ marginTop: 26 }} right={<Pressable onPress={() => router.push('/market')} hitSlop={10}><T size={15} style={{ color: c.accent }}>Market</T></Pressable>}>Rising this week</Heading>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingVertical: 12 }}>
          {hot.map(x => <CardTile key={x.k} card={x} />)}
        </ScrollView>
      </> : null}
    </Screen>
  );
}
