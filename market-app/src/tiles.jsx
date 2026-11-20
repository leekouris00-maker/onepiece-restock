import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { useData, clean } from './data';
import { useTheme } from './theme';
import { CardArt, Change, T } from './ui';

export function setNameOf(d, card, o) {
  if (card?.mine) return card.setName || 'My cards';
  if (card) return d.cat?.byId[card.g]?.name || '';
  return o?.group || '';
}

const openItem = o => router.push({ pathname: '/item/[id]', params: { id: o.id } });
const openCard = k => router.push({ pathname: '/card/[k]', params: { k } });

// Big portfolio tile: picture, name, set, rarity • number, condition • language, qty and price with its 7-day change
export function OwnedTile({ o, width }) {
  const d = useData(), c = useTheme();
  const card = d.card(o.card), q = Number(o.qty) || 1, sold = o.status === 'sold';
  const now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  const code = [card?.r, card?.num || o.num].filter(Boolean).join(' • ');
  const cond = [o.cond, o.lang].filter(Boolean).join(' • ') || o.kind;
  return (
    <Pressable onPress={() => openItem(o)} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 3, opacity: pressed ? 0.7 : 1 })}>
      <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num || (o.kind === 'Sealed' ? 'Sealed' : '')} width={width} big />
      <T w="bold" size={15.5} numberOfLines={2} style={{ marginTop: 8 }}>{clean(o.name)}</T>
      <T size={13.5} mute numberOfLines={1}>{setNameOf(d, card, o)}</T>
      {code ? <T size={13.5} mute numberOfLines={1}>{code}</T> : null}
      {cond ? <T size={13.5} numberOfLines={1} style={{ color: c.accent }}>{cond}</T> : null}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 2 }}>
        <T size={13.5} mute>Qty: {q}</T>
        <T w="bold" size={16}>{sold ? d.aud(Number(o.soldFor) || 0) : d.aud(now)}</T>
      </View>
      {sold ? <T size={13} mute style={{ textAlign: 'right' }}>sold</T>
        : <View style={{ alignItems: 'flex-end' }}><Change now={now} then={then} aud={d.aud} size={13} /></View>}
    </Pressable>
  );
}

// Carousel tile for any card in the market
export function CardTile({ card, width = 132 }) {
  const d = useData();
  const mv = d.move(card), now = card.m, then = mv == null ? null : now / (1 + mv / 100);
  return (
    <Pressable onPress={() => openCard(card.k)} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 3, opacity: pressed ? 0.7 : 1 })}>
      <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={width} big />
      <T w="semi" size={14} numberOfLines={2} style={{ marginTop: 6 }}>{clean(card.n)}</T>
      <T size={12.5} mute numberOfLines={1}>{[card.r, card.num].filter(Boolean).join(' • ')}</T>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: 4 }}>
        <T w="bold" size={15}>{d.money(card.m)}</T>
        <Change now={now} then={then} aud={d.aud} size={12} pctOnly />
      </View>
    </Pressable>
  );
}

// Row for the Most Valuable list
export function OwnedRow({ o, rank }) {
  const d = useData(), c = useTheme();
  const card = d.card(o.card), q = Number(o.qty) || 1, now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  return (
    <Pressable onPress={() => openItem(o)} accessibilityRole="button"
      style={({ pressed }) => ({ flexDirection: 'row', gap: 14, alignItems: 'center', paddingVertical: 10, backgroundColor: pressed ? c.soft : 'transparent', borderRadius: 12 })}>
      {rank ? <T w="bold" size={15} mute style={{ width: 18, textAlign: 'center' }}>{rank}</T> : null}
      <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num} width={52} />
      <View style={{ flex: 1, gap: 2 }}>
        <T w="semi" size={15} numberOfLines={1}>{clean(o.name)}</T>
        <T size={13} mute numberOfLines={1}>{[setNameOf(d, card, o), card?.num || o.num].filter(Boolean).join(' · ')}</T>
        <T size={13} style={{ color: c.accent }} numberOfLines={1}>Qty: {q}</T>
      </View>
      <View style={{ alignItems: 'flex-end', gap: 2 }}>
        <T w="bold" size={16}>{d.aud(now == null ? null : now * q)}</T>
        <Change now={now} then={then} aud={d.aud} size={12.5} pctOnly />
      </View>
    </Pressable>
  );
}
