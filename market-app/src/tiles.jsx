import React, { useMemo, useRef, useState } from 'react';
import { Animated, PanResponder, Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { haptic } from './haptic';
import { useData, clean } from './data';
import { useTheme } from './theme';
import { CardArt, Change, T } from './ui';

export function setNameOf(d, card, o) {
  if (card?.mine) return card.setName || 'My cards';
  if (card) return d.cat?.byId[card.g]?.name || '';
  return o?.group || '';
}

const openItem = o => router.push({ pathname: '/item/[id]', params: { id: o.id } });
const openCard = k => router.push({ pathname: '/card/[k]', params: { k } });

let closeOpen = null;   // only one row's swipe actions open at a time

// Profit or loss on what you paid for this entry (A$), or null when the price paid isn't known
export function plOf(d, o) {
  if (o.paid == null || o.paid === '') return null;
  const q = Number(o.qty) || 1, paid = Number(o.paid) * q;
  const now = o.status === 'sold' ? (Number(o.soldFor) || 0) * q : (d.unitAt(o, 0) || 0) * q;
  return { d: now - paid, p: paid ? ((now - paid) / paid) * 100 : null };
}

// in the currency you've chosen (paid prices are kept in A$ and converted)
export function PL({ v, size = 12 }) {
  const c = useTheme(), d = useData();
  if (!v) return null;
  return <T size={size} w="semi" style={{ color: v.d >= 0 ? c.up : c.down }}>{v.d >= 0 ? '▲ +' : '▼ -'}{d.aud(Math.abs(v.d))}{v.p != null ? ` (${Math.abs(v.p).toFixed(0)}%)` : ''}</T>;
}

// One owned item as a quiet list row: picture, name, number and set, value and weekly change.
// swipe: drag left for −1 / +1 / Sold. Long-press opens the item menu. selecting: tap ticks it.
export function OwnedRow({ o, rank, swipe, actions, selecting, selected, onSelect, onLong, showPL, active }) {
  const d = useData(), c = useTheme();
  const card = d.card(o.card), q = Number(o.qty) || 1, sold = o.status === 'sold';
  const now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  const sub = [card?.num || o.num, o.cond && o.cond !== 'Raw' ? o.cond : null, o.lang && o.lang !== 'EN' ? o.lang : null, q > 1 ? `×${q}` : null].filter(Boolean).join(' · ');
  const tx = useRef(new Animated.Value(0)).current, open = useRef(false);
  const [shown, setShown] = useState(false);          // actions drawn only while swiping / open
  const W = 204;
  const snap = to => {
    open.current = to !== 0;
    Animated.spring(tx, { toValue: to, useNativeDriver: false, bounciness: 0, speed: 20 }).start(({ finished }) => { if (finished && to === 0) setShown(false); });
    if (to !== 0) { if (closeOpen && closeOpen !== close) closeOpen(); closeOpen = close; }
  };
  const close = () => snap(0);
  const pan = useMemo(() => PanResponder.create({
    onMoveShouldSetPanResponderCapture: (e, g) => !!swipe && !selecting && Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy) * 1.6,
    onMoveShouldSetPanResponder: (e, g) => !!swipe && !selecting && Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy) * 1.6,
    onPanResponderGrant: () => { setShown(true); tx.stopAnimation(); tx.setOffset(open.current ? -W : 0); tx.setValue(0); },
    onPanResponderMove: (e, g) => tx.setValue(Math.min(open.current ? W : 0, Math.max(-W - 40 + (open.current ? W : 0), g.dx))),
    onPanResponderRelease: (e, g) => { tx.flattenOffset(); const pos = (open.current ? -W : 0) + g.dx; if (pos < -W / 3 && g.vx < 0.8) { haptic(); snap(-W); } else snap(0); },
    onPanResponderTerminate: () => { tx.flattenOffset(); snap(open.current ? -W : 0); },
    onPanResponderTerminationRequest: () => false,
  }), [swipe, selecting]);
  const act = f => () => { close(); f(o); };
  const right = sold ? <T size={12} mute>Sold</T> : showPL ? (plOf(d, o) ? <PL v={plOf(d, o)} /> : <T size={12} mute>no price paid</T>) : <Change now={now} then={then} aud={d.aud} size={12} pctOnly />;
  return (
    <View nativeID={'own-' + o.id} style={{ overflow: 'hidden', borderRadius: 12, borderLeftWidth: active ? 3 : 0, borderLeftColor: c.accent }}>
      {swipe && !selecting && shown ? <View style={{ position: 'absolute', top: 0, bottom: 0, right: 0, width: W, flexDirection: 'row' }}>
        <SwipeBtn icon="remove" label={q > 1 ? '−1' : 'Remove'} bg={c.raise} onPress={act(actions.minus)} />
        <SwipeBtn icon="add" label="+1" bg={c.soft} onPress={act(actions.plus)} />
        {!sold ? <SwipeBtn icon="cash-outline" label="Sold" bg={c.accent} fg={c.onAccent} onPress={act(actions.sold)} /> : null}
      </View> : null}
      <Animated.View {...pan.panHandlers} style={{ transform: [{ translateX: tx }], backgroundColor: active ? c.soft : c.panel, paddingHorizontal: active ? 8 : 0, touchAction: 'pan-y' }}>
        <Pressable onPress={() => (open.current ? close() : selecting ? onSelect(o) : openItem(o))} onLongPress={onLong ? () => { haptic(); onLong(o); } : undefined} delayLongPress={380}
          accessibilityRole="button" accessibilityLabel={`${clean(o.name)}${selecting ? (selected ? ', selected' : ', not selected') : ''}`}
          accessibilityActions={swipe ? [{ name: 'increment', label: 'Add one' }, { name: 'decrement', label: 'Remove one' }] : undefined}
          onAccessibilityAction={e => (e.nativeEvent.actionName === 'increment' ? actions.plus(o) : actions.minus(o))}
          style={({ pressed }) => ({ flexDirection: 'row', gap: 12, alignItems: 'center', paddingVertical: 9, opacity: pressed ? 0.6 : 1 })}>
          {selecting ? <Ionicons name={selected ? 'checkmark-circle' : 'ellipse-outline'} size={24} color={selected ? c.accent : c.mute} />
            : rank ? <T w="bold" size={13} mute style={{ width: 16, textAlign: 'center' }}>{rank}</T> : null}
          <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num} width={38} />
          <View style={{ flex: 1, gap: 2 }}>
            <T w="semi" size={14.5} numberOfLines={1}>{clean(o.name)}</T>
            <T size={12.5} mute numberOfLines={1}>{sub || setNameOf(d, card, o)}</T>
          </View>
          <View style={{ alignItems: 'flex-end', gap: 2 }}>
            <T w="bold" size={14.5}>{sold ? d.aud((Number(o.soldFor) || 0) * q) : d.aud(now == null ? null : now * q)}</T>
            {right}
          </View>
        </Pressable>
      </Animated.View>
    </View>
  );
}

