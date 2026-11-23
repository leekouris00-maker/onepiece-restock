import React, { useEffect, useRef, useState } from 'react';
import { Animated, Modal, Pressable, ScrollView, Text, TextInput, View, StyleSheet } from 'react-native';
import { Image } from 'expo-image';
import Ionicons from '@expo/vector-icons/Ionicons';
import Svg, { Path, Circle, Line, Defs, LinearGradient, RadialGradient, Stop, Rect } from 'react-native-svg';
import { F, useTheme } from './theme';
import { tcgImage } from './data';

// Text. head = extra-bold for titles and big figures.
export function T({ style, serif, head, caps, w, mute, size, children, ...p }) {
  const c = useTheme();
  const font = head || serif ? F.head : w === 'bold' ? F.bold : w === 'semi' ? F.semi : w === 'medium' ? F.medium : F.text;
  return <Text {...p} style={[{ color: mute ? c.mute : c.ink, fontFamily: font, fontSize: size || 15 },
    caps ? { textTransform: 'uppercase', letterSpacing: 0.8 } : null, style]}>{children}</Text>;
}

export function Chip({ on, onPress, children, style }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!on }}
      hitSlop={4} style={({ pressed }) => [{ minHeight: 38, paddingHorizontal: 14, borderRadius: 999, justifyContent: 'center',
        backgroundColor: on ? c.accent : pressed ? c.raise : c.soft }, style]}>
      <Text style={{ color: on ? c.onAccent : c.ink, fontFamily: F.semi, fontSize: 14 }}>{children}</Text>
    </Pressable>
  );
}

export function Button({ onPress, children, ghost, danger, style, disabled, icon }) {
  const c = useTheme();
  const bg = ghost ? c.soft : danger ? c.down : c.accent, fg = ghost ? c.ink : c.onAccent;
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
      style={({ pressed }) => [{ minHeight: 52, paddingHorizontal: 22, borderRadius: 16, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8,
        backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 }, style]}>
      <Text style={{ color: fg, fontFamily: F.bold, fontSize: 15.5 }}>{children}</Text>
      {icon ? <Ionicons name={icon} size={18} color={fg} /> : null}
    </Pressable>
  );
}

export function Field({ label, style, ...p }) {
  const c = useTheme();
  const [focus, setFocus] = useState(false);
  return (
    <View style={[{ gap: 6, flexGrow: 1, flexBasis: 140 }, style]}>
      <T size={12.5} mute>{label}</T>
      <TextInput placeholderTextColor={c.mute} keyboardAppearance="dark" accessibilityLabel={label} {...p} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={{ minHeight: 48, paddingHorizontal: 14, borderRadius: 12, borderWidth: 1, borderColor: focus ? c.accent : 'transparent',
          backgroundColor: c.soft, color: c.ink, fontFamily: F.medium, fontSize: 16, outlineStyle: 'none' }} />
    </View>
  );
}

export function SearchBar({ value, onChangeText, placeholder, right, autoFocus, inputRef, onSubmitEditing }) {
  const c = useTheme();
  return (
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
      <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 48, borderRadius: 14, backgroundColor: c.soft, paddingHorizontal: 14 }}>
        <Ionicons name="search" size={19} color={c.mute} />
        <TextInput ref={inputRef} value={value} onChangeText={onChangeText} onSubmitEditing={onSubmitEditing} placeholder={placeholder} placeholderTextColor={c.mute} autoFocus={autoFocus}
          autoCorrect={false} autoCapitalize="none" returnKeyType="search" keyboardAppearance="dark"
          style={{ flex: 1, color: c.ink, fontFamily: F.medium, fontSize: 15.5, minHeight: 46, outlineStyle: 'none' }} />
        {value ? <Pressable onPress={() => onChangeText('')} hitSlop={12} accessibilityLabel="Clear search"><Ionicons name="close-circle" size={20} color={c.mute} /></Pressable> : null}
      </View>
      {right}
    </View>
  );
}

