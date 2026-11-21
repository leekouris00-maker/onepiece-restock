import React from 'react';
import { Pressable, View } from 'react-native';
import { Tabs, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { F, useTheme } from '../../src/theme';
import { T } from '../../src/ui';

const ICONS = { index: 'home', search: 'search', market: 'compass', portfolio: 'albums', account: 'person' };

// Solid bar along the bottom; the active tab gets a gold notch on top
function Bar({ state, descriptors }) {
  const c = useTheme(), ins = useSafeAreaInsets();
  return (
    <View style={{ backgroundColor: c.panel, borderTopWidth: 1, borderTopColor: c.line, paddingBottom: Math.max(ins.bottom, 8) }}>
      <View style={{ flexDirection: 'row', width: '100%', maxWidth: 640, alignSelf: 'center' }}>
        {state.routes.map((r, i) => {
          const on = state.index === i, label = descriptors[r.key].options.title ?? r.name;
          const go = () => { if (!on) router.navigate(r.name === 'index' ? '/' : '/' + r.name); };
          return (
            <Pressable key={r.key} onPress={go} accessibilityRole="tab" accessibilityState={{ selected: on }} accessibilityLabel={label}
              style={{ flex: 1, alignItems: 'center', paddingTop: 9, paddingBottom: 4, gap: 3 }}>
              <View style={{ position: 'absolute', top: -1, width: 28, height: 3, borderRadius: 2, backgroundColor: on ? c.accent : 'transparent' }} />
              <Ionicons name={ICONS[r.name] + (on ? '' : '-outline')} size={23} color={on ? c.accent : c.mute} />
              <T size={11} caps style={{ color: on ? c.accent : c.mute, fontFamily: on ? F.head : F.headMed, letterSpacing: 0.8 }}>{label}</T>
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
