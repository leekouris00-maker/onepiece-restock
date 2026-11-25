// Daily spin: a PREVIEW of the free-to-play prize wheel idea (22 Nov 2026). Nothing here is live:
// no prizes are given, spins are unlimited, claiming is switched off.
// Every spin wins something: points (10–100) for the points shop, or a rare card prize (25 Nov 2026).
// Built the compliant way round: spinning and claiming are free (no purchase or subscription), the odds
// are shown, and every slice is drawn exactly as big as its real chance of winning.
import React, { useMemo, useRef, useState } from 'react';
import { Animated, Easing, Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import Svg, { Circle, G, Path, Polygon } from 'react-native-svg';
import { clean, useData } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, CardArt, Panel, T } from '../src/ui';
import { POINT_AUD, nextBonus, usePoints } from '../src/points';
import { toast } from '../src/toast';

const POSTAGE_AUD = 2.5;   // assumed cost to post one prize (stamp + toploader + envelope); change to your real figure

// Prizes and odds (chance per spin). Values come from today's TCGplayer prices.
const PRIZES = [
  { id: 'box', label: 'OP-18 booster box', odds: 0.0005, color: '#ffd54a', k: 't:712901', slices: 1 },
  { id: 'alt', label: 'Random OP-18 alt art', odds: 0.005, color: '#4fc3f7', slices: 2 },
  { id: 'pack', label: 'OP-18 booster pack', odds: 0.04, color: '#c6f432', k: 't:712904', slices: 4 },
];
const ALT_CAP_USD = 120;   // alt arts worth more than this (gold, manga) aren't in the pool
// Points: every spin that isn't a card wins points for the points shop
const POINTS = [
  { id: 'p100', label: '100 points', pts: 100, odds: 0.03, color: '#7fb52a', slices: 3 },
  { id: 'p50', label: '50 points', pts: 50, odds: 0.10, color: '#4b6e22', slices: 4 },
  { id: 'p25', label: '25 points', pts: 25, odds: 0.25, color: '#2c3d1f', slices: 6 },
];
const BASE = { id: 'p10', label: '10 points', pts: 10, odds: 1 - [...PRIZES, ...POINTS].reduce((s, p) => s + p.odds, 0) };
const ALL = [...PRIZES, ...POINTS];        // drawn in this order; anything left over is BASE
const NONE = BASE;                         // the filler slices

// Lay the wheel out: every slice's angle = its exact share of 360°. The bigger wins are spread
// between 10-point slices so the wheel looks like a wheel; the total angle per result is unchanged.
function layout() {
  const sl = p => Array.from({ length: p.slices }, () => ({ p, deg: (p.odds * 360) / p.slices }));
  const prizes = PRIZES.flatMap(sl), pts = POINTS.flatMap(sl);
  // alternate: a card prize, then points, so cards don't bunch up
  const placed = [];
  const order = [3, 1, 4, 0, 5, 2, 6].map(i => prizes[i]).filter(Boolean);
  const n = Math.max(order.length, pts.length);
  for (let i = 0; i < n; i++) { if (pts[i]) placed.push(pts[i]); if (order[i]) placed.push(order[i]); }
  const gapDeg = (BASE.odds * 360) / placed.length;
  const segs = [];
  let at = 0;
  placed.forEach((s, i) => {
    segs.push({ p: BASE, from: at, to: at + gapDeg, alt: i % 2 }); at += gapDeg;
    segs.push({ p: s.p, from: at, to: at + s.deg }); at += s.deg;
  });
  return segs;
}

const rad = d => ((d - 90) * Math.PI) / 180;
const arc = (r, a, b) => {
  const [x1, y1] = [r * Math.cos(rad(a)), r * Math.sin(rad(a))], [x2, y2] = [r * Math.cos(rad(b)), r * Math.sin(rad(b))];
  return `M0 0 L${x1.toFixed(3)} ${y1.toFixed(3)} A${r} ${r} 0 ${b - a > 180 ? 1 : 0} 1 ${x2.toFixed(3)} ${y2.toFixed(3)} Z`;
};
const oneIn = p => (p >= 0.5 ? `${Math.round(p * 100)}%` : `1 in ${Math.round(1 / p).toLocaleString()}`);

