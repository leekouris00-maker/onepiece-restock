// eBay deals found for your deal alerts (deal_alerts.py on GitHub, every 2 hours)
import React, { useEffect, useState } from 'react';
import { Linking, Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { Image } from 'expo-image';
import { useData } from './data';
import { useTheme } from './theme';
import { Heading } from './screen';
import { T, ago } from './ui';

export function useDeals() {
  const d = useData();
  const [list, setList] = useState(null), [err, setErr] = useState('');
  const load = () => d.listDeals().then(l => { setList(l); setErr(''); }, e => { setErr(e.message); setList([]); });
  useEffect(() => { if (d.session) load(); }, [d.session]);
  return { list, err, reload: load, setList };
}

export function DealRow({ x, onDismiss }) {
  const d = useData(), c = useTheme();
  const card = d.card(x.card);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 }}>
      <Pressable onPress={() => x.url && Linking.openURL(x.url)} accessibilityRole="link" style={({ pressed }) => ({ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, opacity: pressed ? 0.6 : 1 })}>
        <View style={{ width: 44, height: 44, borderRadius: 8, overflow: 'hidden', backgroundColor: c.raise }}>
          {x.image ? <Image source={{ uri: x.image }} style={{ width: 44, height: 44 }} contentFit="cover" /> : null}
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <T w="semi" size={13.5} numberOfLines={2}>{x.title}</T>
          <T mute size={12}>{[card?.num, ago(String(x.found_at).slice(0, 10)), card && card.m != null ? `market ${d.money(card.m)}` : null].filter(Boolean).join(' · ')}</T>
        </View>
        <T w="bold" size={15} style={{ color: c.accent }}>A${Number(x.price).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</T>
      </Pressable>
      {onDismiss ? <Pressable onPress={() => onDismiss(x)} hitSlop={8} accessibilityLabel="Dismiss"><T mute size={18}>×</T></Pressable> : null}
    </View>
  );
}

// Home: deals from the last 3 days
export function DealsPanel() {
  const c = useTheme();
  const { list } = useDeals();
  const recent = (list || []).filter(x => Date.now() - new Date(x.found_at).getTime() < 3 * 864e5).slice(0, 4);
  if (!recent.length) return null;
  return (
    <View style={{ borderRadius: 20, padding: 16, gap: 4, backgroundColor: c.panel, marginTop: 14 }}>
      <Heading onMore={() => router.push('/deals')}>New eBay deals</Heading>
      {recent.map(x => <DealRow key={x.item_id} x={x} />)}
    </View>
  );
}
