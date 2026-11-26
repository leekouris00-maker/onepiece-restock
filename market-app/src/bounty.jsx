// Bounties (27 Nov 2026): your bounty and rank, weekly bounties, set completion, the next-reward bar and
// the evening streak reminder. Everything is fixed and known in advance: no chance anywhere.
// Points come from src/points.js (the database checks every claim).
import React, { useMemo, useState } from 'react';
import { Pressable, Switch, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData } from './data';
import { useTheme } from './theme';
import { Button, Panel, T } from './ui';
import { toast } from './toast';
import { haptic } from './haptic';
import { CHECKIN, QUESTS, QUEST_ALL, QUEST_PTS, SET_STEPS, SHOP, berries, rankOf, setProgress, stepsReady, usePoints, weekEnds } from './points';

// the next thing in the shop you're working towards (or one you can already have)
export function nextReward(pts) {
  const list = [...SHOP].sort((a, b) => a.cost - b.cost);
  const next = list.find(x => x.cost > pts);
  const can = list.filter(x => x.cost <= pts).pop() || null;
  return { next, can, toGo: next ? next.cost - pts : 0, frac: next ? pts / next.cost : 1 };
}

export function Bar({ frac, h = 8, color }) {
  const c = useTheme();
  return (
    <View style={{ height: h, borderRadius: h / 2, backgroundColor: c.soft, overflow: 'hidden' }}>
      <View style={{ width: `${Math.max(2, Math.min(100, (frac || 0) * 100))}%`, height: '100%', borderRadius: h / 2, backgroundColor: color || c.accent }} />
    </View>
  );
}

