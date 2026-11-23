// Open or keep sealed? Expected value of the cards in one booster box vs the sealed box price.
// Bandai publishes no odds: the hits per box below are community estimates for a standard English
// 24-pack box (Nov 2026) and can be changed. Commons and uncommons aren't counted.
import React, { useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, useData } from './data';
import { useTheme } from './theme';
import { Field, Panel, T } from './ui';
import { usePref } from './prefs';

export const CLASSES = [
  ['sr', 'Super rare (SR)', 4], ['sec', 'Secret rare (SEC)', 0.7], ['alt', 'Alt art / parallel', 1.5], ['sp', 'SP', 0.17],
  ['manga', 'Manga / super alt art', 0.04], ['tr', 'Treasure rare (TR)', 0.06], ['gold', 'Gold DON!!', 0.17], ['l', 'Leader', 5], ['r', 'Rare (R)', 8],
];

export function cls(x) {
  const n = String(x.n || '').toLowerCase();
  if (x.t === 'don') return /gold/.test(n) ? 'gold' : null;
  if (x.t !== 'card') return null;
  if (/manga|super alternate|super parallel/.test(n)) return 'manga';
  if (/\(sp\)/.test(n)) return 'sp';
  if (x.r === 'TR' || /\(tr\)/.test(n)) return 'tr';
  if (/alternate art|parallel/.test(n)) return 'alt';
  if (/reprint|foil|jolly|pirate|full art|pre-release|winner|judge|celebration/.test(n)) return null;
  return { SEC: 'sec', SR: 'sr', L: 'l', R: 'r' }[x.r] || null;
}

export function boxOf(d, setId) {
  return (d.cat?.list || []).filter(x => x.g === setId && x.t === 'sealed' && /booster box$/i.test(clean(x.n)) && x.m != null)[0] || null;
}

export function useEV(setId) {
  const d = useData();
  const [rates, setRates] = usePref('evRates', Object.fromEntries(CLASSES.map(([k, , v]) => [k, v])));
  const res = useMemo(() => {
    const groups = {};
    for (const x of d.cat?.list || []) if (x.g === setId && x.m != null) { const k = cls(x); if (k) (groups[k] ||= []).push(x); }
    const rows = CLASSES.map(([k, label, def]) => {
      const g = groups[k] || [], avg = g.length ? g.reduce((n, x) => n + x.m, 0) / g.length : 0, rate = Number(rates?.[k] ?? def) || 0;
      const top = [...g].sort((a, b) => b.m - a.m)[0];
      return { k, label, n: g.length, avg, rate, ev: g.length ? avg * rate : 0, top };
    });
    const ev = rows.reduce((n, r) => n + r.ev, 0);
    return { rows, ev, box: boxOf(d, setId) };
  }, [d.cat, setId, rates]);
  return { ...res, rates, setRates };
}

export function BoxEV({ setId, compact }) {
  const d = useData(), c = useTheme();
  const set = d.cat?.byId[setId];
  const { rows, ev, box, rates, setRates } = useEV(setId);
  const [open, setOpen] = useState(!compact);
  if (!set || !['booster', 'extra', 'premium'].includes(set.kind) || !box || ev <= 0) return null;
  const diff = ev - box.m, good = diff > 0;
  const head = (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <View style={{ flex: 1 }}>
        <T w="bold" size={15}>Open or keep sealed?</T>
        <T mute size={12.5}>Cards in an average box ≈ {d.money(ev)} · sealed box {d.money(box.m)}</T>
      </View>
      <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: good ? c.accentDim : 'rgba(255,91,91,0.14)' }}>
        <T w="bold" size={13} style={{ color: good ? c.up : c.down }}>{good ? 'Open' : 'Keep sealed'}</T>
      </View>
      {compact ? <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color={c.mute} /> : null}
    </View>
  );
  return (
    <Panel style={{ gap: 10 }}>
      {compact ? <Pressable onPress={() => setOpen(!open)} accessibilityRole="button" accessibilityState={{ expanded: open }}>{head}</Pressable> : head}
      {open ? <>
        <T size={13.5}>{good
          ? `On average a box’s cards are worth ${d.money(diff)} more than the sealed box. That’s before selling fees, and most boxes land below average: a few big pulls carry the average.`
          : `On average a box’s cards are worth ${d.money(-diff)} less than the sealed box, so sealed holds more value unless you want the cards.`}</T>
        <View style={{ gap: 2 }}>
          <View style={{ flexDirection: 'row', gap: 8, paddingVertical: 4 }}>
            <T mute size={12} style={{ flex: 1 }}>Hit</T><T mute size={12} style={{ width: 70, textAlign: 'right' }}>Per box</T>
            <T mute size={12} style={{ width: 84, textAlign: 'right' }}>Avg card</T><T mute size={12} style={{ width: 78, textAlign: 'right' }}>Worth</T>
          </View>
          {rows.filter(r => r.n).map(r => (
            <View key={r.k} style={{ flexDirection: 'row', gap: 8, alignItems: 'center', paddingVertical: 3 }}>
              <View style={{ flex: 1 }}>
                <T size={13.5} w="semi">{r.label}</T>
                {r.top ? <T mute size={11.5} numberOfLines={1} onPress={() => router.push({ pathname: '/card/[k]', params: { k: r.top.k } })}>top: {clean(r.top.n)} {d.money(r.top.m)}</T> : null}
              </View>
              <Rate value={rates?.[r.k] ?? r.rate} onChange={v => setRates({ ...(rates || {}), [r.k]: v })} />
              <T size={13} style={{ width: 84, textAlign: 'right' }}>{d.money(r.avg)}</T>
              <T size={13} w="bold" style={{ width: 78, textAlign: 'right' }}>{d.money(r.ev)}</T>
            </View>
          ))}
        </View>
        <T mute size={11.5}>Hits per box are community estimates for a 24-pack English box (Bandai doesn’t publish odds); tap a number to change it. Extra and premium boosters pack differently. Commons and uncommons aren’t counted. Prices: TCGplayer market.</T>
        {compact ? <T size={13} w="semi" style={{ color: c.link }} onPress={() => router.push({ pathname: '/card/[k]', params: { k: box.k } })}>Open the box’s price page</T> : null}
      </> : null}
    </Panel>
  );
}

function Rate({ value, onChange }) {
  const c = useTheme();
  return (
    <View style={{ width: 70 }}>
      <Field label="" value={String(value)} onChangeText={v => onChange(v.replace(',', '.'))} keyboardType="decimal-pad" style={{ flexBasis: 'auto', gap: 0 }} />
    </View>
  );
}