// Small rounded dropdown ("1 Month ▾"); the choices open in a bottom sheet
export function Select({ value, options, onChange, label, style }) {
  const c = useTheme();
  const [open, setOpen] = useState(false);
  const cur = options.find(o => o[0] === value);
  return (
    <>
      <Pressable onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel={`${label || 'Choose'}: ${cur?.[1]}`}
        style={({ pressed }) => [{ flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', minHeight: 34, paddingHorizontal: 14, borderRadius: 999, backgroundColor: pressed ? c.raise : c.soft }, style]}>
        <T w="semi" size={13.5}>{cur?.[1]}</T>
        <Ionicons name="chevron-down" size={14} color={c.mute} />
      </Pressable>
      <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
        <Pressable onPress={() => setOpen(false)} style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' }}>
          <Pressable style={{ backgroundColor: c.panel, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 12, paddingBottom: 34, width: '100%', maxWidth: 560, alignSelf: 'center' }}>
            <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: c.raise, alignSelf: 'center', marginBottom: 10 }} />
            {label ? <T mute size={13} style={{ paddingHorizontal: 12, paddingBottom: 6 }}>{label}</T> : null}
            {options.map(([v, l]) => (
              <Pressable key={String(v)} onPress={() => { onChange(v); setOpen(false); }} accessibilityRole="button"
                style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, minHeight: 50, borderRadius: 12, backgroundColor: pressed ? c.soft : 'transparent' })}>
                <T w={v === value ? 'bold' : 'medium'} size={16} style={v === value ? { color: c.accent } : null}>{l}</T>
                {v === value ? <Ionicons name="checkmark" size={20} color={c.accent} /> : null}
              </Pressable>
            ))}
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

// Rounded "↑ 2.4%" pill
export function ChangePill({ now, then, size = 13 }) {
  const c = useTheme();
  if (now == null || !then) return null;
  const p = ((now - then) / then) * 100;
  if (Math.abs(p) < 0.05) return null;
  const up = p > 0;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3, alignSelf: 'center', paddingHorizontal: 9, paddingVertical: 3, borderRadius: 999, backgroundColor: up ? c.accentDim : 'rgba(255,91,91,0.14)' }}>
      <Ionicons name={up ? 'arrow-up' : 'arrow-down'} size={size - 1} color={up ? c.up : c.down} />
      <T w="bold" size={size} style={{ color: up ? c.up : c.down }}>{Math.abs(p).toFixed(2)}%</T>
    </View>
  );
}

// Price as plain bold text (kept under its old name so screens didn't need renaming)
export function Bounty({ children, size = 15, style }) {
  return <T w="bold" size={size} style={style}>{children}</T>;
}

export function Choice({ label, value, options, onChange, style }) {
  return (
    <View style={[{ gap: 6, flexBasis: '100%' }, style]}>
      <T size={12.5} mute>{label}</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {options.map(o => { const [v, l] = Array.isArray(o) ? o : [o, o]; return <Chip key={String(v)} on={value === v} onPress={() => onChange(v)}>{l}</Chip>; })}
      </View>
    </View>
  );
}

// The card's picture: your photo, else TCGplayer's image, else the card number.
export function CardArt({ k, photo, num, label, width, qty, big }) {
  const c = useTheme();
  const [failed, setFailed] = useState(false);
  const src = photo || (!failed && tcgImage(k, big ? 400 : 200));
  return (
    <View style={{ width, aspectRatio: 63 / 88, borderRadius: Math.max(4, width / 20), overflow: 'hidden', backgroundColor: c.raise,
      alignItems: 'center', justifyContent: 'center', padding: 6 }}>
      {src ? <Image source={{ uri: src }} style={StyleSheet.absoluteFill} contentFit="cover" transition={150} onError={() => setFailed(true)} />
        : width >= 80 ? <>
            <T head size={big ? Math.min(20, width / 7) : Math.min(15, width / 7)} style={{ textAlign: 'center', color: c.mute }} numberOfLines={2}>{num || '★'}</T>
            {label ? <T size={11} mute style={{ textAlign: 'center', marginTop: 4 }}>{label}</T> : null}
          </> : <Ionicons name="image-outline" size={16} color={c.mute} />}
      {qty > 1 ? <View style={{ position: 'absolute', top: 4, right: 4, backgroundColor: 'rgba(10,13,11,0.85)', borderRadius: 999, paddingHorizontal: 6, paddingVertical: 1 }}>
        <Text style={{ color: c.ink, fontFamily: F.bold, fontSize: 11 }}>×{qty}</Text></View> : null}
    </View>
  );
}

