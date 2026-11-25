// Promos & prize events (26 Nov 2026): which official events are on, what they give out and what those cards
// are worth, plus every promo card by price. Events from game.json (kept from Bandai's event pages).
import React, { useMemo, useState } from 'react';
import { FlatList, Linking, Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { clean, useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { CardArt, Chip, Panel, SearchBar, T } from '../src/ui';
import { ChipRow } from '../src/screen';
import { CardRow } from '../src/rows';
import { cardsFor, eventsNow, eventsSoon, myNums, niceDate, useGame } from '../src/game';

function EventCard({ e, d, c, own }) {
  const open = num => { const x = cardsFor(d, num)[0]; if (x) router.push({ pathname: '/card/[k]', params: { k: x.k } }); };
  return (
    <Panel>
      <View style={{ gap: 2 }}>
        <T mute size={12}>{`${e.kind} · ${niceDate(e.start)} – ${niceDate(e.end)}`}</T>
        <T w="bold" size={16.5}>{e.name}</T>
        <T mute size={12.5}>{e.where}</T>
      </View>
      {e.prizes.map((p, i) => (
        <View key={i} style={{ gap: 6 }}>
          <T size={13.5}><T w="semi" size={13.5}>{p.who}: </T>{p.what}</T>
          {(p.cards || []).map(num => {
            const list = cardsFor(d, num).slice(0, 3);
            if (!list.length) return <T key={num} mute size={12}>{`${num}: no price yet (new cards can take a few days to appear)`}</T>;
            return list.map(x => (
              <Pressable key={x.k} onPress={() => open(num)} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingLeft: 6 }}>
                <CardArt k={x.k} num={x.num} width={28} />
                <T size={13} style={{ flex: 1 }} numberOfLines={1}>{clean(x.n)}</T>
                {own.has(num) ? <T size={11.5} style={{ color: c.gold }}>you own one</T> : null}
                <T w="semi" size={13}>{x.m ? d.money(x.m) : '–'}</T>
              </Pressable>
            ));
          })}
        </View>
      ))}
      <Pressable onPress={() => Linking.openURL(e.url)}><T size={13} style={{ color: c.accent }}>Event page and how to enter (Bandai TCG+) ›</T></Pressable>
    </Panel>
  );
}

export default function Promos() {
  const d = useData(), c = useTheme();
  const { game, ready } = useGame();
  useTrack('promos');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('price');
  const { own } = useMemo(() => myNums(d, ''), [d.owned, d.cat]);
  const now = eventsNow(game), soon = eventsSoon(game);
  const promos = useMemo(() => {
    if (!d.cat) return [];
    const s = q.trim().toLowerCase();
    const l = d.cat.list.filter(x => /^P-\d{3}$/i.test(String(x.num || '')) && x.t !== 'sealed' && (!s || `${x.n} ${x.num}`.toLowerCase().includes(s)));
    return l.sort((a, b) => (sort === 'price' ? (b.m || 0) - (a.m || 0) : sort === 'move' ? (d.move(b) ?? -999) - (d.move(a) ?? -999) : String(b.num).localeCompare(String(a.num)))).slice(0, 150);
  }, [d.cat, q, sort]);
  const mine = (d.owned || []).filter(o => o.status !== 'sold' && /^P-\d{3}$/i.test(String(o.num || (o.card && d.card(o.card)?.num) || ''))).length;

  const header = (
    <View style={{ padding: 18, gap: 14 }}>
      <View style={{ gap: 4 }}>
        <T w="bold" size={30}>Promos & prize events</T>
        <T mute size={14}>Official events on now, what they give out, and what those cards are worth.</T>
      </View>
      {!ready ? <T mute>Loading…</T> : null}
      {now.length ? <T w="bold" size={18}>On now</T> : null}
      {now.map(e => <EventCard key={e.id} e={e} d={d} c={c} own={own} />)}
      {soon.length ? <T w="bold" size={18}>Coming up</T> : null}
      {soon.map(e => <EventCard key={e.id} e={e} d={d} c={c} own={own} />)}
      <T mute size={11.5}>Events from Bandai’s official pages (Oceania). Check with your store: prizes and dates can differ by store.</T>
      <View style={{ gap: 4, marginTop: 8 }}>
        <T w="bold" size={18}>Every promo card</T>
        <T mute size={13}>{`${promos.length >= 150 ? 'Top 150' : promos.length} promo cards${d.session ? ` · you own ${mine} ${mine === 1 ? 'entry' : 'entries'}` : ''}`}</T>
      </View>
      <SearchBar value={q} onChangeText={setQ} placeholder="Search promos: P-101, Luffy, Sabo…" />
      <ChipRow>{[['price', 'Highest price'], ['move', 'Moved this week'], ['new', 'Newest']].map(([v, l]) => <Chip key={v} on={sort === v} onPress={() => setSort(v)}>{l}</Chip>)}</ChipRow>
    </View>
  );
  return (
    <FlatList style={{ backgroundColor: c.bg, width: '100%', maxWidth: 820, alignSelf: 'center' }} data={promos} keyExtractor={x => x.k}
      ListHeaderComponent={header} renderItem={({ item }) => <CardRow card={item} showSet />} contentContainerStyle={{ paddingBottom: 60 }} />
  );
}
