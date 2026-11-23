// Long price history (back to Feb 2024, weekly then daily) and 90-day signals. Built each morning on
// GitHub by long_history.py into price_history/<set>.json and price_signals.json.
import React, { useEffect, useMemo, useState } from 'react';
import { View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from 'react-native-svg';
import { RAW_BASE, useData } from './data';
import { useTheme } from './theme';
import { Chip, T } from './ui';
import { ChipRow } from './screen';
import { CardRow } from './rows';

// day numbers are Python date.toordinal(): 1970-01-01 = 719163
export const ordOf = t => Math.floor(t / 864e5) + 719163;
export const todayOrd = () => ordOf(Date.now());
const dateOf = o => new Date((o - 719163) * 864e5);
const short = o => dateOf(o).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: '2-digit' });

const groups = {};
export function loadGroup(g) {
  if (!groups[g]) groups[g] = fetch(RAW_BASE + `price_history/${g}.json?h=` + Math.floor(Date.now() / 36e5)).then(r => (r.ok ? r.json() : {})).catch(() => ({}));
  return groups[g];
}

let sigP = null;
export function useSignals() {
  const [s, setS] = useState(null);
  useEffect(() => {
    if (!sigP) sigP = fetch(RAW_BASE + 'price_signals.json?h=' + Math.floor(Date.now() / 36e5)).then(r => (r.ok ? r.json() : null)).catch(() => null);
    let alive = true; sigP.then(v => alive && setS(v)); return () => { alive = false; };
  }, []);
  return s;
}

// [hi90, lo90, avg90, ath, athDay, then90] → plain words. null when there's nothing worth saying.
export function signalOf(sig, m) {
  if (!sig || m == null) return null;
  const [hi, lo, avg, ath, athDay, then] = sig;
  if (hi > lo * 1.08 && m >= hi * 0.98) return { tone: 'up', text: 'At its 90-day high', sub: `It ranged ${fmt(lo)}–${fmt(hi)} over 90 days` };
  if (hi > lo * 1.08 && m <= lo * 1.02) return { tone: 'down', text: 'At its 90-day low', sub: `It ranged ${fmt(lo)}–${fmt(hi)} over 90 days` };
  if (ath > m * 1.25 && ath >= 2) return { tone: 'down', text: `${Math.round((1 - m / ath) * 100)}% below its highest`, sub: `Peaked at ${fmt(ath)} on ${short(athDay)}` };
  if (then && Math.abs(m / then - 1) >= 0.15) return { tone: m > then ? 'up' : 'down', text: `${m > then ? 'Up' : 'Down'} ${Math.round(Math.abs(m / then - 1) * 100)}% in 90 days`, sub: `From ${fmt(then)}` };
  return null;
}
const fmt = usd => 'US$' + (usd >= 100 ? Math.round(usd).toLocaleString() : usd.toFixed(2));

const RANGES = [[30, '1M'], [90, '3M'], [180, '6M'], [365, '1Y'], [99999, 'All']];

