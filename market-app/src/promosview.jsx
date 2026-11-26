// Promos (26 Nov 2026): shown as the Promos tab of Market.
// Official events on now / coming up as one line each (tap for the prizes), then every promo card by price.
// Events from game.json (kept from Bandai's event pages).
import React, { useMemo, useState } from 'react';
import { Linking, Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, useData, useTrack } from './data';
import { useTheme } from './theme';
import { Chip, Panel, SearchBar, T } from './ui';
import { ChipRow } from './screen';
import { CardRow } from './rows';
import { cardsFor, eventsNow, eventsSoon, myNums, niceDate, useGame } from './game';

const prizeCard = (d, e) => (e.prizes || []).flatMap(p => p.cards || []).map(num => cardsFor(d, num)[0]).filter(Boolean)[0];

function EventRow({ e, d, c, own, soon, last }) {
  const [open, setOpen] = useState(false);
  const top = prizeCard(d, e);
  const go = num => { const x = cardsFor(d, num)[0]; if (x) router.push({ pathname: '/card/[k]', params: { k: x.k } }); };
  return (
    <View style={{ borderBottomWidth: last ? 0 : 1, borderBottomColor: c.line }}>
      <Pressable onPress={() => setOpen(o => !o)} accessibilityRole="button" accessibilityLabel={e.name}
        style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 56, paddingVertical: 8 }}>
        <View style={{ flex: 1, minWidth: 0 }}>
          <T w="semi" size={14.5} numberOfLines={1}>{e.name}</T>
          <T mute size={12.5} numberOfLines={1}>{`${soon ? `From ${niceDate(e.start)}` : `Until ${niceDate(e.end)}`}${top ? ` · ${top.num}` : ''}`}</T>
        </View>
        {top && top.m ? <T w="bold" size={14}>{d.money(top.m)}</T> : null}
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={17} color={c.mute} />
      </Pressable>
      {open ? <View style={{ gap: 8, paddingBottom: 12 }}>
        <T mute size={12.5}>{e.where}</T>
        {e.prizes.map((p, i) => (
          <View key={i} style={{ gap: 4 }}>
            <T size={13.5}><T w="semi" size={13.5}>{p.who}: </T>{p.what}</T>
            {(p.cards || []).map(num => { const l = cardsFor(d, num); return /winner|champion|top/i.test(p.who) ? l[0] : l[l.length - 1]; }).filter(Boolean).map(x => (
              <Pressable key={x.k} onPress={() => go(x.num)} style={{ flexDirection: 'row', gap: 10, paddingLeft: 10 }}>
                <T size={13} style={{ flex: 1 }} numberOfLines={1}>{clean(x.n)}</T>
                {own.has(String(x.num).toUpperCase()) ? <T size={11.5} style={{ color: c.gold }}>you own one</T> : null}
                <T w="semi" size={13}>{x.m ? d.money(x.m) : '–'}</T>
              </Pressable>
            ))}
          </View>
        ))}
        <Pressable onPress={() => Linking.openURL(e.url)}><T size={13} style={{ color: c.accent }}>Event page and how to enter ›</T></Pressable>
      </View> : null}
    </View>
  );
}

export function PromosView() {
  const d = useData(), c = useTheme();
  const { game, ready } = useGame();
  useTrack('promos');
  const [q, setQ] = useState('');
  const [sort, setSort] = useState('price');
  const [more, setMore] = useState(false);
  const { own } = useMemo(() => myNums(d, ''), [d.owned, d.cat]);
  const now = eventsNow(game), soon = eventsSoon(game);
  const promos = useMemo(() => {
    if (!d.cat) return [];
    const s = q.trim().toLowerCase();
    const l = d.cat.list.filter(x => /^P-\d{3}$/i.test(String(x.num || '')) && x.t !== 'sealed' && (!s || `${x.n} ${x.num}`.toLowerCase().includes(s)));
    return l.sort((a, b) => (sort === 'price' ? (b.m || 0) - (a.m || 0) : (d.move(b) ?? -999) - (d.move(a) ?? -999)));
  }, [d.cat, q, sort]);
  const shown = promos.slice(0, more ? 150 : 30);
  const events = [...now.map(e => [e, false]), ...soon.map(e => [e, true])];

  return (
    <View style={{ gap: 14, marginTop: 14 }}>
      {!ready ? <T mute>Loading…</T> : null}
      {events.length ? <Panel title="Prize events" style={{ gap: 0 }}>
        {events.map(([e, isSoon], i) => <EventRow key={e.id} e={e} d={d} c={c} own={own} soon={isSoon} last={i === events.length - 1} />)}
      </Panel> : null}
      <View style={{ gap: 10 }}>
        <T w="bold" size={18}>All promo cards</T>
        <SearchBar value={q} onChangeText={setQ} placeholder="Search promos: P-101, Luffy, Sabo…" />
        <ChipRow>{[['price', 'Highest price'], ['move', 'Moved this week']].map(([v, l]) => <Chip key={v} on={sort === v} onPress={() => setSort(v)}>{l}</Chip>)}</ChipRow>
      </View>
      <View style={{ marginHorizontal: -18 }}>{shown.map(x => <CardRow key={x.k} card={x} showSet />)}</View>
      {promos.length > shown.length ? <Pressable onPress={() => setMore(true)} style={{ alignItems: 'center', paddingVertical: 10 }}><T w="semi" style={{ color: c.accent }}>{`Show more (${Math.min(150, promos.length)})`}</T></Pressable> : null}
    </View>
  );
}
