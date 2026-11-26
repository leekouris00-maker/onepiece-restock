// Ban & Meta Radar (26 Nov 2026): what changed in the game and what it means for YOUR cards.
// Shown as the Meta tab of Market. Ban list + news from game.json (Bandai), winning decks from meta.json (Limitless TCG, weekly).
import React, { useMemo } from 'react';
import { Linking, Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, useData, useTrack } from './data';
import { useTheme } from './theme';
import { CardArt, Panel, T } from './ui';
import { usePref } from './prefs';
import { affected, banText, cardsFor, myNums, nameFor, newsWithin, niceDate, todayIso, useGame } from './game';

const pct = v => `${Math.round((v || 0) * 100)}%`;

export function MetaView() {
  const d = useData(), c = useTheme();
  const { game, meta, metaError, ready } = useGame();
  const [deckText] = usePref('deckText', '');
  useTrack('meta');
  const { own, deck } = useMemo(() => myNums(d, deckText), [d.owned, d.cat, deckText]);
  const hits = useMemo(() => affected(game, own, deck), [game, own, deck]);
  const news = newsWithin(game, 60);
  const open = num => { const x = cardsFor(d, num)[0]; if (x) router.push({ pathname: '/card/[k]', params: { k: x.k } }); };
  const price = num => { const x = cardsFor(d, num)[0]; return x && x.m ? d.money(x.m) : ''; };
  const move = num => { const x = cardsFor(d, num)[0]; return x ? d.move(x) : null; };

  return (
    <View style={{ gap: 14, marginTop: 14 }}>
      <T mute size={14}>What changed in the game, and what it means for your cards.</T>
      {!ready ? <T mute>Loading…</T> : null}

      {/* affects you */}
      {game ? <Panel title="Affects you">
        {!d.session ? <T mute size={13.5}>Sign in and add cards (or paste a deck into Deck price) to see which of yours are affected.</T>
          : !hits.length ? <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}><Ionicons name="checkmark-circle" size={20} color={c.accent} /><T size={14}>None of your cards or your saved deck are on the ban list.</T></View>
          : hits.map(h => (
            <Pressable key={h.num} onPress={() => open(h.num)} style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
              <CardArt k={cardsFor(d, h.num)[0]?.k} num={h.num} width={34} />
              <View style={{ flex: 1 }}>
                <T w="semi" size={14}>{`${nameFor(d, h.num)} · ${h.num}`}</T>
                <T size={12.5} style={{ color: h.clash ? c.down : c.mute }}>{banText(h.info)}</T>
                <T mute size={11.5}>{[h.owned ? 'In your collection' : null, h.inDeck ? 'In your saved deck' : null, h.clash ? 'Your deck breaks this rule' : null].filter(Boolean).join(' · ')}</T>
              </View>
              <T size={13} w="semi">{price(h.num)}</T>
            </Pressable>
          ))}
        {deck.size === 0 && d.session ? <Pressable onPress={() => router.push('/deck')}><T size={12.5} style={{ color: c.accent }}>Paste your deck into Deck price to check it too ›</T></Pressable> : null}
      </Panel> : null}

      {/* news */}
      {news.length ? <Panel title="Latest changes">
        {news.map(n => (
          <View key={n.id} style={{ gap: 4, paddingVertical: 4 }}>
            <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
              <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: n.effective > todayIso() ? c.accentDim : c.soft }}>
                <T size={11.5} w="bold" style={{ color: n.effective > todayIso() ? c.accent : c.mute }}>{n.effective > todayIso() ? `FROM ${niceDate(n.effective).toUpperCase()}` : `SINCE ${niceDate(n.effective).toUpperCase()}`}</T>
              </View>
              <T mute size={11.5}>{`Announced ${niceDate(n.announced)}`}</T>
            </View>
            <T w="semi" size={14.5}>{n.title}</T>
            <T mute size={13}>{n.body}</T>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 2 }}>
              {(n.cards || []).map(num => (
                <Pressable key={num} onPress={() => open(num)} style={{ paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: c.soft }}>
                  <T size={12.5}>{`${num} ${price(num)}`}{move(num) != null ? <T size={12} style={{ color: move(num) >= 0 ? c.up : c.down }}>{` ${move(num) >= 0 ? '▲' : '▼'}${Math.abs(move(num)).toFixed(0)}%`}</T> : null}</T>
                </Pressable>
              ))}
            </View>
            {n.url ? <Pressable onPress={() => Linking.openURL(n.url)}><T size={12.5} style={{ color: c.accent }}>Bandai’s notice ›</T></Pressable> : null}
          </View>
        ))}
      </Panel> : null}

      {/* meta */}
      <Panel title="What’s winning" right={meta ? <T mute size={12}>{`last ${meta.window_days} days · ${meta.decks_now} top-${meta.top} decks`}</T> : null}>
        {!meta ? <T mute size={13.5}>{metaError ? 'Tournament data isn’t available yet (the data source needs an access key).' : 'Tournament results arrive with the weekly update.'}</T> : <>
          <T mute size={12.5}>Leaders in the top 8 of online tournaments, and how that changed from the two weeks before.</T>
          {meta.leaders.slice(0, 8).map(l => (
            <View key={l.name} style={{ gap: 4 }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
                <T size={13.5} style={{ flex: 1 }} numberOfLines={1}>{l.name}</T>
                <T w="semi" size={13.5}>{pct(l.share)}</T>
                <T size={12} style={{ width: 56, textAlign: 'right', color: l.share >= l.prev ? c.up : c.down }}>{`${l.share >= l.prev ? '▲' : '▼'}${Math.abs(Math.round((l.share - l.prev) * 100))}`}</T>
              </View>
              <View style={{ height: 5, borderRadius: 3, backgroundColor: c.soft }}><View style={{ width: pct(l.share), height: 5, borderRadius: 3, backgroundColor: c.accent }} /></View>
            </View>
          ))}
          {meta.rising.length ? <>
            <T w="semi" size={14.5} style={{ marginTop: 8 }}>Cards showing up more</T>
            <T mute size={12}>Share of top decks playing the card, now vs before. Prices often follow.</T>
            {meta.rising.slice(0, 10).map(r => (
              <Pressable key={r.num} onPress={() => open(r.num)} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                <CardArt k={cardsFor(d, r.num)[0]?.k} num={r.num} width={30} />
                <View style={{ flex: 1 }}>
                  <T size={13.5} numberOfLines={1}>{nameFor(d, r.num)}</T>
                  <T mute size={11.5}>{`${r.num} · in ${pct(r.rate)} of top decks (was ${pct(r.prev)})`}{own.has(r.num) ? ' · you own it' : ''}</T>
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <T size={13} w="semi">{price(r.num)}</T>
                  {move(r.num) != null ? <T size={11.5} style={{ color: move(r.num) >= 0 ? c.up : c.down }}>{`${move(r.num) >= 0 ? '▲' : '▼'}${Math.abs(move(r.num)).toFixed(1)}% 7d`}</T> : null}
                </View>
              </Pressable>
            ))}
          </> : null}
          <Pressable onPress={() => Linking.openURL(meta.source_url)}><T mute size={11.5}>{`Data: Limitless TCG (online community events; official paper events aren’t included). Updated ${new Date(meta.updated).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}.`}</T></Pressable>
        </>}
      </Panel>

      {/* the list */}
      {game ? <Panel title="Current ban list">
        <T w="semi" size={13.5}>Banned (can’t be in any deck)</T>
        {(game.banned || []).map(b => (
          <Pressable key={b.num} onPress={() => open(b.num)} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
            <T size={13.5} style={{ flex: 1 }}>{`${b.name} · ${b.num}`}{own.has(b.num) ? <T size={12} style={{ color: c.gold }}>  you own it</T> : null}</T>
            <T mute size={12.5}>{b.since ? `since ${niceDate(b.since)}` : ''}</T>
          </Pressable>
        ))}
        <T w="semi" size={13.5} style={{ marginTop: 6 }}>Banned pairs (can’t be in the same deck)</T>
        {(game.pairs || []).map((p, i) => (
          <T key={i} size={13.5}>{`${p.a.name} (${p.a.num}) + ${p.b.map(b => `${b.name} (${b.num})`).join(' or ')}`}{p.since && p.since > todayIso() ? <T size={12} style={{ color: c.accent }}>{`  from ${niceDate(p.since)}`}</T> : null}</T>
        ))}
        <T mute size={12.5}>{(game.restricted || []).length ? '' : 'Restricted cards: none right now.'}</T>
        <Pressable onPress={() => Linking.openURL(game.banlist_url)}><T size={12.5} style={{ color: c.accent }}>{`Bandai’s official list ›  (checked ${niceDate(game.updated)})`}</T></Pressable>
      </Panel> : null}

    </View>
  );
}