export function RankBadge({ rank, size = 44 }) {
  const c = useTheme();
  return (
    <View style={{ width: size, height: size, borderRadius: size * 0.3, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
      <Ionicons name={rank.icon} size={size * 0.5} color={c.accent} />
    </View>
  );
}

// Rewards page top: bounty + rank (opens the wanted poster), then points + next reward (opens the shop)
export function BountyCard({ pts }) {
  const c = useTheme();
  const b = pts.bounty, r = rankOf(b || 0), nr = nextReward(pts.pts);
  return (
    <View style={{ gap: 10 }}>
      {b != null ? <Pressable onPress={() => router.push('/poster')} accessibilityRole="button" accessibilityLabel={`Your bounty ${berries(b)}, ${r.label}. Open your wanted poster`}
        style={({ pressed, hovered }) => ({ padding: 14, gap: 10, borderRadius: 18, backgroundColor: pressed || hovered ? c.raise : c.panel, borderWidth: 1, borderColor: c.accentDim })}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
          <RankBadge rank={r} />
          <View style={{ flex: 1, gap: 1 }}>
            <T mute size={12} w="semi">YOUR BOUNTY · {r.label.toUpperCase()}</T>
            <T w="bold" size={24} numberOfLines={1} adjustsFontSizeToFit>{berries(b)}</T>
          </View>
          <View style={{ alignItems: 'center' }}>
            <Ionicons name="document-text-outline" size={20} color={c.accent} />
            <T size={11} w="semi" style={{ color: c.accent }}>Poster</T>
          </View>
        </View>
        {r.next ? <>
          <Bar frac={r.frac} />
          <T mute size={12.5}>{`${berries(r.toNext, true)} to ${r.next.label}`}</T>
        </> : <T mute size={12.5}>Top rank. Your bounty keeps growing.</T>}
      </Pressable> : null}
      <Pressable onPress={() => router.push('/shop')} accessibilityRole="button" accessibilityLabel="Points shop"
        style={({ pressed, hovered }) => ({ padding: 14, gap: 8, borderRadius: 18, backgroundColor: pressed || hovered ? c.raise : c.panel, borderWidth: 1, borderColor: c.line })}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Ionicons name="sparkles" size={18} color={c.accent} />
          <T w="bold" size={18} style={{ flex: 1 }}>{pts.pts.toLocaleString()} points</T>
          <T w="semi" size={14} style={{ color: c.accent }}>Points shop ›</T>
        </View>
        {nr.next ? <>
          <Bar frac={nr.frac} />
          <T mute size={12.5}>{nr.can ? `You can swap for ${nr.can.label} now · ` : ''}{`${nr.toGo.toLocaleString()} more for ${nr.next.label}`}</T>
        </> : <T mute size={12.5}>You can swap for anything in the shop.</T>}
      </Pressable>
    </View>
  );
}

// Home: one card. Before today's check-in it's the Morning Log nudge; after, your bounty and the next reward.
export function HomeRewardsCard() {
  const c = useTheme(), pts = usePoints();
  if (!(pts.mode === 'server' || pts.mode === 'device')) return null;
  const nr = nextReward(pts.pts), r = pts.bounty != null ? rankOf(pts.bounty) : null;
  const left = (pts.quests || []).filter(q => !q.claimed).length;
  const ready = (pts.quests || []).filter(q => q.done && !q.claimed).length;
  const line = !pts.checkedIn ? `${pts.streak ? `${pts.streak}-day streak · ` : ''}Your movers, ban news and events · +${CHECKIN} points`
    : ready ? `${ready} weekly ${ready === 1 ? 'bounty' : 'bounties'} ready to claim`
    : left ? `${left} weekly ${left === 1 ? 'bounty' : 'bounties'} left this week`
    : 'All weekly bounties done. New ones on Monday.';
  return (
    <Pressable onPress={() => router.push('/rewards')} accessibilityRole="button" accessibilityLabel={pts.checkedIn ? 'Rewards' : 'Daily check-in'}
      style={({ pressed, hovered }) => ({ marginTop: 14, gap: 10, padding: 12, paddingRight: 14, borderRadius: 16,
        backgroundColor: pressed || hovered ? c.raise : c.panel, borderWidth: 1, borderColor: c.accentDim })}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        {r && pts.checkedIn ? <RankBadge rank={r} size={36} /> : <View style={{ width: 36, height: 36, borderRadius: 11, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="newspaper-outline" size={19} color={c.accent} />
        </View>}
        <View style={{ flex: 1 }}>
          <T w="semi" size={14.5}>{!pts.checkedIn ? 'Today’s Morning Log' : r ? `${r.label} · ${berries(pts.bounty, true)}` : 'Rewards'}</T>
          <T mute size={12.5} style={ready && pts.checkedIn ? { color: c.accent } : null}>{line}</T>
        </View>
        <Ionicons name="chevron-forward" size={17} color={c.mute} />
      </View>
      {nr.next ? <View style={{ gap: 5 }}>
        <Bar frac={nr.frac} h={6} />
        <T mute size={12}>{`${nr.toGo.toLocaleString()} points to ${nr.next.label}`}</T>
      </View> : null}
    </Pressable>
  );
}

function Claim({ label, onPress, disabled }) {
  const c = useTheme();
  return (
    <Pressable disabled={disabled} onPress={onPress} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed }) => ({ paddingHorizontal: 14, minHeight: 36, borderRadius: 18, justifyContent: 'center', backgroundColor: pressed ? c.accentDim : c.accent })}>
      <T w="bold" size={13.5} style={{ color: c.onAccent }}>{label}</T>
    </Pressable>
  );
}

export function WeeklyBounties({ pts, busy, run }) {
  const c = useTheme();
  const qs = pts.quests;
  if (!qs) return null;
  const n = qs.filter(q => q.claimed).length;
  const claim = q => run(async () => {
    if (await pts.claimQuest(q.id)) {
      haptic('success');
      const all = qs.filter(x => x.claimed || x.id === q.id).length === qs.length;
      toast(all ? `+${QUEST_PTS} points, and +${QUEST_ALL} for finishing all three this week` : `+${QUEST_PTS} points: ${q.label}`);
    }
  });
  return (
    <Panel title="Weekly bounties" right={<T mute size={12.5}>{`${n} of ${qs.length} done`}</T>}>
      <T mute size={12.5}>{`+${QUEST_PTS} each, +${QUEST_ALL} more for all three. ${weekEnds()}.`}</T>
      {qs.map(q => {
        const m = QUESTS[q.id] || { icon: 'flag-outline', go: '/rewards', sub: '' };
        return (
          <View key={q.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 50 }}>
            <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: q.claimed ? c.accentDim : c.soft, alignItems: 'center', justifyContent: 'center' }}>
              <Ionicons name={q.claimed ? 'checkmark' : m.icon} size={18} color={q.claimed || q.done ? c.accent : c.mute} />
            </View>
            <View style={{ flex: 1 }}>
              <T w="semi" size={14} style={q.claimed ? { color: c.mute } : null}>{q.label}</T>
              <T mute size={12}>{q.claimed ? 'Done' : q.done ? 'Done: claim your points' : m.sub}</T>
            </View>
            {q.claimed ? <T w="semi" size={13.5} mute>+{QUEST_PTS}</T>
              : q.done ? <Claim label={`Claim +${QUEST_PTS}`} disabled={busy} onPress={() => claim(q)} />
              : <Pressable onPress={() => router.push(m.go)} hitSlop={8} accessibilityRole="button" accessibilityLabel={`Go: ${q.label}`}
                  style={{ flexDirection: 'row', alignItems: 'center', gap: 4, minHeight: 36 }}>
                  <T w="semi" size={13.5} style={{ color: c.accent }}>Go</T><Ionicons name="chevron-forward" size={15} color={c.accent} />
                </Pressable>}
          </View>
        );
      })}
      <View style={{ flexDirection: 'row', gap: 6 }}>
        {qs.map(q => <View key={q.id} style={{ flex: 1 }}><Bar frac={q.claimed ? 1 : 0} h={5} /></View>)}
      </View>
    </Panel>
  );
}

