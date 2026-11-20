import React, { useState } from 'react';
import { Pressable, Text, TextInput, View, StyleSheet } from 'react-native';
import { Image } from 'expo-image';
import Ionicons from '@expo/vector-icons/Ionicons';
import Svg, { Path, Circle, Line, Defs, LinearGradient, Stop } from 'react-native-svg';
import { F, useTheme } from './theme';
import { tcgImage } from './data';

export function T({ style, serif, w, mute, size, children, ...p }) {
  const c = useTheme();
  const font = serif || w === 'bold' ? F.bold : w === 'semi' ? F.semi : F.text;
  return <Text {...p} style={[{ color: mute ? c.mute : c.ink, fontFamily: font, fontSize: size || 15 }, style]}>{children}</Text>;
}

export function Chip({ on, onPress, children, style }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!on }}
      style={({ pressed }) => [{ minHeight: 36, paddingHorizontal: 16, borderRadius: 999, borderWidth: 1, justifyContent: 'center',
        borderColor: on ? c.ink : c.line, backgroundColor: on ? c.ink : pressed ? c.raise : c.soft }, style]}>
      <Text style={{ color: on ? c.bg : c.ink, fontFamily: F.semi, fontSize: 14 }}>{children}</Text>
    </Pressable>
  );
}

export function Button({ onPress, children, ghost, danger, style, disabled, icon }) {
  const c = useTheme();
  const bg = ghost ? 'transparent' : danger ? c.down : c.accent;
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
      style={({ pressed }) => [{ minHeight: 48, paddingHorizontal: 22, borderRadius: 999, alignItems: 'center', justifyContent: 'center', flexDirection: 'row', gap: 8,
        backgroundColor: bg, borderWidth: 1, borderColor: ghost ? c.line : bg, opacity: disabled ? 0.5 : pressed ? 0.8 : 1 }, style]}>
      {icon ? <Ionicons name={icon} size={18} color={ghost ? c.ink : '#000'} /> : null}
      <Text style={{ color: ghost ? c.ink : '#000', fontFamily: F.bold, fontSize: 15 }}>{children}</Text>
    </Pressable>
  );
}

export function Field({ label, style, ...p }) {
  const c = useTheme();
  const [focus, setFocus] = useState(false);
  return (
    <View style={[{ gap: 6, flexGrow: 1, flexBasis: 140 }, style]}>
      <T size={13} mute>{label}</T>
      <TextInput placeholderTextColor={c.mute} keyboardAppearance="dark" {...p} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={{ minHeight: 48, paddingHorizontal: 14, borderWidth: 1, borderRadius: 14, borderColor: focus ? c.accent : c.line,
          backgroundColor: c.soft, color: c.ink, fontFamily: F.text, fontSize: 16, outlineStyle: 'none' }} />
    </View>
  );
}

export function SearchBar({ value, onChangeText, placeholder, right, autoFocus }) {
  const c = useTheme();
  return (
    <View style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
      <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 50, borderRadius: 999, borderWidth: 1, borderColor: c.line, paddingHorizontal: 18 }}>
        <Ionicons name="search" size={22} color={c.ink} />
        <TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={c.mute} autoFocus={autoFocus}
          autoCorrect={false} autoCapitalize="none" returnKeyType="search" keyboardAppearance="dark"
          style={{ flex: 1, color: c.ink, fontFamily: F.text, fontSize: 17, minHeight: 48, outlineStyle: 'none' }} />
        {value ? <Pressable onPress={() => onChangeText('')} hitSlop={12} accessibilityLabel="Clear search"><Ionicons name="close" size={24} color={c.ink} /></Pressable> : null}
      </View>
      {right}
    </View>
  );
}

export function RoundAction({ icon, label, onPress, ring }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" style={{ alignItems: 'center', gap: 6, width: 82 }}>
      <View style={{ width: 54, height: 54, borderRadius: 27, borderWidth: ring ? 2 : 1, borderColor: ring ? c.accent : c.line, alignItems: 'center', justifyContent: 'center' }}>
        <Ionicons name={icon} size={24} color={c.accent} />
      </View>
      <T size={13.5} style={{ color: c.accent, textAlign: 'center' }}>{label}</T>
    </Pressable>
  );
}

export function Choice({ label, value, options, onChange, style }) {
  return (
    <View style={[{ gap: 6, flexBasis: '100%' }, style]}>
      <T size={13} mute>{label}</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
        {options.map(o => { const [v, l] = Array.isArray(o) ? o : [o, o]; return <Chip key={String(v)} on={value === v} onPress={() => onChange(v)}>{l}</Chip>; })}
      </View>
    </View>
  );
}

