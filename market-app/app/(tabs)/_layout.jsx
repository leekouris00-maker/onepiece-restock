import React from 'react';
import { Pressable, View } from 'react-native';
import { Tabs, router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { F, useTheme } from '../../src/theme';
import { T } from '../../src/ui';
import { SIDE, useWide } from '../../src/layout';

const ICONS = { index: 'home', search: 'search', market: 'compass', portfolio: 'albums', account: 'person' };

const goTo = r => router.navigate(r.name === 'index' ? '/' : '/' + r.name);

// Computer: a sidebar down the left with the logo and the five sections
function Side({ state, descriptors }) {
  const c = useTheme();
  return (
    <View style={{ width: SIDE, backgroundColor: c.bg, borderRightWidth: 1, borderRightColor: c.line, paddingTop: 26, paddingHorizontal: 14, gap: 4 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 10, marginBottom: 22 }}>
        <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="compass" size={19} color={c.onAccent} />
        </View>
        <T head size={14} style={{ letterSpacing: 0.4 }}>ONE PIECE MARKET</T>
      </View>
      {state.routes.map((r, i) => {
        const on = state.index === i, label = descriptors[r.key].options.title ?? r.name;
        return (
          <Pressable key={r.key} onPress={() => { if (!on) goTo(r); }} accessibilityRole="tab" accessibilityState={{ selected: on }} accessibilityLabel={label}
            style={({ pressed, hovered }) => ({ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11, paddingHorizontal: 12, borderRadius: 12,
              backgroundColor: on ? c.accentDim : pressed || hovered ? c.soft : 'transparent' })}>
            <Ionicons name={ICONS[r.name] + (on ? '' : '-outline')} size={20} color={on ? c.accent : c.mute} />
            <T w={on ? 'bold' : 'medium'} size={15} style={{ color: on ? c.accent : c.ink }}>{label}</T>
          </Pressable>
        );
      })}
    </View>
  );
}

// Phone: quiet bar along the bottom: icons with small labels, the active one in lime
function Bar({ state, descriptors }) {
  const c = useTheme(), ins = useSafeAreaInsets();
  return (
    <View style={{ backgroundColor: c.bg, borderTopWidth: 1, borderTopColor: c.line, paddingBottom: Math.max(ins.bottom, 8) }}>
      <View style={{ flexDirection: 'row', width: '100%', maxWidth: 640, alignSelf: 'center' }}>
        {state.routes.map((r, i) => {
          const on = state.index === i, label = descriptors[r.key].options.title ?? r.name;
          const go = () => { if (!on) goTo(r); };
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
  const c = useTheme(), wide = useWide();
  return (
    <Tabs tabBar={p => (wide ? <Side {...p} /> : <Bar {...p} />)}
      screenOptions={{ headerShown: false, tabBarPosition: wide ? 'left' : 'bottom', sceneStyle: { backgroundColor: c.bg } }}>
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="search" options={{ title: 'Search' }} />
      <Tabs.Screen name="market" options={{ title: 'Market' }} />
      <Tabs.Screen name="portfolio" options={{ title: 'Collection' }} />
      <Tabs.Screen name="account" options={{ title: 'Profile' }} />
    </Tabs>
  );
}