// +A$0.71 (5.32%) in lime, -A$… in red; nothing when flat
export function Change({ now, then, aud, size = 14, pctOnly }) {
  const c = useTheme();
  if (now == null || then == null || !then) return null;
  const d = now - then, p = (d / then) * 100;
  if (Math.abs(p) < 0.05) return null;
  const col = d > 0 ? c.up : c.down;
  const ar = d > 0 ? '▲ ' : '▼ ';
  return <T size={size} w="semi" style={{ color: col }} accessibilityLabel={`${d > 0 ? 'up' : 'down'} ${Math.abs(p).toFixed(2)} percent`}>{pctOnly ? `${ar}${Math.abs(p).toFixed(2)}%` : `${ar}${aud(Math.abs(d))} (${Math.abs(p).toFixed(2)}%)`}</T>;
}

const DAY = 86400000;
const shortDate = t => new Date(t).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });

// Glowing lime value chart. Drag across it to read any day. values: oldest first, one per day ending today.
export function GlowChart({ values, width, height = 230, fmt }) {
  const c = useTheme();
  const [sel, setSel] = useState(null);
  if (!width || values.length < 2) return <View style={{ height: height + 26 }} />;
  const n = values.length, i = sel == null ? n - 1 : sel;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || hi * 0.05 || 1;
  const Tp = 58, B = height - 6, X = k => (k / (n - 1)) * width, Y = v => B - ((B - Tp) * (v - lo)) / span;
  let d = `M${X(0)},${Y(values[0])}`;
  for (let k = 1; k < n; k++) { const x0 = X(k - 1), x1 = X(k), xm = (x0 + x1) / 2; d += ` C${xm},${Y(values[k - 1])} ${xm},${Y(values[k])} ${x1},${Y(values[k])}`; }
  const px = X(i), py = Y(values[i]), when = Date.now() - (n - 1 - i) * DAY;
  const tipW = 132, tipX = Math.min(width - tipW - 4, Math.max(4, px - tipW / 2)), tipY = Math.max(0, py - 76);
  const pick = e => setSel(Math.max(0, Math.min(n - 1, Math.round((e.nativeEvent.locationX / width) * (n - 1)))));
  const ticks = [0, Math.round((n - 1) / 3), Math.round((2 * (n - 1)) / 3), n - 1];
  return (
    <View>
      <View style={{ width, height }} onStartShouldSetResponder={() => true} onMoveShouldSetResponder={() => true}
        onResponderGrant={pick} onResponderMove={pick} onResponderTerminationRequest={() => false} accessibilityLabel="Value chart, drag to read a day">
        <Svg width={width} height={height}>
          <Defs>
            <RadialGradient id="glow" cx={px / width} cy={py / height} rx="0.55" ry="0.8" fx={px / width} fy={py / height}>
              <Stop offset="0" stopColor={c.accent} stopOpacity="0.22" /><Stop offset="1" stopColor={c.accent} stopOpacity="0" />
            </RadialGradient>
            <LinearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={c.accent} stopOpacity="0.28" /><Stop offset="1" stopColor={c.accent} stopOpacity="0" />
            </LinearGradient>
            <LinearGradient id="drop" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={c.accent} stopOpacity="0.9" /><Stop offset="1" stopColor={c.accent} stopOpacity="0" />
            </LinearGradient>
          </Defs>
          <Rect x="0" y="0" width={width} height={height} fill="url(#glow)" />
          <Path d={`${d} L${width},${height} L0,${height} Z`} fill="url(#fill)" />
          <Path d={d} fill="none" stroke={c.accent} strokeWidth={6} strokeOpacity={0.18} />
          <Path d={d} fill="none" stroke={c.accent} strokeWidth={2.5} />
          <Rect x={px - 1} y={py} width={2} height={height - py} fill="url(#drop)" />
          <Circle cx={px} cy={py} r={9} fill={c.accent} fillOpacity={0.25} />
          <Circle cx={px} cy={py} r={4.5} fill={c.bg} stroke={c.accent} strokeWidth={2.5} />
        </Svg>
        <View pointerEvents="none" style={{ position: 'absolute', left: tipX, top: tipY, width: tipW, backgroundColor: c.paper, borderRadius: 12, paddingVertical: 8, paddingHorizontal: 12 }}>
          <T w="bold" size={13.5} style={{ color: c.paperInk }}>{fmt(values[i])}</T>
          <T size={11.5} style={{ color: c.paperMute, marginTop: 1 }}>{i === n - 1 ? 'Today' : shortDate(when)}</T>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 }}>
        {ticks.map((k, j) => <T key={j} size={11.5} mute>{k === n - 1 ? 'Today' : shortDate(Date.now() - (n - 1 - k) * DAY)}</T>)}
      </View>
    </View>
  );
}

