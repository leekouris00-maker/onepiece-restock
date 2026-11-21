// Daily spin: a PREVIEW of the free-to-play prize wheel idea (22 Nov 2026). Nothing here is live:
// no prizes are given, spins are unlimited, claiming is switched off.
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

const POSTAGE_AUD = 2.5;   // assumed cost to post one prize (stamp + toploader + envelope); change to your real figure

// Prizes and odds (chance per spin). Values come from today's TCGplayer prices.
const PRIZES = [
  { id: 'box', label: 'OP-18 booster box', odds: 0.0005, color: '#ffd54a', k: 't:712901', slices: 1 },
  { id: 'alt', label: 'Random OP-18 alt art', odds: 0.005, color: '#4fc3f7', slices: 2 },
  { id: 'pack', label: 'OP-18 booster pack', odds: 0.04, color: '#c6f432', k: 't:712904', slices: 4 },
];
const ALT_CAP_USD = 120;   // alt arts worth more than this (gold, manga) aren't in the pool
const NONE = { id: 'none', label: 'No prize this time', odds: 1 - PRIZES.reduce((s, p) => s + p.odds, 0) };

// Lay the wheel out: every slice's angle = its exact share of 360°. Prize slices are spread
// between "no prize" slices so the wheel looks like a wheel; the total angle per prize is unchanged.
function layout() {
  const prizeSlices = PRIZES.flatMap(p => Array.from({ length: p.slices }, () => ({ p, deg: (p.odds * 360) / p.slices })));
  const order = [3, 1, 4, 0, 5, 2, 6];   // mix pack / alt art / box around the rim
  const placed = order.map(i => prizeSlices[i]).filter(Boolean);
  const gaps = placed.length, gapDeg = (NONE.odds * 360) / gaps;
  const segs = [];
  let at = 0;
  placed.forEach((s, i) => {
    segs.push({ p: NONE, from: at, to: at + gapDeg, alt: i % 2 }); at += gapDeg;
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

  const card = k => (k && d.cat ? d.cat.list.find(x => x.k === k) : null);
  // the alt-art pool: OP-18 alternate art / parallel cards up to the cap
  const alts = useMemo(() => (d.cat ? d.cat.list.filter(x => String(x.num).startsWith('OP18-') && /\((Alternate Art|Parallel)/i.test(x.n) && x.m && x.m <= ALT_CAP_USD) : []), [d.cat]);
  const altAvg = alts.length ? alts.reduce((s, x) => s + x.m, 0) / alts.length : null;
  const valueOf = p => (p.id === 'alt' ? altAvg : card(p.k)?.m ?? null);   // US$ (alt art: the pool's average)

  // what the wheel costs to run (expected prize value + postage on each win), per spin
  const perSpinUsd = PRIZES.reduce((s, p) => s + p.odds * (valueOf(p) || 0), 0);
  const winOdds = 1 - NONE.odds;
  const fx = d.cat?.meta?.fx || 1.5;
  const perSpinAud = perSpinUsd * fx + winOdds * POSTAGE_AUD;

  const spin = () => {
    if (spinning) return;
    setWon(null); setClaim(false);
    // pick the result by its odds, then land somewhere inside one of its slices
    let r = Math.random(), p = NONE;
    for (const x of PRIZES) { if (r < x.odds) { p = x; break; } r -= x.odds; }
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
      setWon(prize);
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
        <T mute size={14.5}>One free spin a day. Win cards, shipped free. No purchase or subscription needed.</T>
      </View>

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
        {won.id === 'none' ? <>
          <T w="bold" size={20}>No prize this time</T>
          <T mute size={14}>Come back tomorrow for another free spin. (Preview: spin again as often as you like.)</T>
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
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <View style={{ width: 12, height: 12, borderRadius: 3, backgroundColor: '#1d2420', borderWidth: 1, borderColor: c.line }} />
          <T size={14} style={{ flex: 1 }}>No prize</T>
          <T w="semi" size={14} style={{ width: 92, textAlign: 'right' }}>{(NONE.odds * 100).toFixed(1)}%</T>
        </View>
        <T mute size={12}>Each slice on the wheel is exactly as big as its chance. The booster box is the thin gold line.</T>
      </Panel>

      <Panel title="The rules (draft)">
        <T size={13.5} mute>Free to spin, free to claim, free shipping: no purchase or subscription is ever needed, and members get no extra spins or better odds. One spin per person per day. 18+, Australia only. Prize values are today's TCGplayer market prices. These are draft rules for the preview, not legal terms.</T>
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
        <Row label={`Postage on wins (assumed A$${POSTAGE_AUD.toFixed(2)} each, ${(winOdds * 100).toFixed(2)}% of spins)`} value={`A$${(winOdds * POSTAGE_AUD).toFixed(2)}`} />
        <Row label="Total per spin" value={`A$${perSpinAud.toFixed(2)}`} bold />
        <View style={{ height: 1, backgroundColor: c.line }} />
        <Row label="100 people spinning daily, per month" value={`A$${Math.round(perSpinAud * 100 * 30).toLocaleString()}`} bold />
        <Row label="100 people spinning weekly, per month" value={`A$${Math.round(perSpinAud * 100 * 4.3).toLocaleString()}`} bold />
        <T mute size={12}>Prize values are what the cards sell for; your real cost is what you paid for them (e.g. packs bought at retail). Lower odds or a weekly spin brings the cost down fast.</T>
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