// The card's picture: your photo, else TCGplayer's image, else the card number on a dark card.
export function CardArt({ k, photo, num, label, width, qty, big }) {
  const c = useTheme();
  const [failed, setFailed] = useState(false);
  const src = photo || (!failed && tcgImage(k, big ? 400 : 200));
  return (
    <View style={{ width, aspectRatio: 63 / 88, borderRadius: Math.max(4, width / 22), overflow: 'hidden', backgroundColor: c.raise,
      alignItems: 'center', justifyContent: 'center', padding: 6 }}>
      {src ? <Image source={{ uri: src }} style={StyleSheet.absoluteFill} contentFit="cover" transition={150} onError={() => setFailed(true)} />
        : width >= 80 ? <>
            <T w="bold" size={big ? Math.min(24, width / 7) : Math.min(17, width / 7)} style={{ textAlign: 'center' }} numberOfLines={2}>{num || '★'}</T>
            {label ? <T size={11} mute style={{ textAlign: 'center', marginTop: 4 }}>{label}</T> : null}
          </> : <Ionicons name="image-outline" size={16} color={c.mute} />}
      {qty > 1 ? <View style={{ position: 'absolute', top: 6, right: 6, backgroundColor: 'rgba(0,0,0,0.75)', borderRadius: 999, paddingHorizontal: 7, paddingVertical: 2 }}>
        <Text style={{ color: '#fff', fontFamily: F.bold, fontSize: 11 }}>×{qty}</Text></View> : null}
    </View>
  );
}

// +A$0.71 (5.32%) in teal, -A$… in coral
export function Change({ now, then, aud, size = 14, pctOnly }) {
  const c = useTheme();
  if (now == null || then == null || !then) return null;
  const d = now - then, p = (d / then) * 100;
  if (Math.abs(p) < 0.05) return null;
  const col = d > 0 ? c.up : c.down;
  return <T size={size} style={{ color: col }}>{pctOnly ? `${d > 0 ? '▲' : '▼'} ${Math.abs(p).toFixed(2)}%` : `${d > 0 ? '+' : '-'}${aud(Math.abs(d))} (${d > 0 ? '' : '-'}${Math.abs(p).toFixed(2)}%)`}</T>;
}

// Filled area chart of a value over time (oldest first)
export function AreaChart({ values, width, height = 260 }) {
  const c = useTheme();
  if (!width || values.length < 2) return <View style={{ height }} />;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || hi * 0.05 || 1;
  const Tp = 16, B = height - 4, X = i => (i / (values.length - 1)) * width, Y = v => B - ((B - Tp) * (v - (lo - span * 0.25))) / (span * 1.35);
  let d = `M${X(0)},${Y(values[0])}`;
  for (let i = 1; i < values.length; i++) { const x0 = X(i - 1), x1 = X(i), xm = (x0 + x1) / 2; d += ` C${xm},${Y(values[i - 1])} ${xm},${Y(values[i])} ${x1},${Y(values[i])}`; }
  return (
    <Svg width={width} height={height}>
      <Defs><LinearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
        <Stop offset="0" stopColor={c.accent} stopOpacity="0.45" /><Stop offset="1" stopColor={c.accent} stopOpacity="0" />
      </LinearGradient></Defs>
      <Path d={`${d} L${width},${height} L0,${height} Z`} fill="url(#fill)" />
      <Path d={d} fill="none" stroke={c.accent} strokeWidth={3} />
    </Svg>
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
        <Defs><LinearGradient id="spk" x1="0" y1="0" x2="0" y2="1"><Stop offset="0" stopColor={c.accent} stopOpacity="0.35" /><Stop offset="1" stopColor={c.accent} stopOpacity="0" /></LinearGradient></Defs>
        <Path d={`${d} V${B} H${X(pts[0][0])} Z`} fill="url(#spk)" />
        <Line x1={L} x2={R} y1={B} y2={B} stroke={c.line} />
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
    <View style={[{ borderWidth: 1, borderColor: c.line, borderRadius: 18, padding: 18, gap: 12, backgroundColor: c.panel }, style]}>
      {title ? <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}><T w="bold" size={19}>{title}</T>{right}</View> : null}
      {children}
    </View>
  );
}

export function Section({ title, right, children }) {
  return <Panel title={title} right={right} style={{ marginTop: 16 }}>{children}</Panel>;
}

export function Stat({ label, value, tone }) {
  const c = useTheme();
  return (
    <View style={{ flexGrow: 1, flexBasis: 140, borderWidth: 1, borderColor: c.line, borderRadius: 16, padding: 14, backgroundColor: c.panel }}>
      <T size={13} mute>{label}</T>
      <T w="bold" size={22} style={[{ marginTop: 2 }, tone ? { color: tone } : null]}>{value}</T>
    </View>
  );
}

export function Empty({ children }) {
  return <T mute style={{ textAlign: 'center', paddingVertical: 40, paddingHorizontal: 20 }}>{children}</T>;
}
