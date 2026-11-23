import React, { useCallback, useMemo, useState } from 'react';
import { ScrollView, View, useWindowDimensions } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, ChangePill, Empty, GlowChart, Note, Panel, Select, Skel, SkelRows, T } from '../../src/ui';
import { AlertList } from '../../src/alerts';
import { SignalsPanel } from '../../src/history';
import { DealsPanel } from '../../src/deals';
import { Heading, IconBtn, Screen, TileRail } from '../../src/screen';
import { useTiles } from '../../src/layout';
import { CardTile, OwnedRow } from '../../src/tiles';
import { CardRow } from '../../src/rows';

const CardRowLite = ({ card }) => <View style={{ marginHorizontal: -16 }}><CardRow card={card} /></View>;

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
  const tiles = useTiles(), wide = tiles.wide;
  useFocusEffect(useCallback(() => { if (d.session) d.refresh(); }, [d.session]));
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
      {wide ? <T head size={28}>Home</T> : <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={{ width: 28, height: 28, borderRadius: 8, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="compass" size={18} color={c.onAccent} />
          </View>
          <T head size={15} style={{ letterSpacing: 0.4 }}>ONE PIECE MARKET</T>
        </View>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <IconBtn icon="scan" label="Scan a card" onPress={() => router.push('/scan')} />
          <IconBtn icon="person-outline" label="Profile" onPress={() => router.push('/account')} />
        </View>
      </View>}

      {signedOut ? (
        <View style={{ marginTop: 40, gap: 12, alignItems: 'center' }}>
          <T head size={30} style={{ textAlign: 'center' }}>Know what your cards are worth</T>
          <T mute style={{ textAlign: 'center' }}>Prices for every One Piece set and promo. No account needed to look around.</T>
          <Button icon="scan" onPress={() => router.push('/scan')} style={{ alignSelf: 'stretch', marginTop: 8 }}>Scan a card</Button>
          <Button ghost icon="search" onPress={() => router.push('/search')} style={{ alignSelf: 'stretch' }}>Search prices</Button>
          {d.configured ? <T size={13.5} mute style={{ textAlign: 'center', marginTop: 6 }}>Want to track your own cards? <T size={13.5} w="semi" style={{ color: c.accent }} onPress={() => router.push('/account')}>Sign in or create an account</T></T> : null}
          {d.alerts.length ? <View style={{ alignSelf: 'stretch', marginTop: 12 }}><AlertList max={4} /></View> : null}
        </View>
      ) : !d.loaded && d.busy ? (
        <View style={{ marginTop: 22, gap: 16, alignItems: 'center' }}>
          <Skel w={110} h={30} r={15} /><Skel w={220} h={52} /><Skel w={90} h={22} r={11} />
          <Skel h={200} r={16} />
          <View style={{ alignSelf: 'stretch' }}><SkelRows n={4} art={38} /></View>
        </View>
      ) : (
        <>
          {d.loadError ? <Note tone="warn" title="Couldn’t load your collection" style={{ marginTop: 14 }} action="Retry" onAction={() => d.refresh()}>{d.loadError}</Note> : null}
          {d.alerts.length ? <View style={{ marginTop: 14 }}><AlertList max={4} /></View> : null}
          <DealsPanel />
          <SignalsPanel />
          <View style={wide ? { flexDirection: 'row', gap: 28, alignItems: 'flex-start', marginTop: 8 } : null}>
          <View style={wide ? { flex: 1.35, minWidth: 0 } : null}>
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
            <GlowChart values={values} width={chartW} height={wide ? 260 : Math.min(240, width * 0.58)} fmt={d.aud} />
          </View>

          <Button icon="add" onPress={() => router.push('/item/new')} style={{ marginTop: 18 }}>Add to collection</Button>
          </View>
          <View style={wide ? { flex: 1, minWidth: 0, marginTop: 18 } : null}>

          <Panel style={{ marginTop: wide ? 0 : 22, gap: 4 }}>
            <Heading onMore={() => router.push('/portfolio')}>Most valuable</Heading>
            {top.length ? top.map((o, i) => <OwnedRow key={o.id} o={o} rank={i + 1} />) : <View style={{ gap: 10, paddingVertical: 8 }}>
              <T mute size={14}>Nothing in your collection yet.</T>
              <Button icon="scan" onPress={() => router.push('/scan')}>Scan your first card</Button>
              <Button ghost icon="cloud-upload-outline" onPress={() => router.push('/import')}>Import from Collectr or a CSV</Button>
            </View>}
          </Panel>

          {d.favs.length ? <Panel style={{ marginTop: 14, gap: 4 }}>
            <Heading onMore={() => router.push('/watchlist')}>Watchlist</Heading>
            {d.favs.map(f => d.card(f.card)).filter(Boolean).slice(0, 4).map(x => <CardRowLite key={x.k} card={x} />)}
          </Panel> : null}

          {movers.length ? <Panel style={{ marginTop: 14, gap: 4 }}>
            <Heading onMore={() => router.push('/movers')}>Moved this week</Heading>
            {movers.map(o => <OwnedRow key={o.id} o={o} />)}
          </Panel> : null}
          </View>
          </View>
        </>
      )}

      {hot.length ? <>
        <Heading style={{ marginTop: 26 }} onMore={() => router.push('/market')} more="Market">Rising this week</Heading>
        <TileRail>
          {(wide ? hot.slice(0, tiles.cols * Math.max(1, Math.floor(hot.length / tiles.cols))) : hot).map(x => <CardTile key={x.k} card={x} width={tiles.width} />)}
        </TileRail>
      </> : null}
    </Screen>
  );
}
