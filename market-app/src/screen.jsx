import React from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from './theme';
import { T } from './ui';

export const BAR_SPACE = 110; // room for the floating tab bar

export function useTop() { const ins = useSafeAreaInsets(); return ins.top + 10; }

export function Screen({ children, onRefresh, refreshing, max = 1100, pad = 18, ...p }) {
  const c = useTheme(), top = useTop();
  return (
    <ScrollView keyboardShouldPersistTaps="handled" {...p}
      contentContainerStyle={{ paddingTop: top, paddingHorizontal: pad, paddingBottom: BAR_SPACE, maxWidth: max, width: '100%', alignSelf: 'center' }}
      refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={c.mute} /> : undefined}>
      {children}
    </ScrollView>
  );
}

export function Heading({ children, right, style }) {
  return (
    <View style={[{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }, style]}>
      <T w="bold" size={21}>{children}</T>{right}
    </View>
  );
}