// 35-day stepped price line for one card
export function Sparkline({ hist, now, width, height = 150, label }) {
  const c = useTheme();
  const pts = hist.map(([ago, p]) => [35 - ago, p]); if (now != null) pts.push([35, now]);
  if (pts.length < 2 || !width) return <T mute size={13} style={{ paddingVertical: 20 }}>Not enough price history yet.</T>;
  const ys = pts.map(p => p[1]), lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo) * 0.15 || hi * 0.05 || 1;
  const L = 4, R = width - 80, Tp = 8, B = height - 8, X = d => L + ((R - L) * Math.max(0, d)) / 35, Y = v => B - ((B - Tp) * (v - (lo - pad))) / (hi + pad - (lo - pad));
  let d = `M${X(pts[0][0])},${Y(pts[0][1])}`; for (let i = 1; i < pts.length; i++) d += `H${X(pts[i][0])}V${Y(pts[i][1])}`;
  const last = pts[pts.length - 1];
  return (
    <View style={{ width, height }}>
      <Svg width={width} height={height}>
        <Defs><LinearGradient id="spk" x1="0" y1="0" x2="0" y2="1"><Stop offset="0" stopColor={c.accent} stopOpacity="0.25" /><Stop offset="1" stopColor={c.accent} stopOpacity="0" /></LinearGradient></Defs>
        <Path d={`${d} V${B} H${X(pts[0][0])} Z`} fill="url(#spk)" />
        <Path d={d} fill="none" stroke={c.accent} strokeWidth={2.5} />
        <Circle cx={X(35)} cy={Y(last[1])} r={4.5} fill={c.accent} />
      </Svg>
      <T size={13} w="semi" style={{ position: 'absolute', left: R + 10, top: Math.min(height - 20, Math.max(0, Y(last[1]) - 9)) }}>{label}</T>
    </View>
  );
}

export function Panel({ title, right, children, style }) {
  const c = useTheme();
  return (
    <View style={[{ borderRadius: 20, padding: 16, gap: 12, backgroundColor: c.panel }, style]}>
      {title ? <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}><T w="bold" size={16}>{title}</T>{right}</View> : null}
      {children}
    </View>
  );
}

export function Section({ title, right, children }) {
  return <Panel title={title} right={right} style={{ marginTop: 14 }}>{children}</Panel>;
}

export function Stat({ label, value, tone }) {
  const c = useTheme();
  return (
    <View style={{ flexGrow: 1, flexBasis: 100, borderRadius: 16, padding: 14, backgroundColor: c.panel }}>
      <T size={12.5} mute>{label}</T>
      <T w="bold" size={19} style={[{ marginTop: 3 }, tone ? { color: tone } : null]}>{value}</T>
    </View>
  );
}

export function Empty({ children }) {
  return <T mute style={{ textAlign: 'center', paddingVertical: 36, paddingHorizontal: 20 }}>{children}</T>;
}

// Grey placeholder shapes that gently pulse while something loads
export function Skel({ w = '100%', h = 14, r = 8, style }) {
  const c = useTheme();
  const a = useRef(new Animated.Value(0.5)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(a, { toValue: 1, duration: 700, useNativeDriver: false }), Animated.timing(a, { toValue: 0.5, duration: 700, useNativeDriver: false })]));
    loop.start(); return () => loop.stop();
  }, []);
  return <Animated.View style={[{ width: w, height: h, borderRadius: r, backgroundColor: c.raise, opacity: a }, style]} />;
}

