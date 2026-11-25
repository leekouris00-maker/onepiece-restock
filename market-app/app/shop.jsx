// Points shop: swap points earned in Rewards for store credit, packs and singles.
// Fixed points prices (100 points = A$1), no mystery or random items.
// PREVIEW (25 Nov 2026): points live on this device only and nothing is sent.
import React, { useCallback, useState } from 'react';
import { Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { useWide } from '../src/layout';
import { Button, CardArt, Panel, Sheet, T } from '../src/ui';
import { SHOP, POINT_AUD, PRICES_SET, nextBonus, usePoints } from '../src/points';
import { toast } from '../src/toast';

const ago = t => { const m = Math.round((Date.now() - t) / 60000); return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`; };

export default function Shop() {
  const d = useData(), c = useTheme(), wide = useWide(), { width } = useWindowDimensions();
  const pts = usePoints();
  useTrack('shop');
  useFocusEffect(useCallback(() => { pts.reload(); }, [pts.reload]));
  const [pick, setPick] = useState(null);
  const [busy, setBusy] = useState(false);
  const can = pts.mode === 'server' || pts.mode === 'device';
  const items = SHOP.map(x => ({ ...x, card: x.k && d.card ? d.card(x.k) : null }));
  const nb = nextBonus(pts.streak);
  const cols = wide ? 3 : 2, gap = 10, w = Math.floor((Math.min(width, 760) - 36 - gap * (cols - 1)) / cols);

  const redeem = async x => {
    if (busy) return;
    setBusy(true);
    try {
      const id = await pts.redeem(x);
      setPick(null);
      toast(`Swapped ${x.cost.toLocaleString()} points for ${x.label}`, { action: { label: 'Undo', onPress: () => pts.cancel(id).catch(e => toast(e.message || String(e))) } });
    } catch (e) { toast(e.message || String(e)); } finally { setBusy(false); }
  };

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ padding: 18, paddingBottom: 60, gap: 16, width: '100%', maxWidth: 760, alignSelf: 'center' }}>
      <View style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: c.soft }}>
        <T size={12} w="semi" style={{ color: c.accent }}>{pts.mode === 'device' ? 'PREVIEW · points on this device only · nothing is sent' : 'TEST PHASE · swaps are recorded · nothing ships yet'}</T>
      </View>
      <View style={{ gap: 4 }}>
        <T w="bold" size={30}>Points shop</T>
        <T mute size={14.5}>Swap the points you earn in Rewards. Points are earned, never bought.</T>
      </View>

      {/* balance */}
      <Panel>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <View style={{ width: 48, height: 48, borderRadius: 15, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name="sparkles" size={24} color={c.accent} />
          </View>
          <View style={{ flex: 1 }}>
            <T w="bold" size={28}>{pts.pts.toLocaleString()}</T>
            <T mute size={12.5}>{`points · about A$${(pts.pts * POINT_AUD).toFixed(2)} in the shop`}</T>
          </View>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="flame-outline" size={17} color={pts.streak ? c.accent : c.mute} />
          <T size={13.5} style={{ flex: 1 }}>{pts.streak ? `${pts.streak}-day streak. ` : 'No streak yet. '}{`${nb.inDays} more ${nb.inDays === 1 ? 'day' : 'days'} in a row for +${nb.pts} points.`}</T>
        </View>
        <Button icon="gift-outline" onPress={() => router.navigate('/rewards')}>{pts.mode === 'signedout' ? 'Sign in to earn points' : 'Earn points'}</Button>
      </Panel>

      {/* rewards */}
      <T w="bold" size={18} style={{ marginTop: 4 }}>Rewards</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap }}>
        {items.map(x => {
          const can = pts.pts >= x.cost, part = Math.min(1, pts.pts / x.cost);
          return (
            <Pressable key={x.id} onPress={() => setPick(x)} accessibilityRole="button" accessibilityLabel={`${x.label}, ${x.cost} points`}
              style={({ pressed, hovered }) => ({ width: w, padding: 12, gap: 8, borderRadius: 18, backgroundColor: pressed || hovered ? c.raise : c.panel, borderWidth: 1, borderColor: can ? c.accent : c.line })}>
              <View style={{ height: 96, alignItems: 'center', justifyContent: 'center', borderRadius: 12, backgroundColor: c.soft }}>
                {x.card ? <CardArt k={x.card.k} num={x.card.num} width={62} />
                  : <View style={{ alignItems: 'center', gap: 4 }}>
                      <Ionicons name={x.icon} size={30} color={c.accent} />
                      {x.id.startsWith('c') ? <T w="bold" size={18}>A${x.aud}</T> : null}
                    </View>}
              </View>
              <T w="bold" size={14.5} numberOfLines={2}>{x.label}</T>
              <T mute size={12} numberOfLines={1}>{x.sub}</T>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <Ionicons name="sparkles" size={13} color={c.accent} />
                <T w="bold" size={15}>{x.cost.toLocaleString()}</T>
              </View>
              <View style={{ height: 5, borderRadius: 3, backgroundColor: c.soft, overflow: 'hidden' }}>
                <View style={{ width: `${part * 100}%`, height: 5, backgroundColor: c.accent }} />
              </View>
              <T size={12} style={{ color: can ? c.accent : c.mute }}>{can ? 'You can swap for this' : `${(x.cost - pts.pts).toLocaleString()} more points`}</T>
            </Pressable>
          );
        })}
      </View>
      <T mute size={12}>{`Fixed prices: 100 points = A$1 of value (set ${PRICES_SET}). Packs and boxes are sealed and ship free. Price changes get 30 days’ notice.`}</T>

      {pts.swaps && pts.swaps.length ? <Panel title="Your swaps">
        {pts.swaps.map(x => (
          <View key={x.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={{ flex: 1 }}><T size={13.5}>{x.label}</T><T mute size={12}>{`${x.cost.toLocaleString()} points · ${x.status === 'requested' ? 'waiting to be sent' : x.status}`}</T></View>
            {x.status === 'requested' ? <Pressable onPress={() => pts.cancel(x.id).then(() => toast('Swap undone, points back')).catch(e => toast(e.message || String(e)))} hitSlop={8}><T w="semi" size={13} style={{ color: c.accent }}>Undo</T></Pressable> : null}
          </View>
        ))}
      </Panel> : null}

      {/* history */}
      {pts.log.length ? <Panel title="Your points">
        {pts.log.slice(0, 12).map((e, i) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <T size={13.5} style={{ flex: 1 }}>{e.why}</T>
            <T mute size={12}>{ago(new Date(e.at).getTime())}</T>
            <T w="semi" size={14} style={{ width: 70, textAlign: 'right', color: e.delta >= 0 ? c.up : c.down }}>{e.delta >= 0 ? '+' : '−'}{Math.abs(e.delta).toLocaleString()}</T>
          </View>
        ))}
      </Panel> : null}

      <Panel title="How points work (draft)">
        <T size={13.5} mute>Earn points with the daily check-in, streak bonuses and milestones in Rewards. Every reward is fixed: nothing is left to chance. Points can’t be bought, sold or moved to another account, have no cash value, and members earn exactly the same as everyone else. Swapping is free, postage included.</T>
      </Panel>

      <Sheet open={!!pick} onClose={() => setPick(null)} title={pick ? pick.label : ''}>
        {pick ? <View style={{ gap: 12 }}>
          <T size={15}>{`Costs ${pick.cost.toLocaleString()} points (about A$${pick.aud.toFixed(2)} of value). You have ${pts.pts.toLocaleString()}.`}</T>
          {pick.id.startsWith('single') ? <T mute size={13.5}>In the real shop you’d pick the card next, from anything in stock up to the limit.</T> : null}
          <T mute size={13}>{pts.mode === 'server' ? 'Test phase: the swap is saved to your account and the points come off, but nothing ships yet and no address is asked for. You can undo it until it’s sent.' : 'Preview: swapping takes the points off on this device only. Nothing is sent.'}</T>
          {!can ? <Button ghost onPress={() => { setPick(null); router.push({ pathname: '/account', params: { back: '1' } }); }}>Sign in to swap</Button>
            : pts.pts >= pick.cost ? <Button icon="swap-horizontal" disabled={busy} onPress={() => redeem(pick)}>Swap {pick.cost.toLocaleString()} points</Button>
            : <Button ghost disabled>{`${(pick.cost - pts.pts).toLocaleString()} more points needed`}</Button>}
        </View> : null}
      </Sheet>
    </ScrollView>
  );
}
