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

// One owned item as a quiet list row: picture, name, number and set, value and weekly change
export function OwnedRow({ o, rank }) {
  const d = useData(), c = useTheme();
  const card = d.card(o.card), q = Number(o.qty) || 1, sold = o.status === 'sold';
  const now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  const sub = [card?.num || o.num, o.cond && o.cond !== 'Raw' ? o.cond : null, q > 1 ? `×${q}` : null].filter(Boolean).join(' · ');
  return (
    <Pressable onPress={() => openItem(o)} accessibilityRole="button"
      style={({ pressed }) => ({ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 9, opacity: pressed ? 0.6 : 1 })}>
      {rank ? <T w="bold" size={13} mute style={{ width: 16, textAlign: 'center' }}>{rank}</T> : null}
      <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num} width={38} />
      <View style={{ flex: 1, gap: 2 }}>
        <T w="semi" size={14.5} numberOfLines={1}>{clean(o.name)}</T>
        <T size={12.5} mute numberOfLines={1}>{sub || setNameOf(d, card, o)}</T>
      </View>
      <View style={{ alignItems: 'flex-end', gap: 2 }}>
        <T w="bold" size={14.5}>{sold ? d.aud((Number(o.soldFor) || 0) * q) : d.aud(now == null ? null : now * q)}</T>
        {sold ? <T size={12} mute>Sold</T> : <Change now={now} then={then} aud={d.aud} size={12} pctOnly />}
      </View>
    </Pressable>
  );
}

// Card-first tile for the grid view
export function OwnedTile({ o, width }) {
  const d = useData();
  const card = d.card(o.card), q = Number(o.qty) || 1, now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  return (
    <Pressable onPress={() => openItem(o)} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 3, opacity: pressed ? 0.7 : 1 })}>
      <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num || (o.kind === 'Sealed' ? 'Sealed' : '')} width={width} qty={q} big />
      <T w="semi" size={13} numberOfLines={1} style={{ marginTop: 6 }}>{clean(o.name)}</T>
      <T w="bold" size={14}>{d.aud(now == null ? null : now * q)}</T>
      <Change now={now} then={then} aud={d.aud} size={11.5} pctOnly />
    </Pressable>
  );
}

// Carousel tile for any card in the market
export function CardTile({ card, width = 120 }) {
  const d = useData();
  const mv = d.move(card), now = card.m, then = mv == null ? null : now / (1 + mv / 100);
  return (
    <Pressable onPress={() => openCard(card.k)} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 3, opacity: pressed ? 0.7 : 1 })}>
      <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={width} big />
      <T w="semi" size={13} numberOfLines={1} style={{ marginTop: 6 }}>{clean(card.n)}</T>
      <T size={12} mute numberOfLines={1}>{card.num}</T>
      <T w="bold" size={14}>{d.money(card.m)}</T>
      <Change now={now} then={then} aud={d.aud} size={11.5} pctOnly />
    </Pressable>
  );
}
