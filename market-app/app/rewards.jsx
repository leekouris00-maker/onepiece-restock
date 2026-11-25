// Rewards (test phase, 25 Nov 2026): earn points by using the app, swap them in the points shop.
// Fixed rewards only, nothing left to chance: a daily check-in (opens today's movers), streak bonuses,
// and one-off milestones for building your collection. Points are saved to your account (src/points.js).
import React, { useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, Panel, T } from '../src/ui';
import { CardRow } from '../src/rows';
import { OwnedRow } from '../src/tiles';
import { usePref } from '../src/prefs';
import { toast } from '../src/toast';
import { haptic } from '../src/haptic';
import { affected, eventsNow, cardsFor, myNums, newsWithin, niceDate, useGame } from '../src/game';
import { CHECKIN, MILESTONES, MILESTONE_TOTAL, MONTH_BONUS, POINT_AUD, WEEK_BONUS, dayKey, nextBonus, usePoints } from '../src/points';

const WEEKDAY = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

export default function Rewards() {
  const d = useData(), c = useTheme();
  const pts = usePoints();
  useTrack('rewards');
  useFocusEffect(useCallback(() => { pts.reload(); }, [pts.reload]));
  const [busy, setBusy] = useState(false);
  const can = pts.mode === 'server' || pts.mode === 'device';
  const [scanned] = usePref('didScan', false);
  const [imported] = usePref('didImport', false);
  const [owner, setOwner] = useState(false);
  const nb = nextBonus(pts.streak);
  const live = d.owned.filter(o => o.status !== 'sold');

  // today's movers in your own collection (since yesterday; falls back to the week when nothing moved)
  const mine = useMemo(() => {
    const rows = span => live.map(o => ({ o, a: d.unitAt(o, 0), b: d.unitAt(o, span) })).filter(x => x.a && x.b && Math.abs(x.a - x.b) / x.b >= 0.005)
      .sort((x, y) => Math.abs(y.a - y.b) * (Number(y.o.qty) || 1) - Math.abs(x.a - x.b) * (Number(x.o.qty) || 1));
    const day = rows(1);
    const list = day.length ? day : rows(7);
    const change = list.reduce((s, x) => s + (x.a - x.b) * (Number(x.o.qty) || 1), 0);
    return { list: list.slice(0, 5).map(x => x.o), span: day.length ? 'since yesterday' : 'this week', change };
  }, [d.owned, d.cat]);
  const { game, meta } = useGame();
  const [deckText] = usePref('deckText', '');
  const mn = useMemo(() => myNums(d, deckText), [d.owned, d.cat, deckText]);
  const hits = useMemo(() => affected(game, mn.own, mn.deck), [game, mn]);
  const news = newsWithin(game, 14), onNow = eventsNow(game);
  const watchMoves = useMemo(() => (d.favs || []).map(f => ({ f, x: d.card(f.card) })).filter(y => y.x && d.move(y.x) != null && Math.abs(d.move(y.x)) >= 1)
    .sort((a, b) => Math.abs(d.move(b.x)) - Math.abs(d.move(a.x))).slice(0, 3), [d.favs, d.cat]);
  const market = useMemo(() => (d.cat ? d.cat.list.filter(x => x.t === 'card' && x.m >= 5 && d.move(x) != null && Math.abs(d.move(x)) <= 75).sort((a, b) => d.move(b) - d.move(a)).slice(0, 5) : []), [d.cat]);

  const state = { items: live.length, scanned: !!scanned, imported: !!imported, alert: (d.favs || []).some(f => f.below != null || f.above != null) };
  const claimable = MILESTONES.filter(m => !pts.ms[m.id] && m.done(state));

  const run = async fn => { if (busy) return; setBusy(true); try { await fn(); } catch (e) { toast(e.message || String(e)); } finally { setBusy(false); } };
  const checkIn = () => run(async () => {
    const r = await pts.checkIn();
    if (!r || r.already) { toast('Already checked in today'); return; }
    haptic('success');
    toast(r.bonus ? `Checked in: +${CHECKIN} points, and +${r.bonus} for ${r.streak} days in a row` : `Checked in: +${CHECKIN} points · ${r.streak}-day streak`);
  });
  const claim = m => run(async () => { if (await pts.claim(m)) { haptic('success'); toast(`+${m.pts} points: ${m.label}`); } });
  const claimAll = () => run(async () => { let n = 0; for (const m of claimable) { try { if (await pts.claim(m)) n += m.pts; } catch {} } toast(n ? `+${n} points from milestones` : 'Nothing new to claim yet'); });

  // the last 7 days: checked in / covered by the monthly freeze / missed / today
  const week = Array.from({ length: 7 }, (_, i) => { const t = new Date(); t.setDate(t.getDate() - (6 - i)); return t; });

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ padding: 18, paddingBottom: 60, gap: 16, width: '100%', maxWidth: 680, alignSelf: 'center' }}>
      <View style={{ alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: c.soft }}>
        <T size={12} w="semi" style={{ color: c.accent }}>{pts.mode === 'device' ? 'PREVIEW · points on this device only · nothing is sent' : 'TEST PHASE · swaps are recorded · nothing ships yet'}</T>
      </View>
      <View style={{ gap: 4 }}>
        <T w="bold" size={30}>Rewards</T>
        <T mute size={14.5}>Earn points for using the app and swap them in the points shop. Every reward is fixed: no chance, no purchase.</T>
      </View>

      {pts.mode === 'signedout' ? <Panel>
        <T w="bold" size={18}>Sign in to earn points</T>
        <T mute size={14}>Points are saved to your account, so they follow you to any device.</T>
        <Button onPress={() => router.push({ pathname: '/account', params: { back: '1' } })}>Sign in or create an account</Button>
      </Panel> : null}
      {pts.mode === 'loading' ? <T mute>Loading your points…</T> : null}
      {pts.mode === 'error' ? <Panel><T w="semi">Couldn’t load your points</T><T mute size={13.5}>{pts.error}</T><Button ghost onPress={pts.reload}>Try again</Button></Panel> : null}
      {pts.mode === 'device' ? <T size={12.5} style={{ color: c.mute }}>Points are on this device for now: the rewards database update (supabase/2026-11-25-rewards.sql) hasn’t been run yet.</T> : null}

      {can ? <>
      {/* balance */}
      <Pressable onPress={() => router.push('/shop')} accessibilityRole="button" accessibilityLabel="Points shop"
        style={({ pressed, hovered }) => ({ flexDirection: 'row', alignItems: 'center', gap: 14, padding: 14, borderRadius: 18, backgroundColor: pressed || hovered ? c.raise : c.panel, borderWidth: 1, borderColor: c.line })}>
        <View style={{ width: 46, height: 46, borderRadius: 14, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
          <Ionicons name="sparkles" size={22} color={c.accent} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <T w="bold" size={22}>{pts.pts.toLocaleString()} points</T>
          <T mute size={12.5}>{`About A$${(pts.pts * POINT_AUD).toFixed(2)} in the shop`}</T>
        </View>
        <T w="semi" size={14} style={{ color: c.accent }}>Points shop ›</T>
      </Pressable>

      {/* daily check-in */}
      <Panel>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <T w="bold" size={18}>Morning Log</T>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <Ionicons name="flame" size={16} color={pts.streak ? c.accent : c.mute} />
            <T w="semi" size={14}>{pts.streak ? `${pts.streak}-day streak` : 'No streak yet'}</T>
          </View>
        </View>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          {week.map((t, i) => {
            const k = dayKey(t), on = pts.days.includes(k), isToday = i === 6;
            return (
              <View key={k} style={{ alignItems: 'center', gap: 5 }}>
                <T mute size={11.5}>{WEEKDAY[t.getDay()]}</T>
                <View style={{ width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center',
                  backgroundColor: on ? c.accent : c.soft, borderWidth: isToday && !on ? 1.5 : 0, borderColor: c.accent, borderStyle: 'dashed' }}>
                  {on ? <Ionicons name="checkmark" size={18} color={c.onAccent} /> : <T size={12} mute>{t.getDate()}</T>}
                </View>
              </View>
            );
          })}
        </View>
        <T mute size={12.5}>{`+${CHECKIN} a day · ${nb.inDays} more ${nb.inDays === 1 ? 'day' : 'days'} in a row for +${nb.pts} · ${pts.freezeLeft ? 'one missed day this month is covered' : 'this month’s missed-day cover is used'}`}</T>
        {pts.checkedIn ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44 }}>
            <Ionicons name="checkmark-circle" size={20} color={c.accent} />
            <T w="semi" size={14.5}>Today’s log is open below. Come back tomorrow for +{CHECKIN}.</T>
          </View>
          : <Button icon="newspaper-outline" disabled={busy} onPress={checkIn}>{`Open today’s Morning Log · +${CHECKIN} points`}</Button>}
        {!pts.checkedIn ? <T mute size={12.5}>Your cards’ overnight moves, ban and meta news, prize events on now, and the market’s top movers.</T> : null}
      </Panel>

      {/* what the check-in opens */}
      {pts.checkedIn ? <>
        <Panel title={`Your collection ${mine.span}`} right={mine.list.length ? <T w="semi" size={14} style={{ color: mine.change >= 0 ? c.up : c.down }}>{mine.change >= 0 ? '▲ +' : '▼ -'}{d.aud(Math.abs(mine.change))}</T> : null}>
          {!d.session ? <T mute size={13.5}>Sign in and add cards to see your own movers here.</T>
            : !mine.list.length ? <T mute size={13.5}>Nothing you own moved this week.</T>
            : mine.list.map(o => <OwnedRow key={o.id} o={o} />)}
        </Panel>
        <Panel title="In the game" right={<Pressable onPress={() => router.push('/meta')} hitSlop={8}><T w="semi" size={13.5} style={{ color: c.accent }}>Ban & Meta</T></Pressable>}>
          {hits.some(h => h.clash) ? <T size={13.5} style={{ color: c.down }}>{`Your saved deck breaks the ban list (${hits.filter(h => h.clash).map(h => h.num).join(', ')}). Open Ban & Meta.`}</T> : null}
          {news.length ? news.map(n => (
            <Pressable key={n.id} onPress={() => router.push('/meta')} style={{ gap: 2 }}>
              <T w="semi" size={14}>{n.title}</T>
              <T mute size={12.5}>{`${n.effective > dayKey() ? 'From' : 'Since'} ${niceDate(n.effective)}${hits.some(h => (n.cards || []).includes(h.num)) ? ' · affects cards you have' : ''}`}</T>
            </Pressable>
          )) : <T mute size={13.5}>No ban list changes in the last two weeks.</T>}
          {meta && meta.rising.length ? <T size={13}>{'Showing up more in winning decks: ' + meta.rising.slice(0, 3).map(r => r.num).join(', ')}</T> : null}
        </Panel>
        {onNow.length ? <Panel title="Prize events on now" right={<Pressable onPress={() => router.push('/promos')} hitSlop={8}><T w="semi" size={13.5} style={{ color: c.accent }}>All</T></Pressable>}>
          {onNow.slice(0, 3).map(e => {
            const top = (e.prizes || []).flatMap(p => p.cards || []).map(num => cardsFor(d, num)[0]).filter(Boolean)[0];
            return (
              <Pressable key={e.id} onPress={() => router.push('/promos')} style={{ flexDirection: 'row', gap: 10, alignItems: 'center' }}>
                <View style={{ flex: 1 }}><T w="semi" size={14} numberOfLines={1}>{e.name}</T><T mute size={12}>{`until ${niceDate(e.end)}`}</T></View>
                {top && top.m ? <T size={12.5} w="semi">{`${top.num} ${d.money(top.m)}`}</T> : null}
              </Pressable>
            );
          })}
        </Panel> : null}
        {watchMoves.length ? <Panel title="Your watchlist this week">
          {watchMoves.map(({ f, x }) => (
            <Pressable key={f.card} onPress={() => router.push({ pathname: '/card/[k]', params: { k: x.k } })} style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
              <T size={13.5} style={{ flex: 1 }} numberOfLines={1}>{`${x.num} ${clean(x.n)}`}</T>
              <T size={13} w="semi" style={{ color: d.move(x) >= 0 ? c.up : c.down }}>{`${d.move(x) >= 0 ? '▲' : '▼'}${Math.abs(d.move(x)).toFixed(1)}%  ${d.money(x.m)}`}</T>
            </Pressable>
          ))}
        </Panel> : null}
        <Panel title="Top of the market this week" right={<Pressable onPress={() => router.push('/movers')} hitSlop={8}><T w="semi" size={13.5} style={{ color: c.accent }}>See all</T></Pressable>}>
          <View style={{ marginHorizontal: -16 }}>{market.map(x => <CardRow key={x.k} card={x} showSet />)}</View>
        </Panel>
      </> : null}

      {/* milestones */}
      <Panel title="Milestones" right={<T mute size={12.5}>{`${Object.keys(pts.ms).length} of ${MILESTONES.length} · up to ${MILESTONE_TOTAL} pts`}</T>}>
        <T mute size={12.5}>One-off rewards for setting up your collection. Each pays once.</T>
        {MILESTONES.map(m => {
          const got = !!pts.ms[m.id], ready = !got && m.done(state);
          return (
            <View key={m.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 48 }}>
              <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: got ? c.accentDim : c.soft, alignItems: 'center', justifyContent: 'center' }}>
                <Ionicons name={got ? 'checkmark' : m.icon} size={18} color={got || ready ? c.accent : c.mute} />
              </View>
              <View style={{ flex: 1 }}>
                <T w="semi" size={14} style={got ? { color: c.mute } : null}>{m.label}</T>
                <T mute size={12}>{got ? 'Done' : m.sub}</T>
              </View>
              {got ? <T w="semi" size={13.5} mute>+{m.pts}</T>
                : ready ? <Pressable disabled={busy} onPress={() => claim(m)} accessibilityRole="button" accessibilityLabel={`Claim ${m.pts} points`}
                    style={({ pressed }) => ({ paddingHorizontal: 14, minHeight: 36, borderRadius: 18, justifyContent: 'center', backgroundColor: pressed ? c.accentDim : c.accent })}>
                    <T w="bold" size={13.5} style={{ color: c.onAccent }}>Claim +{m.pts}</T>
                  </Pressable>
                : <Pressable onPress={() => router.push(m.go)} hitSlop={8} accessibilityRole="button" accessibilityLabel={m.label}
                    style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                    <T w="semi" size={13.5} mute>+{m.pts}</T><Ionicons name="chevron-forward" size={15} color={c.mute} />
                  </Pressable>}
            </View>
          );
        })}
        {claimable.length > 1 ? <Button ghost disabled={busy} onPress={claimAll}>{`Claim all (+${claimable.reduce((s, m) => s + m.pts, 0)})`}</Button> : null}
      </Panel>

      {/* history */}
      {pts.log.length ? <Panel title="Your points">
        {pts.log.slice(0, 10).map((e, i) => (
          <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <T size={13.5} style={{ flex: 1 }} numberOfLines={1}>{e.why}</T>
            <T mute size={12}>{new Date(e.at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })}</T>
            <T w="semi" size={14} style={{ width: 64, textAlign: 'right', color: e.delta >= 0 ? c.up : c.down }}>{e.delta >= 0 ? '+' : '−'}{Math.abs(e.delta).toLocaleString()}</T>
          </View>
        ))}
      </Panel> : null}

      </> : null}

      <Panel title="How points work (draft)">
        <T size={13.5} mute>{`Check in once a day for +${CHECKIN}. Every 7th day in a row adds +${WEEK_BONUS}, and day 30 adds +${MONTH_BONUS}. One missed day a month doesn’t break your streak. Milestones pay once each.`}</T>
        <T size={13.5} mute>Points are free and fixed: nothing is left to chance and nothing can be bought. They have no cash value, can’t be sold or moved to another account, and paid members earn exactly the same. One account per person; points from extra accounts or automation are removed. Changes to how points work get at least 30 days’ notice, with a chance to use your points first. Points expire after 12 months without signing in. To run Rewards, the app records your check-ins, points and swaps, plus a daily count of a few things you do in the app (see the privacy policy).</T>
      </Panel>

      {/* owner numbers */}
      <Pressable onPress={() => setOwner(o => !o)} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name={owner ? 'chevron-down' : 'chevron-forward'} size={16} color={c.mute} />
        <T w="semi" size={14} mute>What this would cost you</T>
      </Pressable>
      {owner ? <Panel>
        <Row label="Most one person can earn in a month (every day + bonuses)" value={`${(30 * CHECKIN + 4 * WEEK_BONUS + MONTH_BONUS).toLocaleString()} pts · A$${((30 * CHECKIN + 4 * WEEK_BONUS + MONTH_BONUS) * POINT_AUD).toFixed(2)}`} />
        <Row label="Milestones, once per new person" value={`${MILESTONE_TOTAL} pts · A$${(MILESTONE_TOTAL * POINT_AUD).toFixed(2)}`} />
        <View style={{ height: 1, backgroundColor: c.line }} />
        <Row label="100 people checking in every day, per month (if every point is spent)" value={`A$${Math.round((30 * CHECKIN + 4 * WEEK_BONUS + MONTH_BONUS) * POINT_AUD * 100).toLocaleString()}`} bold />
        <T mute size={12}>That’s the ceiling: most people skip days, and points only cost you when they’re swapped. Store credit costs you less than its face value, and packs cost what you paid for them.</T>
      </Panel> : null}
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
