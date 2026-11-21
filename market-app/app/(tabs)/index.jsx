import React, { useMemo, useState } from 'react';
import { ScrollView, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, ChangePill, Empty, GlowChart, Panel, Select, T } from '../../src/ui';
import { Heading, IconBtn, Screen } from '../../src/screen';
import { CardTile, OwnedRow } from '../../src/tiles';

const RANGES = [[1, '1 Day'], [7, '7 Days'], [30, '1 Month']];

// "A$2,911.40" → small "A$" + big "2,911" + ".40"
function BigMoney({ text }) {
  const c = useTheme();
  const m = /^([^\d]*)([\d,]+)(\.\d+)?$/.exec(text || '') || [null, '', text, ''];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'center' }}>
      <T w="bold" size={20} style={{ marginTop: 8, marginRight: 3 }}>{m[1]}</T>
      <T head size={50} style={{ letterSpacing: -1.5 }}>{m[2]}</T>
      {m[3] ? <T head size={50} style={{ letterSpacing: -1.5, color: c.mute }}>{m[3]}</T> : null}
    </View>
  );
}

export default function Home() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const [days, setDays] = useState(30);
  const [chartW, setChartW] = useState(0);
  const live = d.owned.filter(o => o.status !== 'sold');
  const values = useMemo(() => (d.cat ? d.series(days) : []), [d.owned, d.cat, d.comps, d.sales, d.watch, days]);
  const tot = o => (d.unitAt(o, 0) || 0) * (Number(o.qty) || 1);
  const stats = useMemo(() => {
    let paid = 0, paidWorth = 0;
    for (const o of live) if (o.paid != null && o.paid !== '') { paid += Number(o.paid) * (Number(o.qty) || 1); paidWorth += tot(o); }
    return { paid, profit: paidWorth - paid };
  }, [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const top = useMemo(() => [...live].sort((a, b) => tot(b) - tot(a)).slice(0, 5), [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const movers = useMemo(() => live.map(o => ({ o, a: d.unitAt(o, 0), b: d.unitAt(o, 7) }))
    .filter(x => x.a && x.b && Math.abs(x.a - x.b) / x.b >= 0.005)
    .sort((x, y) => Math.abs(y.a - y.b) / y.b - Math.abs(x.a - x.b) / x.b).slice(0, 4).map(x => x.o), [d.owned, d.cat]);
  const hot = useMemo(() => (d.cat ? d.cat.list.filter(x => x.t === 'card' && x.m >= 5 && d.move(x) != null && Math.abs(d.move(x)) <= 75).sort((a, b) => d.move(b) - d.move(a)).slice(0, 12) : []), [d.cat]);
  const now = values[values.length - 1], then = values[0];
  const signedOut = !d.configured || (d.authReady && !d.session);

  return (
    <Screen onRefresh={() => { d.refresh(); d.loadCatalog(true); }} refreshing={d.busy}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="compass" size={18} color={c.onAccent} />
          </View>
          <T head size={15} style={{ letterSpacing: 0.4 }}>ONE PIECE MARKET</T>
        </View>
        <IconBtn icon="person-outline" label="Profile" onPress={() => router.push('/account')} />
      </View>

      {signedOut ? (
        <View style={{ marginTop: 40, gap: 12, alignItems: 'center' }}>
          <T head size={30} style={{ textAlign: 'center' }}>Know what your cards are worth</T>
          <T mute style={{ textAlign: 'center' }}>{d.configured ? 'Sign in to see your collection and how its value moves.' : 'Saving isn’t set up in this build yet. You can still browse prices.'}</T>
          {d.configured ? <Button onPress={() => router.push('/account')} style={{ alignSelf: 'stretch', marginTop: 8 }}>Sign in</Button> : null}
        </View>
      ) : (
        <>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 18 }}>
            <View><T size={12.5} mute>Paid</T><T w="bold" size={15}>{stats.paid ? d.aud(stats.paid) : '–'}</T></View>
            <View style={{ alignItems: 'flex-end' }}>
              <T size={12.5} mute>Profit on what you paid for</T>
              <T w="bold" size={15} style={{ color: !stats.paid ? c.ink : stats.profit >= 0 ? c.up : c.down }}>{stats.paid ? (stats.profit >= 0 ? '+' : '-') + d.aud(Math.abs(stats.profit)) : '–'}</T>
            </View>
          </View>

          <View style={{ alignItems: 'center', marginTop: 22, gap: 10 }}>
            <Select value={days} onChange={setDays} options={RANGES} label="Show change over" style={{ alignSelf: 'center' }} />
            <BigMoney text={d.cat ? d.aud(now ?? 0) : '…'} />
            <ChangePill now={now} then={then} />
          </View>

          <View onLayout={e => setChartW(e.nativeEvent.layout.width)} style={{ marginTop: 6 }}>
            <GlowChart values={values} width={chartW} height={Math.min(240, width * 0.58)} fmt={d.aud} />
          </View>

          <Button icon="add" onPress={() => router.push('/item/new')} style={{ marginTop: 18 }}>Add to collection</Button>

          <Panel style={{ marginTop: 22, gap: 4 }}>
            <Heading onMore={() => router.push('/portfolio')}>Most valuable</Heading>
            {top.length ? top.map((o, i) => <OwnedRow key={o.id} o={o} rank={i + 1} />) : <Empty>Nothing in your collection yet.</Empty>}
          </Panel>

          {movers.length ? <Panel style={{ marginTop: 14, gap: 4 }}>
            <Heading onMore={() => router.push('/movers')}>Moved this week</Heading>
            {movers.map(o => <OwnedRow key={o.id} o={o} />)}
          </Panel> : null}
        </>
      )}

      {hot.length ? <>
        <Heading style={{ marginTop: 26 }} onMore={() => router.push('/market')} more="Market">Rising this week</Heading>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingVertical: 12, paddingHorizontal: 18 }} style={{ marginHorizontal: -18 }}>
          {hot.map(x => <CardTile key={x.k} card={x} />)}
        </ScrollView>
      </> : null}
    </Screen>
  );
}