export function SkelRows({ n = 5, art = 40 }) {
  return <View style={{ gap: 14, paddingVertical: 8 }}>{Array.from({ length: n }, (_, i) => (
    <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
      <Skel w={art} h={art / (63 / 88)} r={5} />
      <View style={{ flex: 1, gap: 7 }}><Skel w="70%" h={13} /><Skel w="40%" h={11} /></View>
      <Skel w={58} h={14} />
    </View>))}</View>;
}

// Bottom sheet for menus and small forms
export function Sheet({ open, onClose, title, children, maxWidth = 560 }) {
  const c = useTheme();
  // ignore touches for a moment after opening, so the finger that long-pressed to open it can't tap an item by lifting
  const [armed, setArmed] = useState(false);
  useEffect(() => { if (!open) { setArmed(false); return undefined; } const t = setTimeout(() => setArmed(true), 450); return () => clearTimeout(t); }, [open]);
  return (
    <Modal visible={!!open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable onPress={() => armed && onClose()} style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' }} accessibilityLabel="Close">
        <Pressable style={{ backgroundColor: c.panel, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingTop: 12, paddingBottom: 30, width: '100%', maxWidth, alignSelf: 'center', maxHeight: '88%' }}>
          <View style={{ width: 40, height: 4, borderRadius: 2, backgroundColor: c.raise, alignSelf: 'center', marginBottom: 10 }} />
          <ScrollView contentContainerStyle={{ paddingHorizontal: 18, gap: 10 }} keyboardShouldPersistTaps="handled" pointerEvents={armed ? 'auto' : 'none'}>
            {title ? <T w="bold" size={17} style={{ marginBottom: 2 }}>{title}</T> : null}
            {children}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

// One line in a menu sheet
export function MenuItem({ icon, label, sub, onPress, danger }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button"
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 14, minHeight: 52, paddingHorizontal: 6, borderRadius: 12, backgroundColor: pressed ? c.soft : 'transparent' })}>
      {icon ? <Ionicons name={icon} size={21} color={danger ? c.down : c.ink} /> : null}
      <View style={{ flex: 1 }}>
        <T w="semi" size={15.5} style={danger ? { color: c.down } : null}>{label}</T>
        {sub ? <T mute size={12.5}>{sub}</T> : null}
      </View>
    </Pressable>
  );
}

// Coloured note: 'warn' (red), 'info' (lime) or plain
export function Note({ tone, title, children, action, onAction, style }) {
  const c = useTheme();
  const bg = tone === 'warn' ? 'rgba(255,91,91,0.14)' : tone === 'info' ? c.accentDim : c.soft;
  const fg = tone === 'warn' ? c.down : tone === 'info' ? c.accent : c.ink;
  return (
    <View style={[{ padding: 14, borderRadius: 14, backgroundColor: bg, flexDirection: 'row', alignItems: 'center', gap: 12 }, style]}>
      <View style={{ flex: 1 }}>
        {title ? <T w="semi" size={14} style={{ color: fg }}>{title}</T> : null}
        {children ? <T size={13} mute style={{ marginTop: title ? 2 : 0 }}>{children}</T> : null}
      </View>
      {action ? <Pressable onPress={onAction} hitSlop={8} accessibilityRole="button"><T w="bold" size={13.5} style={{ color: fg }}>{action}</T></Pressable> : null}
    </View>
  );
}

// How sure a price is, from how many sales it rests on
export function Confidence({ n }) {
  const c = useTheme();
  if (n == null) return null;
  const [label, col] = n >= 10 ? ['Solid', c.up] : n >= 3 ? ['Fair', '#f2c94c'] : ['Few sales', c.down];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: c.soft }}>
      <View style={{ width: 7, height: 7, borderRadius: 4, backgroundColor: col }} />
      <T size={11.5} w="semi">{label} · {n} {n === 1 ? 'sale' : 'sales'}</T>
    </View>
  );
}

// "today", "yesterday", "3 days ago", else the date
export function ago(day) {
  if (!day) return '';
  const t = new Date(String(day).length <= 10 ? day + 'T12:00:00' : day).getTime();
  if (isNaN(t)) return String(day);
  const n = Math.round((Date.now() - t) / 864e5);
  return n <= 0 ? 'today' : n === 1 ? 'yesterday' : n < 31 ? `${n} days ago` : new Date(t).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
}
