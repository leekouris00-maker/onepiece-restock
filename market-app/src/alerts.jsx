// Watchlist cards that crossed a price you set
import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, useData } from './data';
import { useTheme } from './theme';
import { CardArt, Panel, T } from './ui';

export function AlertList({ max }) {
  const d = useData(), c = useTheme();
  if (!d.alerts.length) return null;
  return (
    <Panel style={{ gap: 6, backgroundColor: c.accentDim }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name="notifications" size={18} color={c.accent} />
        <T w="bold" size={16} style={{ flex: 1 }}>Price alerts</T>
      </View>
      {d.alerts.slice(0, max || 99).map(({ f, c: card, a, dir, at }) => (
        <Pressable key={f.card} onPress={() => router.push({ pathname: '/card/[k]', params: { k: f.card } })} accessibilityRole="button"
          style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 6, opacity: pressed ? 0.6 : 1 })}>
          <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={34} />
          <View style={{ flex: 1 }}>
            <T w="semi" size={14} numberOfLines={1}>{clean(card.n)}</T>
            <T size={12.5} mute>{dir === 'below' ? `Dropped to ${d.aud(a)} · your alert ${d.aud(at)}` : `Rose to ${d.aud(a)} · your alert ${d.aud(at)}`}</T>
          </View>
          <Ionicons name={dir === 'below' ? 'trending-down' : 'trending-up'} size={20} color={dir === 'below' ? c.down : c.up} />
        </Pressable>
      ))}
    </Panel>
  );
}

