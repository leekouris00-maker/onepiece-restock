import React, { useState } from 'react';
import { Pressable, Text, TextInput, View, StyleSheet } from 'react-native';
import { Image } from 'expo-image';
import Svg, { Path, Circle, Line } from 'react-native-svg';
import { F, useTheme } from './theme';
import { tcgImage } from './data';

export function T({ style, serif, w, mute, size, children, ...p }) {
  const c = useTheme();
  const font = serif ? F.serif : w === 'bold' ? F.bold : w === 'semi' ? F.semi : w === 'medium' ? F.medium : F.text;
  return <Text {...p} style={[{ color: mute ? c.mute : c.ink, fontFamily: font, fontSize: size || (serif ? 20 : 15) }, style]}>{children}</Text>;
}

export function Chip({ on, onPress, children, style }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected: !!on }}
      style={({ pressed }) => [{ minHeight: 38, paddingHorizontal: 16, borderRadius: 999, borderWidth: 1, justifyContent: 'center',
        borderColor: on ? c.ink : c.line, backgroundColor: on ? c.ink : pressed ? c.soft : c.panel }, style]}>
      <Text style={{ color: on ? c.bg : c.ink, fontFamily: F.medium, fontSize: 14 }}>{children}</Text>
    </Pressable>
  );
}

export function Button({ onPress, children, ghost, danger, style, disabled }) {
  const c = useTheme();
  const bg = ghost ? 'transparent' : danger ? c.down : c.ink;
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button"
      style={({ pressed }) => [{ minHeight: 48, paddingHorizontal: 22, borderRadius: 999, alignItems: 'center', justifyContent: 'center',
        backgroundColor: bg, borderWidth: 1, borderColor: ghost ? c.line : bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 }, style]}>
      <Text style={{ color: ghost ? c.ink : c.bg, fontFamily: F.semi, fontSize: 15 }}>{children}</Text>
    </Pressable>
  );
}

export function Field({ label, style, ...p }) {
  const c = useTheme();
  const [focus, setFocus] = useState(false);
  return (
    <View style={[{ gap: 5, flexGrow: 1, flexBasis: 140 }, style]}>
      <T size={12.5} mute>{label}</T>
      <TextInput placeholderTextColor={c.mute} {...p} onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={{ minHeight: 46, paddingHorizontal: 12, borderWidth: 1, borderRadius: 10, borderColor: focus ? c.gold : c.line,
          backgroundColor: c.bg, color: c.ink, fontFamily: F.text, fontSize: 16 }} />
    </View>
  );
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

// A card-shaped picture: your photo, else TCGplayer's image, else the card number in a frame.
export function CardArt({ k, photo, num, label, width, qty, big }) {
  const c = useTheme();
  const [failed, setFailed] = useState(false);
  const src = photo || (!failed && tcgImage(k, big ? 400 : 200));
  return (
    <View style={{ width, aspectRatio: 63 / 88, borderRadius: 10, overflow: 'hidden', backgroundColor: c.soft,
      borderWidth: StyleSheet.hairlineWidth, borderColor: c.line, alignItems: 'center', justifyContent: 'center', padding: 8 }}>
      {src ? <Image source={{ uri: src }} style={StyleSheet.absoluteFill} contentFit="cover" transition={150} onError={() => setFailed(true)} />
        : <>
            <View style={{ position: 'absolute', top: 6, left: 6, right: 6, bottom: 6, borderWidth: 1, borderColor: c.gold, opacity: 0.4, borderRadius: 6 }} />
            {width >= 80 ? <T serif size={big ? Math.min(26, width / 7) : Math.min(18, width / 7)} style={{ textAlign: 'center' }} numberOfLines={2}>{num || '★'}</T>
              : <T serif size={14} style={{ color: c.gold }}>★</T>}
            {label && width >= 80 ? <T size={11} mute style={{ textAlign: 'center', marginTop: 4 }}>{label}</T> : null}
          </>}
      {qty > 1 ? <View style={{ position: 'absolute', top: 7, right: 7, backgroundColor: c.ink, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 }}>
        <Text style={{ color: c.bg, fontFamily: F.bold, fontSize: 12 }}>×{qty}</Text></View> : null}
    </View>
  );
}

// 35-day stepped price line
export function Sparkline({ hist, now, width, height = 130, label }) {
  const c = useTheme();
  const pts = hist.map(([ago, p]) => [35 - ago, p]); if (now != null) pts.push([35, now]);
  if (pts.length < 2 || !width) return <T mute size={13} style={{ paddingVertical: 20 }}>Not enough price history yet.</T>;
  const ys = pts.map(p => p[1]), lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo) * 0.15 || hi * 0.05 || 1;
  const L = 4, R = width - 76, Tp = 8, B = height - 8, X = d => L + ((R - L) * Math.max(0, d)) / 35, Y = v => B - ((B - Tp) * (v - (lo - pad))) / (hi + pad - (lo - pad));
  let d = `M${X(pts[0][0])},${Y(pts[0][1])}`; for (let i = 1; i < pts.length; i++) d += `H${X(pts[i][0])}V${Y(pts[i][1])}`;
  const last = pts[pts.length - 1];
  return (
    <View style={{ width, height }}>
      <Svg width={width} height={height}>
        <Line x1={L} x2={R} y1={B} y2={B} stroke={c.line} />
        <Path d={d} fill="none" stroke={c.red} strokeWidth={2.2} />
        <Circle cx={X(35)} cy={Y(last[1])} r={4} fill={c.red} />
      </Svg>
      <T size={13} style={{ position: 'absolute', left: R + 8, top: Math.min(height - 20, Math.max(0, Y(last[1]) - 9)) }}>{label}</T>
    </View>
  );
}

export function Section({ title, right, children }) {
  const c = useTheme();
  return (
    <View style={{ borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.line, paddingTop: 16, marginTop: 22, gap: 10 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', gap: 10 }}>
        <T serif size={21}>{title}</T>{right}
      </View>
      {children}
    </View>
  );
}

export function Stat({ label, value, tone }) {
  const c = useTheme();
  return (
    <View style={{ flexGrow: 1, flexBasis: 140, borderWidth: 1, borderColor: c.line, borderRadius: 12, padding: 12, backgroundColor: c.panel }}>
      <T size={12.5} mute>{label}</T>
      <T serif size={23} style={tone ? { color: tone } : null}>{value}</T>
    </View>
  );
}

export function Empty({ children }) {
  return <T mute style={{ textAlign: 'center', paddingVertical: 40, paddingHorizontal: 20 }}>{children}</T>;
}