export default function Spin() {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const size = Math.min(width - 48, 360);
  const segs = useMemo(layout, []);
  const turn = useRef(new Animated.Value(0)).current;
  const angle = useRef(0);
  const [spinning, setSpinning] = useState(false);
  const [won, setWon] = useState(null);
  const [claim, setClaim] = useState(false);
  const [owner, setOwner] = useState(false);
  const pts = usePoints();
  const nb = nextBonus(pts.streak);

  const card = k => (k && d.cat ? d.cat.list.find(x => x.k === k) : null);
  // the alt-art pool: OP-18 alternate art / parallel cards up to the cap
  const alts = useMemo(() => (d.cat ? d.cat.list.filter(x => String(x.num).startsWith('OP18-') && /\((Alternate Art|Parallel)/i.test(x.n) && x.m && x.m <= ALT_CAP_USD) : []), [d.cat]);
  const altAvg = alts.length ? alts.reduce((s, x) => s + x.m, 0) / alts.length : null;
  const valueOf = p => (p.id === 'alt' ? altAvg : card(p.k)?.m ?? null);   // US$ (alt art: the pool's average)

  // what the wheel costs to run (expected prize value + postage on each win), per spin
  const perSpinUsd = PRIZES.reduce((s, p) => s + p.odds * (valueOf(p) || 0), 0);
  const winOdds = PRIZES.reduce((s, p) => s + p.odds, 0);          // card wins that need posting
  const avgPts = [...POINTS, BASE].reduce((s, p) => s + p.odds * p.pts, 0);
  const fx = d.cat?.meta?.fx || 1.5;
  const perSpinAud = perSpinUsd * fx + winOdds * POSTAGE_AUD + avgPts * POINT_AUD;

  const spin = () => {
    if (spinning) return;
    setWon(null); setClaim(false);
    // pick the result by its odds, then land somewhere inside one of its slices
    let r = Math.random(), p = BASE;
    for (const x of ALL) { if (r < x.odds) { p = x; break; } r -= x.odds; }
    const mine = segs.filter(s => s.p === p);
    const s = mine[Math.floor(Math.random() * mine.length)];
    const target = s.from + (s.to - s.from) * (0.2 + Math.random() * 0.6);   // wheel angle under the pointer
    const now = angle.current % 360;
    const to = angle.current - now + 360 * 6 + ((360 - target) % 360);
    angle.current = to;
    setSpinning(true);
    Animated.timing(turn, { toValue: to, duration: 4600, easing: Easing.bezier(0.12, 0.7, 0.1, 1), useNativeDriver: false }).start(() => {
      setSpinning(false);
      const prize = p.id === 'alt' && alts.length ? { ...p, card: alts[Math.floor(Math.random() * alts.length)] } : { ...p, card: card(p.k) };
      const { bonus, streak } = pts.spun(p.pts || 0);
      if (bonus) toast(`${streak} days in a row: +${bonus} bonus points`);
      setWon({ ...prize, bonus });
    });
  };

  const rotate = turn.interpolate({ inputRange: [0, 360], outputRange: ['0deg', '360deg'] });

  return (
    <ScrollView contentContainerStyle={{ padding: 18, paddingBottom: 60, gap: 16, width: '100%', maxWidth: 640, alignSelf: 'center' }} style={{ backgroundColor: c.bg }}>
      <View style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: c.soft }}>
        <T size={12} w="semi" style={{ color: c.accent }}>PREVIEW · not live · no real prizes</T>
      </View>
      <View style={{ gap: 4 }}>
        <T w="bold" size={30}>Daily spin</T>
        <T mute size={14.5}>One free spin a day. Every spin wins: points for the points shop, or a card shipped free. No purchase or subscription needed.</T>
      </View>

      <Pressable onPress={() => router.push('/shop')} accessibilityRole="button" accessibilityLabel="Points shop"
        style={({ pressed, hovered }) => ({ flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14, borderRadius: 18, backgroundColor: pressed || hovered ? c.raise : c.panel, borderWidth: 1, borderColor: c.line })}>
        <View style={{ width: 44, height: 44, borderRadius: 14, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="sparkles" size={22} color={c.accent} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <T w="bold" size={20}>{pts.pts.toLocaleString()} points</T>
          <T mute size={12.5}>{pts.streak ? `${pts.streak}-day streak · ` : ''}{`${nb.inDays} more ${nb.inDays === 1 ? 'day' : 'days'} in a row for +${nb.pts}`}</T>
        </View>
        <T w="semi" size={14} style={{ color: c.accent }}>Points shop ›</T>
      </Pressable>

      {/* the wheel */}
      <View style={{ alignItems: 'center', marginTop: 6 }}>
        <View style={{ width: size, height: size }}>
          <Animated.View style={{ width: size, height: size, transform: [{ rotate }] }}>
            <Svg width={size} height={size} viewBox="-105 -105 210 210">
              <Circle r={103} fill={c.raise} />
              {segs.map((s, i) => (
                <Path key={i} d={arc(98, s.from, s.to)}
                  fill={s.p === NONE ? (s.alt ? '#161b18' : '#1d2420') : s.p.color}
                  stroke={s.p === NONE ? 'none' : s.p.color} strokeWidth={s.to - s.from < 1 ? 1.4 : 0} />
              ))}
              <Circle r={98} fill="none" stroke={c.accent} strokeOpacity={0.35} strokeWidth={1} />
            </Svg>
          </Animated.View>
          {/* hub (doesn't turn) */}
          <Pressable onPress={spin} disabled={spinning} accessibilityRole="button" accessibilityLabel="Spin"
            style={({ pressed }) => ({ position: 'absolute', left: size / 2 - 42, top: size / 2 - 42, width: 84, height: 84, borderRadius: 42,
              alignItems: 'center', justifyContent: 'center', backgroundColor: spinning ? c.raise : c.accent, opacity: pressed ? 0.8 : 1,
              shadowColor: c.accent, shadowOpacity: spinning ? 0 : 0.5, shadowRadius: 18 })}>
            <T w="bold" size={spinning ? 13 : 17} style={{ color: spinning ? c.mute : c.onAccent }}>{spinning ? '…' : 'SPIN'}</T>
          </Pressable>
          {/* pointer */}
          <Svg width={28} height={26} style={{ position: 'absolute', top: -8, left: size / 2 - 14 }}>
            <Polygon points="2,2 26,2 14,24" fill={c.ink} stroke={c.bg} strokeWidth={2} />
          </Svg>
        </View>
      </View>

      {/* result */}
      {won ? <Panel>
        {won.pts ? <>
          <T size={12.5} w="semi" style={{ color: c.accent }}>YOU WON</T>
          <T w="bold" size={26}>+{won.pts} points{won.bonus ? `  +${won.bonus} streak bonus` : ''}</T>
          <T mute size={14}>{`You have ${pts.pts.toLocaleString()} points. Swap them in the points shop, or keep saving. (Preview: spin as often as you like.)`}</T>
          <Button ghost icon="sparkles-outline" onPress={() => router.push('/shop')}>Points shop</Button>
        </> : <>
          <T size={12.5} w="semi" style={{ color: won.color }}>YOU WON</T>
          <View style={{ flexDirection: 'row', gap: 14, alignItems: 'center' }}>
            {won.card ? <CardArt k={won.card.k} num={won.card.num} width={70} /> : null}
            <View style={{ flex: 1, gap: 3 }}>
              <T w="bold" size={18}>{won.id === 'alt' && won.card ? clean(won.card.n) : won.label}</T>
              {won.id === 'alt' && won.card ? <T mute size={13}>{won.card.num} · {won.card.r} alt art</T> : null}
              {won.card?.m ? <T size={14}>Worth about {d.money(won.card.m)}</T> : null}
            </View>
          </View>
          {claim ? <T size={13.5} style={{ color: c.accent }}>Preview only: claiming isn't switched on. In the real version you'd confirm your address here and it ships free. No payment, no subscription.</T>
            : <Button icon="gift-outline" onPress={() => setClaim(true)}>Claim, shipped free</Button>}
        </>}
      </Panel> : null}

      {/* odds */}
      <Panel title="Odds on every spin">
        {PRIZES.map(p => (
          <View key={p.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: p.color }} />
            <T size={14} style={{ flex: 1 }}>{p.label}</T>
            <T mute size={13}>{valueOf(p) != null ? (p.id === 'alt' ? 'avg ' : '') + d.money(valueOf(p)) : ''}</T>
            <T w="semi" size={14} style={{ width: 92, textAlign: 'right' }}>{oneIn(p.odds)}</T>
          </View>
        ))}
        {[...POINTS, BASE].map(p => (
          <View key={p.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: p.color || '#1d2420', borderWidth: p.color ? 0 : 1, borderColor: c.line }} />
            <T size={14} style={{ flex: 1 }}>{p.label}</T>
            <T w="semi" size={14} style={{ width: 92, textAlign: 'right' }}>{p.odds >= 0.1 ? `${(p.odds * 100).toFixed(1)}%` : oneIn(p.odds)}</T>
          </View>
        ))}
        <T mute size={12}>{`Every spin wins something. Each slice is exactly as big as its chance; the booster box is the thin gold line. Average ${Math.round(avgPts)} points a spin, plus streak bonuses: +100 every 7th day in a row, +500 on day 30.`}</T>
      </Panel>

      <Panel title="The rules (draft)">
        <T size={13.5} mute>Free to spin, free to claim, free shipping: no purchase or subscription is ever needed, and members get no extra spins, points or better odds. Points can only be won, never bought, sold or swapped between accounts, and have no cash value. One spin per person per day. 18+, Australia only. Prize values are today's TCGplayer market prices. These are draft rules for the preview, not legal terms.</T>
      </Panel>

      <Panel title="Members (separate from the wheel)">
        <T size={13.5} mute>An idea for the paid side, with no chance involved: a monthly card mailer guaranteed to be worth at least what you pay, price alerts on your cards, and the full collection tools. Being a member doesn't change your spin or your odds.</T>
      </Panel>

      {/* owner numbers */}
      <Pressable onPress={() => setOwner(o => !o)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name={owner ? 'chevron-down' : 'chevron-forward'} size={16} color={c.mute} />
        <T w="semi" size={14} mute>What this would cost you to run</T>
      </Pressable>
      {owner ? <Panel>
        <Row label="Prize value given away, per spin" value={d.money(perSpinUsd)} />
        <Row label={`Postage on card wins (assumed A$${POSTAGE_AUD.toFixed(2)} each, ${(winOdds * 100).toFixed(2)}% of spins)`} value={`A$${(winOdds * POSTAGE_AUD).toFixed(2)}`} />
        <Row label={`Points given out (avg ${Math.round(avgPts)} a spin at 100 = A$1)`} value={`A$${(avgPts * POINT_AUD).toFixed(2)}`} />
        <Row label="Total per spin" value={`A$${perSpinAud.toFixed(2)}`} bold />
        <View style={{ height: 1, backgroundColor: c.line }} />
        <Row label="100 people spinning daily, per month" value={`A$${Math.round(perSpinAud * 100 * 30).toLocaleString()}`} bold />
        <Row label="100 people spinning weekly, per month" value={`A$${Math.round(perSpinAud * 100 * 4.3).toLocaleString()}`} bold />
        <T mute size={12}>Prize values are what the cards sell for; your real cost is what you paid for them (e.g. packs bought at retail). Points only cost you when they're spent, and store credit costs you less than its face value. Lower odds or a weekly spin brings the cost down fast.</T>
      </Panel> : null}

      <Button ghost onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}>Close preview</Button>
    </ScrollView>
  );
}

function Row({ label, value, bold }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 12 }}>
      <T size={13.5} mute={!bold} style={{ flex: 1 }}>{label}</T>
      <T size={14} w={bold ? 'bold' : 'semi'}>{value}</T>
    </View>
  );
}
