import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData, clean } from './data';
import { useTheme } from './theme';
import { CardArt, T } from './ui';

export function CardRow({ card, showSet, onOpen, active }) {
  const d = useData(), c = useTheme();
  const sl = d.salesOf(card.k), last = sl[0], cp = d.compOf(card.k), mv = d.move(card), own = d.owned.filter(o => o.card === card.k && o.status !== 'sold').reduce((n, o) => n + (Number(o.qty) || 1), 0);
  const ebay = last ? d.money(d.toUsd(last.price, last.cur)) : cp ? d.money(cp.median) : null;
  return (
    <Pressable onPress={() => { onOpen && onOpen(); router.push({ pathname: '/card/[k]', params: { k: card.k } }); }} accessibilityRole="button"
      style={({ pressed, hovered }) => ({ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 9, paddingHorizontal: 18, opacity: pressed ? 0.6 : 1,
        borderRadius: 12, backgroundColor: active ? c.soft : hovered ? 'rgba(255,255,255,0.03)' : 'transparent', borderLeftWidth: 3, borderLeftColor: active ? c.accent : 'transparent' })}>
      <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={40} />
      <View style={{ flex: 1, gap: 2 }}>
        <T size={14.5} w="semi" numberOfLines={1}>{clean(card.n)}</T>
        <T size={12.5} mute numberOfLines={1}>
          {[card.num, card.r, showSet ? (card.mine ? card.setName : d.cat?.byId[card.g]?.code) : null].filter(Boolean).join(' · ')}
          {own ? <T size={12.5} style={{ color: c.accent }}>{'  ·  You own ' + own}</T> : null}
        </T>
      </View>
      <View style={{ alignItems: 'flex-end', gap: 2 }}>
        <T w="bold" size={14.5}>{card.mine ? (ebay || '–') : d.money(card.m)}</T>
        {mv != null && Math.abs(mv) >= 0.05 ? <T size={12} w="semi" style={{ color: mv > 0 ? c.up : c.down }}>{mv > 0 ? '▲ ' : '▼ '}{Math.abs(mv).toFixed(2)}%</T>
          : !card.mine && ebay ? <T size={12} mute>eBay {ebay}</T> : null}
      </View>
    </Pressable>
  );
}

export function SetRow({ set, count, active }) {
  const c = useTheme();
  return (
    <Pressable onPress={() => router.push({ pathname: '/set/[id]', params: { id: set.id } })} accessibilityRole="button"
      style={({ pressed, hovered }) => ({ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, paddingHorizontal: 18, opacity: pressed ? 0.6 : 1,
        borderRadius: 12, backgroundColor: active ? c.soft : hovered ? 'rgba(255,255,255,0.03)' : 'transparent', borderLeftWidth: 3, borderLeftColor: active ? c.accent : 'transparent' })}>
      <View style={{ width: 54, height: 36, borderRadius: 10, backgroundColor: c.soft, alignItems: 'center', justifyContent: 'center' }}>
        <T w="bold" size={11.5} style={{ color: c.accent }} numberOfLines={1}>{set.code}</T>
      </View>
      <View style={{ flex: 1 }}>
        <T w="semi" size={14.5} numberOfLines={1}>{set.name}</T>
        {set.date || count ? <T size={12} mute>{[set.date, count ? `${count} cards` : null].filter(Boolean).join(' · ')}</T> : null}
      </View>
      <Ionicons name="chevron-forward" size={16} color={c.mute} />
    </Pressable>
  );
}
