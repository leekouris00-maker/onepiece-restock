import React from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useTheme } from './theme';
import { T } from './ui';

export const BAR_SPACE = 30;

export function useTop() { const ins = useSafeAreaInsets(); return ins.top + 10; }

export function Screen({ children, onRefresh, refreshing, max = 1100, pad = 18, ...p }) {
  const c = useTheme(), top = useTop();
  return (
    <ScrollView keyboardShouldPersistTaps="handled" {...p}
      contentContainerStyle={{ paddingTop: top, paddingHorizontal: pad, paddingBottom: BAR_SPACE, maxWidth: max, width: '100%', alignSelf: 'center' }}
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={c.accent} /> : undefined}>
      {children}
    </ScrollView>
  );
}

export function Title({ children, right, sub }) {
  return (
    <View style={{ marginBottom: 6 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10, minHeight: 40 }}>
        <T head size={28}>{children}</T>{right}
      </View>
      {sub ? <T mute size={13} style={{ marginTop: 2 }}>{sub}</T> : null}
    </View>
  );
}

export function Heading({ children, right, style, onMore, more = 'See all' }) {
  const c = useTheme();
  return (
    <View style={[{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }, style]}>
      <T w="bold" size={17}>{children}</T>
      {right || (onMore ? <Pressable onPress={onMore} hitSlop={10}><T w="semi" size={13.5} style={{ color: c.accent }}>{more}</T></Pressable> : null)}
    </View>
  );
}

// Plain round icon button for headers
export function IconBtn({ icon, onPress, label, on }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label} hitSlop={6}
      style={({ pressed }) => ({ width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed || on ? c.raise : c.soft })}>
      <Ionicons name={icon} size={20} color={on ? c.accent : c.ink} />
    </Pressable>
  );
}