function SwipeBtn({ icon, label, bg, fg, onPress }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed }) => ({ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 2, backgroundColor: bg, opacity: pressed ? 0.75 : 1 })}>
      <Ionicons name={icon} size={19} color={fg || c.ink} />
      <T w="bold" size={12} style={{ color: fg || c.ink }}>{label}</T>
    </Pressable>
  );
}

// Card-first tile for the grid view
export function OwnedTile({ o, width, selecting, selected, onSelect, onLong, active }) {
  const d = useData(), c = useTheme();
  const card = d.card(o.card), q = Number(o.qty) || 1, now = d.unitAt(o, 0), then = d.unitAt(o, 7);
  return (
    <Pressable onPress={() => (selecting ? onSelect(o) : openItem(o))} onLongPress={onLong ? () => { haptic(); onLong(o); } : undefined} delayLongPress={380}
      nativeID={'own-' + o.id} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 3, opacity: pressed ? 0.7 : 1 })}>
      <View style={active ? { borderRadius: Math.max(4, width / 20) + 3, borderWidth: 3, borderColor: c.accent, margin: -3 } : null}>
        <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num || (o.kind === 'Sealed' ? 'Sealed' : '')} width={width} qty={q} big />
        {selecting ? <View style={{ position: 'absolute', top: 6, left: 6, borderRadius: 14, backgroundColor: 'rgba(10,13,11,0.7)' }}>
          <Ionicons name={selected ? 'checkmark-circle' : 'ellipse-outline'} size={26} color={selected ? c.accent : c.ink} /></View> : null}
      </View>
      <T w="semi" size={13} numberOfLines={1} style={{ marginTop: 6 }}>{clean(o.name)}</T>
      <T w="bold" size={14}>{d.aud(now == null ? null : now * q)}</T>
      <Change now={now} then={then} aud={d.aud} size={11.5} pctOnly />
    </Pressable>
  );
}

// Carousel tile for any card in the market
export function CardTile({ card, width = 120 }) {
  const d = useData();
  const mv = d.move(card), now = card.m, then = mv == null ? null : now / (1 + mv / 100);
  return (
    <Pressable onPress={() => openCard(card.k)} accessibilityRole="button" style={({ pressed }) => ({ width, gap: 3, opacity: pressed ? 0.7 : 1 })}>
      <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={width} big />
      <T w="semi" size={13} numberOfLines={1} style={{ marginTop: 6 }}>{clean(card.n)}</T>
      <T size={12} mute numberOfLines={1}>{card.num}</T>
      <T w="bold" size={14}>{d.money(card.m)}</T>
      <Change now={now} then={then} aud={d.aud} size={11.5} pctOnly />
    </Pressable>
  );
}
