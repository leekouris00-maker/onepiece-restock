import React from 'react';
import { View } from 'react-native';
import { useTheme } from './theme';

export function Progress({ v, h = 8 }) {
  const c = useTheme();
  return (
    <View style={{ height: h, borderRadius: h / 2, backgroundColor: c.raise, overflow: 'hidden' }} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(v * 100) }}>
      <View style={{ width: `${Math.max(0, Math.min(1, v)) * 100}%`, height: '100%', borderRadius: h / 2, backgroundColor: c.accent }} />
    </View>
  );
}
