import React from 'react';
import { Pressable, View } from 'react-native';
import { Tabs, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { F, useTheme } from '../../src/theme';
import { T } from '../../src/ui';

const ICONS = { index: 'home', search: 'search', market: 'storefront', portfolio: 'albums', account: 'person' };

// Floating rounded bar, the active tab sits in a soft pill
function Bar({ state, descriptors }) {
  const c = useTheme(), ins = useSafeAreaInsets();
  return (
    <View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, bottom: 0, paddingBottom: Math.max(ins.bottom, 12), paddingHorizontal: 12, alignItems: 'center' }}>
      <View style={{ flexDirection: 'row', width: '100%', maxWidth: 560, backgroundColor: c.panel, borderRadius: 999, borderWidth: 1, borderColor: c.line, padding: 6,
        shadowColor: '#000', shadowOpacity: 0.6, shadowRadius: 18, shadowOffset: { width: 0, height: 6 }, elevation: 12 }}>
        {state.routes.map((r, i) => {
          const on = state.index === i, label = descriptors[r.key].options.title ?? r.name;
          const go = () => { if (!on) router.navigate(r.name === 'index' ? '/' : '/' + r.name); };
          return (
            <Pressable key={r.key} onPress={go} accessibilityRole="tab" accessibilityState={{ selected: on }} accessibilityLabel={label}
              style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 8, borderRadius: 999, gap: 2, backgroundColor: on ? c.raise : 'transparent' }}>
              <Ionicons name={ICONS[r.name] + (on ? '' : '-outline')} size={23} color={on ? c.accent : c.ink} />
              <T size={11.5} style={{ color: on ? c.accent : c.ink, fontFamily: on ? F.semi : F.text }}>{label}</T>
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
      <Tabs.Screen name="portfolio" options={{ title: 'Portfolio' }} />
      <Tabs.Screen name="account" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
