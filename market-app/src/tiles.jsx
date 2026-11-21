import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { useData, clean } from './data';
import { useTheme } from './theme';
import { Bounty, CardArt, Change, T } from './ui';

export function setNameOf(d, card, o) {
  if (card?.mine) return card.setName || 'My cards';
  if (card) return d.cat?.byId[card.g]?.name || '';
  return o?.group || '';
}

const openItem = o => router.push({ pathname: '/item/[id]', params: { id: o.id } });
const openCard = k => router.push({ pathname: '/card/[k]', params: { k } });

// One owned item as a ledger row: picture, name, set and number, condition, bounty and weekly change
export function OwnedRow({ o, rank, last }) {
  const d = useData(), c = useTheme();
  const card = d.card(o.card), q = Number(o.qty) || 1, sold = o.status === 'sold';
  const now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  const cond = [o.cond, o.lang].filter(Boolean).join(' · ');
  return (
    <Pressable onPress={() => openItem(o)} accessibilityRole="button"
      style={({ pressed }) => ({ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 11, backgroundColor: pressed ? c.soft : 'transparent',
        borderBottomWidth: last ? 0 : 1, borderBottomColor: c.line })}>
      {rank ? <T head size={18} style={{ width: 22, textAlign: 'center', color: rank <= 3 ? c.accent : c.mute }}>{rank}</T> : null}
      <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num} width={46} qty={q} />
      <View style={{ flex: 1, gap: 2 }}>
        <T w="semi" size={15} numberOfLines={1}>{clean(o.name)}</T>
        <T size={12.5} mute numberOfLines={1}>{[card?.num || o.num, setNameOf(d, card, o)].filter(Boolean).join(' · ')}</T>
        {cond ? <T size={12} numberOfLines={1} style={{ color: c.accent }}>{cond}{q > 1 ? ` · ${q} × ${d.aud(now)}` : ''}</T> : null}
      </View>
      <View style={{ alignItems: 'flex-end', gap: 4 }}>
        <Bounty size={15}>{sold ? d.aud((Number(o.soldFor) || 0) * q) : d.aud(now == null ? null : now * q)}</Bounty>
        {sold ? <T size={12} mute>sold</T> : <Change now={now} then={then} aud={d.aud} size={12} pctOnly />}
      </View>
    </Pressable>
  );
}

// Card-first tile for the grid view and podium
export function OwnedTile({ o, width, rank }) {
  const d = useData(), c = useTheme();
  const card = d.card(o.card), q = Number(o.qty) || 1, now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  return (
    <Pressable onPress={() => openItem(o)} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 6, opacity: pressed ? 0.7 : 1 })}>
      <View>
        <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num || (o.kind === 'Sealed' ? 'Sealed' : '')} width={width} qty={q} big framed={!!rank} />
        {rank ? <View style={{ position: 'absolute', left: -6, top: -6, width: 28, height: 28, borderRadius: 14, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: c.bg }}>
          <T head size={14} style={{ color: c.bg }}>{rank}</T></View> : null}
      </View>
      <T w="semi" size={13.5} numberOfLines={2}>{clean(o.name)}</T>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 4, flexWrap: 'wrap' }}>
        <Bounty size={14}>{d.aud(now == null ? null : now * q)}</Bounty>
        <Change now={now} then={then} aud={d.aud} size={11.5} pctOnly />
      </View>
    </Pressable>
  );
}

// Carousel tile for any card in the market
export function CardTile({ card, width = 128 }) {
  const d = useData();
  const mv = d.move(card), now = card.m, then = mv == null ? null : now / (1 + mv / 100);
  return (
    <Pressable onPress={() => openCard(card.k)} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 5, opacity: pressed ? 0.7 : 1 })}>
      <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={width} big />
      <T w="semi" size={13.5} numberOfLines={2}>{clean(card.n)}</T>
      <T size={12} mute numberOfLines={1}>{[card.num, card.r].filter(Boolean).join(' · ')}</T>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 4, flexWrap: 'wrap' }}>
        <Bounty size={14}>{d.money(card.m)}</Bounty>
        <Change now={now} then={then} aud={d.aud} size={11.5} pctOnly />
      </View>
    </Pressable>
  );
}
