import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { useData, clean } from './data';
import { useTheme } from './theme';
import { Bounty, CardArt, T } from './ui';

export function CardRow({ card, showSet }) {
  const d = useData(), c = useTheme();
  const sl = d.salesOf(card.k), last = sl[0], cp = d.compOf(card.k), mv = d.move(card), own = d.owned.filter(o => o.card === card.k && o.status !== 'sold').reduce((n, o) => n + (Number(o.qty) || 1), 0);
  const ebay = last ? d.money(d.toUsd(last.price, last.cur)) : cp ? d.money(cp.median) : null;
  return (
    <Pressable onPress={() => router.push({ pathname: '/card/[k]', params: { k: card.k } })} accessibilityRole="button"
      style={({ pressed }) => ({ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 10, paddingHorizontal: 18,
        borderBottomWidth: 1, borderBottomColor: c.line, backgroundColor: pressed ? c.hi : 'transparent' })}>
      <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={44} />
      <View style={{ flex: 1, gap: 2 }}>
        <T size={15} w="semi" numberOfLines={2}>{clean(card.n)}</T>
        <T size={12.5} mute numberOfLines={1}>
          {[card.num, card.r, showSet ? (card.mine ? card.setName : d.cat?.byId[card.g]?.code) : null].filter(Boolean).join(' · ')}
        </T>
        {own ? <T size={12} style={{ color: c.accent }}>In your collection ×{own}</T> : null}
      </View>
      <View style={{ alignItems: 'flex-end', gap: 4 }}>
        <Bounty size={15}>{card.mine ? (ebay || '–') : d.money(card.m)}</Bounty>
        {mv != null && Math.abs(mv) >= 0.05 ? <T size={12} w="semi" style={{ color: mv > 0 ? c.up : c.down }}>{mv > 0 ? '▲' : '▼'} {Math.abs(mv).toFixed(1)}%</T>
          : !card.mine && ebay ? <T size={12} mute>eBay {ebay}</T> : null}
      </View>
    </Pressable>
  );
}