// set completion: bounty only, at 25 / 50 / 75 / 100% of a set's card numbers
export function SetBounties({ pts, busy, run }) {
  const d = useData(), c = useTheme();
  const [all, setAll] = useState(false);
  const list = useMemo(() => setProgress(d).filter(x => x.have > 0).sort((a, b) => b.pct - a.pct || b.have - a.have), [d.cat, d.owned]);
  if (pts.bounty == null) return null;
  const ready = list.flatMap(x => stepsReady(x, pts.sets).map(([p, amt]) => ({ x, p, amt })));
  const claimAll = () => run(async () => {
    let got = 0;
    for (const r of ready) { try { await pts.claimSet(r.x, r.p); got += r.amt; } catch (e) { toast(e.message); break; } }
    if (got) { haptic('success'); toast(`+${berries(got, true)} bounty from your sets`); }
  });
  const shown = all ? list : list.slice(0, 4);
  return (
    <Panel title="Complete sets" right={<T mute size={12.5}>Bounty only</T>}>
      <T mute size={12.5}>{`Own 25%, 50%, 75% and all of a set’s card numbers to raise your bounty (${SET_STEPS.map(([p, a]) => `${p}%: ${berries(a, true)}`).join(' · ')}).`}</T>
      {!list.length ? <T mute size={13.5}>Add cards with their card numbers (like OP05-119) and your sets show up here.</T> : null}
      {shown.map(x => {
        const next = SET_STEPS.find(([p]) => !pts.sets.has(`set:${x.code}:${p}`));
        const r = stepsReady(x, pts.sets);
        return (
          <Pressable key={x.code} onPress={() => router.push({ pathname: '/set/[id]', params: { id: x.set } })} accessibilityRole="button" accessibilityLabel={`${x.code}: ${x.have} of ${x.size}`}
            style={{ gap: 6, paddingVertical: 4 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <T w="semi" size={14} style={{ flex: 1 }} numberOfLines={1}>{`${x.code} · ${x.name}`}</T>
              <T mute size={12.5}>{`${x.have} of ${x.size}`}</T>
            </View>
            <Bar frac={x.pct} h={6} />
            <T size={12} style={{ color: r.length ? c.accent : c.mute }}>
              {r.length ? `${r.map(([p]) => `${p}%`).join(', ')} reached: claim ${berries(r.reduce((s, [, a]) => s + a, 0), true)}`
                : next ? `${Math.ceil((x.size * next[0]) / 100) - x.have} more for ${next[0]}% (${berries(next[1], true)})` : 'Complete'}
            </T>
          </Pressable>
        );
      })}
      {list.length > 4 ? <Button ghost onPress={() => setAll(a => !a)}>{all ? 'Show fewer' : `Show all ${list.length} sets`}</Button> : null}
      {ready.length ? <Button disabled={busy} icon="trophy-outline" onPress={claimAll}>{`Claim ${berries(ready.reduce((s, r) => s + r.amt, 0), true)} bounty`}</Button> : null}
    </Panel>
  );
}

// opt-in evening reminder (only on days your streak would end), needs phone notifications on
export function ReminderRow({ pts }) {
  const c = useTheme();
  const [busy, setBusy] = useState(false);
  if (pts.mode !== 'server' || pts.bounty == null) return null;
  const flip = async v => {
    setBusy(true);
    try { await pts.setRemind(v); toast(v ? 'You’ll get one reminder at about 7pm, only on days your streak would end' : 'Streak reminder off'); }
    catch (e) { toast(e.message || String(e)); } finally { setBusy(false); }
  };
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 }}>
      <Ionicons name="alarm-outline" size={18} color={c.mute} />
      <View style={{ flex: 1 }}>
        <T size={13.5}>Remind me at 7pm if my streak’s about to end</T>
        <T mute size={11.5}>One notification at most, and only if you haven’t checked in. Needs notifications on (Settings).</T>
      </View>
      <Switch value={pts.remind} disabled={busy} onValueChange={flip} accessibilityLabel="Streak reminder"
        trackColor={{ true: c.accent, false: c.raise }} thumbColor={pts.remind ? c.onAccent : '#ccc'} />
    </View>
  );
}
