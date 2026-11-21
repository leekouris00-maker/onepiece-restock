import React from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from './theme';
import { T } from './ui';

export const BAR_SPACE = 36; // the tab bar sits below the content, so only a little room is needed

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

// Big condensed page title, gold rule underneath
export function Title({ children, right, sub }) {
  const c = useTheme();
  return (
    <View style={{ borderBottomWidth: 1, borderBottomColor: c.line, paddingBottom: 12, marginBottom: 4 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <T head caps size={30} style={{ letterSpacing: 1.5 }}>{children}</T>{right}
      </View>
      {sub ? <T mute size={13} style={{ marginTop: 2 }}>{sub}</T> : null}
      <View style={{ width: 44, height: 3, backgroundColor: c.accent, borderRadius: 2, marginTop: 10 }} />
    </View>
  );
}

export function Heading({ children, right, style, onMore, more = 'View all' }) {
  const c = useTheme();
  return (
    <View style={[{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }, style]}>
      <T head caps size={19} style={{ letterSpacing: 1.2 }}>{children}</T>
      {right || (onMore ? <Pressable onPress={onMore} hitSlop={10}><T head caps size={13} style={{ color: c.accent, letterSpacing: 1 }}>{more} ›</T></Pressable> : null)}
    </View>
  );
}
