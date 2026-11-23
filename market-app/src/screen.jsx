import React, { useRef, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useTheme } from './theme';
import { T } from './ui';
import { useWide } from './layout';
import { haptic } from './haptic';
import { useData } from './data';

export const BAR_SPACE = 30;

export function useTop() { const ins = useSafeAreaInsets(), wide = useWide(); return ins.top + (wide ? 28 : 10); }

// Page that scrolls. Pull down from the top to refresh: the phone app's own pull on iPhone/Android,
// and a hand-made one in the browser / home-screen app (where the built-in one doesn't exist).
export function Screen({ children, onRefresh, refreshing, max = 1100, pad, after, ...p }) {
  const c = useTheme(), top = useTop(), wide = useWide();
  pad ??= wide ? 32 : 18;
  const web = Platform.OS === 'web';
  const y = useRef(0), start = useRef(null), [pull, setPull] = useState(0), [spin, setSpin] = useState(false);
  const PULL = 70;
  const touch = web && onRefresh && !wide ? {
    onTouchStart: e => { start.current = y.current <= 0 ? e.nativeEvent.touches[0].pageY : null; },
    onTouchMove: e => {
      if (start.current == null) return;
      const d = (e.nativeEvent.touches[0].pageY - start.current) * 0.5;
      if (d > 0 && y.current <= 0) { if (d >= PULL && pull < PULL) haptic(); setPull(Math.min(d, PULL * 1.4)); } else if (pull) setPull(0);
    },
    onTouchEnd: async () => {
      start.current = null;
      if (pull >= PULL) { setSpin(true); setPull(PULL * 0.7); try { await onRefresh(); } finally { setTimeout(() => { setSpin(false); setPull(0); }, 500); } }
      else setPull(0);
    },
  } : null;
  return (
    <View style={{ flex: 1 }}>
      {touch && (pull > 0 || spin) ? <View pointerEvents="none" style={{ position: 'absolute', top: top - 6 + Math.min(pull, PULL) * 0.4, left: 0, right: 0, alignItems: 'center', zIndex: 5 }}>
        <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: c.panel, alignItems: 'center', justifyContent: 'center' }}>
          {spin || refreshing ? <ActivityIndicator size="small" color={c.accent} />
            : <Ionicons name="arrow-down" size={18} color={pull >= PULL ? c.accent : c.mute} style={{ transform: [{ rotate: pull >= PULL ? '180deg' : '0deg' }] }} />}
        </View>
      </View> : null}
      <ScrollView keyboardShouldPersistTaps="handled" scrollEventThrottle={16} {...p} {...touch}
        onScroll={e => { y.current = e.nativeEvent.contentOffset.y; p.onScroll && p.onScroll(e); }}
        contentContainerStyle={{ paddingTop: top + (touch ? pull * 0.6 : 0), paddingHorizontal: pad, paddingBottom: wide ? 48 : BAR_SPACE + (after ? 70 : 0), maxWidth: max, width: '100%', alignSelf: 'center' }}
        refreshControl={onRefresh && !web ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={c.accent} /> : undefined}>
        <StatusNotes />
        {children}
      </ScrollView>
      {after}
    </View>
  );
}

// Offline / old-prices notes at the top of every page
export function StatusNotes() {
  const d = useData(), c = useTheme();
  if (!d) return null;
  const old = d.cat && d.cat.meta?.updated && (Date.now() - new Date(d.cat.meta.updated + 'T12:00:00').getTime()) / 864e5 > 2.5;
  const msg = d.offline ? `You’re offline. Showing saved prices${d.cat ? ` from ${d.cat.meta.updated}` : ''}${d.session ? ' and your saved collection' : ''}. Changes need signal.`
    : d.stale ? `Couldn’t update prices just now, so these are from ${d.cat?.meta?.updated || 'the last update'}. Pull down to try again.`
    : old ? `Prices were last updated ${d.cat.meta.updated}.` : null;
  if (!msg) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, paddingHorizontal: 12, borderRadius: 12, backgroundColor: c.soft, marginBottom: 12 }}>
      <Ionicons name={d.offline ? 'cloud-offline-outline' : 'time-outline'} size={16} color={c.mute} />
      <T size={12.5} mute style={{ flex: 1 }}>{msg}</T>
    </View>
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
      style={({ pressed }) => ({ width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed || on ? c.raise : c.soft })}>
      <Ionicons name={icon} size={20} color={on ? c.accent : c.ink} />
    </Pressable>
  );
}

// Chips: one scrolling row on a phone; wrapped onto as many lines as needed on a computer, where sideways scrolling is awkward
export function ChipRow({ children, pad = 0, style }) {
  const wide = useWide();
  if (wide) return <View style={[{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, paddingHorizontal: pad }, style]}>{children}</View>;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ gap: 8, paddingHorizontal: pad }} style={style}>
      {children}
    </ScrollView>
  );
}

// Card tiles: a sideways carousel on a phone; a wrapped grid on a computer
export function TileRail({ children, pad = 18 }) {
  const wide = useWide();
  if (wide) return <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 18, rowGap: 22, paddingVertical: 14 }}>{children}</View>;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 14, paddingVertical: 12, paddingHorizontal: pad }} style={{ marginHorizontal: -pad }}>
      {children}
    </ScrollView>
  );
}
