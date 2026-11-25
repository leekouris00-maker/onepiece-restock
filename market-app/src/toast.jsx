// Bottom message with an optional action ("Removed Sabo · Undo"). Use toast() from anywhere.
import React, { useEffect, useRef, useState } from 'react';
import { Animated, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from './theme';
import { T } from './ui';
import { useWide } from './layout';

let push = null;
const MAC = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '');
let lift = 0, relift = null;
// a page with its own bottom bar (selection bar, floating buttons) moves toasts above it
export function setToastLift(px) { lift = px; relift && relift(px); }
// the last Undo offered, for Ctrl/⌘ Z (good for 30 seconds, once)
let undoRec = null;
export function lastUndo() {
  if (!undoRec || Date.now() - undoRec.at > 30000) return null;
  const u = undoRec;
  return { text: u.text, run: () => { if (undoRec === u) undoRec = null; u.run(); } };
}
export function toast(text, opts = {}) {
  if (opts.action && /undo/i.test(opts.action.label)) {
    const rec = { run: opts.action.onPress, at: Date.now(), text };
    undoRec = rec;
    opts = { ...opts, action: { ...opts.action, onPress: () => { if (undoRec === rec) undoRec = null; rec.run(); } } };
  }
  if (push) push({ text, ...opts, id: Date.now() + Math.random() });
}

export function ToastHost() {
  const c = useTheme(), ins = useSafeAreaInsets(), wide = useWide();
  const [t, setT] = useState(null);
  const [up, setUp] = useState(lift);
  useEffect(() => { relift = setUp; return () => { relift = null; }; }, []);
  const fade = useRef(new Animated.Value(0)).current;
  const timer = useRef(null);
  useEffect(() => {
    push = x => {
      clearTimeout(timer.current);
      setT(x);
      fade.setValue(0);
      Animated.timing(fade, { toValue: 1, duration: 160, useNativeDriver: false }).start();
      timer.current = setTimeout(() => setT(cur => (cur && cur.id === x.id ? null : cur)), x.ms || (x.action ? 6000 : 2600));
    };
    return () => { push = null; clearTimeout(timer.current); };
  }, []);
  if (!t) return null;
  const close = () => { clearTimeout(timer.current); setT(null); };
  return (
    <View pointerEvents="box-none" style={{ position: 'absolute', left: 0, right: 0, bottom: (wide ? 24 : ins.bottom + 76) + up, alignItems: 'center', paddingHorizontal: 14, zIndex: 1000 }}>
      <Animated.View accessibilityLiveRegion="polite" style={{ opacity: fade, transform: [{ translateY: fade.interpolate({ inputRange: [0, 1], outputRange: [10, 0] }) }],
        flexDirection: 'row', alignItems: 'center', gap: 14, maxWidth: 520, width: '100%', minHeight: 50, paddingLeft: 16, paddingRight: t.action ? 6 : 16, paddingVertical: 6,
        borderRadius: 16, backgroundColor: c.paper, shadowColor: '#000', shadowOpacity: 0.35, shadowRadius: 18, shadowOffset: { width: 0, height: 6 } }}>
        <T w="semi" size={14} style={{ flex: 1, color: c.paperInk }} numberOfLines={2}>{t.text}</T>
        {t.action ? <Pressable onPress={() => { close(); t.action.onPress(); }} accessibilityRole="button" hitSlop={6}
          style={({ pressed }) => ({ minHeight: 40, paddingHorizontal: 14, borderRadius: 12, justifyContent: 'center', backgroundColor: pressed ? c.paperLine : 'transparent' })}>
          <T w="bold" size={14} style={{ color: '#4b7a00' }}>{t.action.label}{wide && /undo/i.test(t.action.label) ? <T size={11.5} style={{ color: c.paperMute }}>{MAC ? '  ⌘Z' : '  Ctrl Z'}</T> : null}</T>
        </Pressable> : null}
      </Animated.View>
    </View>
  );
}