// Card page chart with ranges. Falls back to the 35 days in the catalog until the long history loads.
export function PriceHistory({ card, width }) {
  const d = useData(), c = useTheme();
  const [long, setLong] = useState(null);
  const [days, setDays] = useState(90);
  useEffect(() => { let a = true; if (!card.mine) loadGroup(card.g).then(m => a && setLong(m[card.k.slice(2)] || [])); return () => { a = false; }; }, [card.k]);
  const today = todayOrd();
  const pts = useMemo(() => {
    const m = new Map();
    for (const [o, p] of long || []) m.set(o, p);
    const base = d.cat?.meta?.updated ? ordOf(new Date(d.cat.meta.updated + 'T12:00:00Z').getTime()) : today;
    for (const [ago, p] of card.h || []) if (!m.has(base - ago)) m.set(base - ago, p);
    if (card.m != null) m.set(base, card.m);
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [long, card.k, d.cat]);
  if (card.mine) return null;
  const first = pts.length ? pts[0][0] : today;
  const span = Math.min(days, today - first + 1);
  const from = today - span;
  // the price on the first day shown = the last change before it
  const shown = pts.filter(p => p[0] >= from);
  const before = [...pts].reverse().find(p => p[0] < from);
  if (before) shown.unshift([from, before[1]]);
  const toA = v => (d.cur === 'AUD' ? v * d.fx : v);
  const sym = d.cur === 'AUD' ? 'A$' : 'US$';
  const avail = RANGES.filter(([n]) => n <= 30 || today - first >= n * 0.6 || n === 99999);
  return (
    <View style={{ marginTop: 14, gap: 8 }}>
      <ChipRow>{avail.map(([n, l]) => <Chip key={n} on={days === n} onPress={() => setDays(n)} style={{ minHeight: 32 }}>{l}</Chip>)}</ChipRow>
      <Line pts={shown} from={from} to={today} width={width} fmt={v => sym + Math.round(toA(v)).toLocaleString()} />
      <T mute size={12.5}>TCGplayer market price{long && long.length ? `, since ${short(first)}` : ', last 35 days (longer history loading…)'}</T>
    </View>
  );
}

function Line({ pts, from, to, width, height = 160, fmt }) {
  const c = useTheme();
  if (pts.length < 2 || !width) return <T mute size={13} style={{ paddingVertical: 20 }}>Not enough price history yet.</T>;
  const ys = pts.map(p => p[1]), lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi - lo) * 0.12 || hi * 0.05 || 1;
  const L = 4, R = width - 74, Tp = 10, B = height - 10;
  const X = o => L + ((R - L) * (o - from)) / Math.max(1, to - from), Y = v => B - ((B - Tp) * (v - (lo - pad))) / (hi + pad - (lo - pad));
  let dd = `M${X(pts[0][0])},${Y(pts[0][1])}`;
  for (let i = 1; i < pts.length; i++) dd += `H${X(pts[i][0])}V${Y(pts[i][1])}`;
  dd += `H${X(to)}`;
  const last = pts[pts.length - 1][1];
  const hiP = pts.reduce((a, p) => (p[1] > a[1] ? p : a)), loP = pts.reduce((a, p) => (p[1] < a[1] ? p : a));
  return (
    <View style={{ width, height }}>
      <Svg width={width} height={height}>
        <Defs><LinearGradient id="lh" x1="0" y1="0" x2="0" y2="1"><Stop offset="0" stopColor={c.accent} stopOpacity="0.25" /><Stop offset="1" stopColor={c.accent} stopOpacity="0" /></LinearGradient></Defs>
        <Path d={`${dd} V${B} H${X(pts[0][0])} Z`} fill="url(#lh)" />
        <Path d={dd} fill="none" stroke={c.accent} strokeWidth={2.2} />
        <Circle cx={X(to)} cy={Y(last)} r={4.5} fill={c.accent} />
      </Svg>
      <T size={13} w="semi" style={{ position: 'absolute', left: R + 8, top: Math.min(height - 20, Math.max(0, Y(last) - 9)) }}>{fmt(last)}</T>
      {hiP[1] !== last && Y(last) - Y(hiP[1]) > 20 ? <T size={11} mute style={{ position: 'absolute', left: R + 8, top: Math.max(0, Y(hiP[1]) - 7) }}>high {fmt(hiP[1])}</T> : null}
      {loP[1] !== last && Y(loP[1]) - Y(hiP[1]) > 24 && Y(loP[1]) - Y(last) > 20 ? <T size={11} mute style={{ position: 'absolute', left: R + 8, top: Math.min(height - 16, Y(loP[1]) - 7) }}>low {fmt(loP[1])}</T> : null}
    </View>
  );
}

// One line under the chart: "At its 90-day high · It ranged …"
export function SignalLine({ card }) {
  const d = useData(), c = useTheme(), s = useSignals();
  const sg = s && !card.mine ? signalOf(s.items[card.k.slice(2)], card.m) : null;
  if (!sg) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: 12, backgroundColor: sg.tone === 'up' ? c.accentDim : 'rgba(255,91,91,0.12)', marginTop: 8 }}>
      <T w="bold" size={13.5} style={{ color: sg.tone === 'up' ? c.up : c.down }}>{sg.tone === 'up' ? '▲' : '▼'} {sg.text}</T>
      <T mute size={12} style={{ flex: 1 }} numberOfLines={2}>{sg.sub}</T>
    </View>
  );
}

// Home: cards you own that are at a high (time to sell?) and watched cards at a low (time to buy?)
export function SignalsPanel() {
  const d = useData(), c = useTheme(), s = useSignals();
  const rows = useMemo(() => {
    if (!s || !d.cat) return [];
    const out = [], seen = new Set();
    for (const o of d.owned) {
      if (o.status === 'sold' || !o.card || !o.card.startsWith('t:') || seen.has(o.card)) continue;
      const card = d.card(o.card); if (!card || card.m == null || card.m * d.fx < 10) continue;
      const sg = signalOf(s.items[o.card.slice(2)], card.m);
      if (sg && sg.tone === 'up') { out.push({ card, sg, why: 'You own it' }); seen.add(o.card); }
    }
    for (const f of d.favs) {
      const card = d.card(f.card); if (!card || card.mine || card.m == null || seen.has(card.k)) continue;
      const sg = signalOf(s.items[card.k.slice(2)], card.m);
      if (sg && sg.tone === 'down') { out.push({ card, sg, why: 'On your watchlist' }); seen.add(card.k); }
    }
    return out.slice(0, 6);
  }, [s, d.cat, d.owned, d.favs]);
  if (!rows.length) return null;
  return (
    <View style={{ borderRadius: 20, padding: 16, gap: 4, backgroundColor: c.panel, marginTop: 14 }}>
      <T w="bold" size={16}>Price signals</T>
      <T mute size={12.5}>Cards you own at a high may be worth selling; watched cards at a low may be worth buying.</T>
      {rows.map(({ card, sg, why }) => (
        <View key={card.k} style={{ marginHorizontal: -16 }}>
          <CardRow card={card} />
          <T size={12} w="semi" style={{ marginTop: -6, marginBottom: 4, paddingLeft: 70, color: sg.tone === 'up' ? c.up : c.down }}>{sg.tone === 'up' ? '▲' : '▼'} {sg.text} · {why}</T>
        </View>
      ))}
    </View>
  );
}
