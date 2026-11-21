import React from 'react';
import { Pressable, View } from 'react-native';
import { Tabs, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { F, useTheme } from '../../src/theme';
import { T } from '../../src/ui';

const ICONS = { index: 'home', search: 'search', market: 'compass', portfolio: 'albums', account: 'person' };

// Quiet bar along the bottom: icons with small labels, the active one in lime
function Bar({ state, descriptors }) {
  const c = useTheme(), ins = useSafeAreaInsets();
  return (
    <View style={{ backgroundColor: c.bg, borderTopWidth: 1, borderTopColor: c.line, paddingBottom: Math.max(ins.bottom, 8) }}>
      <View style={{ flexDirection: 'row', width: '100%', maxWidth: 640, alignSelf: 'center' }}>
        {state.routes.map((r, i) => {
          const on = state.index === i, label = descriptors[r.key].options.title ?? r.name;
          const go = () => { if (!on) router.navigate(r.name === 'index' ? '/' : '/' + r.name); };
          return (
            <Pressable key={r.key} onPress={go} accessibilityRole="tab" accessibilityState={{ selected: on }} accessibilityLabel={label}
              style={{ flex: 1, alignItems: 'center', paddingTop: 10, paddingBottom: 4, gap: 3 }}>
              <Ionicons name={ICONS[r.name] + (on ? '' : '-outline')} size={22} color={on ? c.accent : c.mute} />
              <T size={11} style={{ color: on ? c.accent : c.mute, fontFamily: on ? F.bold : F.medium }}>{label}</T>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export default function TabsLayout() {
  const c = useTheme();
  return (
    <Tabs tabBar={p => <Bar {...p} />} screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: c.bg } }}>
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="search" options={{ title: 'Search' }} />
      <Tabs.Screen name="market" options={{ title: 'Market' }} />
      <Tabs.Screen name="portfolio" options={{ title: 'Collection' }} />
      <Tabs.Screen name="account" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
