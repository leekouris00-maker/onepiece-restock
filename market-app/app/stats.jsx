// Owner stats (25 Nov 2026): is the app working? Only the owner's account can see this (checked by the database).
// Numbers come from owner_stats() in supabase/2026-11-25-rewards.sql: sign-ups, who comes back, check-ins,
// points owed, swaps to send, and which features get used.
import React, { useCallback, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { supabase, useData } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, Panel, T } from '../src/ui';
import { toast } from '../src/toast';
import { POINT_AUD } from '../src/points';

const FEATURE = { open: 'Opened the app', checkin: 'Daily check-in', search: 'Searched', card_add: 'Added to collection', scan_add: 'Scanned and added', alert_set: 'Set a price alert',
  import: 'Imported a CSV', export: 'Exported a CSV', trade: 'Trade calculator', deck: 'Deck price', sets: 'Set progress', sales: 'Sales report', watchlist: 'Watchlist',
  rewards: 'Rewards page', shop: 'Points shop', share: 'Shared a group', meta: 'Ban & Meta Radar', promos: 'Promos & prize events' };
const pct = ([r, e]) => (e ? `${Math.round((r / e) * 100)}%` : '–');

export default function Stats() {
  const d = useData(), c = useTheme();
  const [st, setSt] = useState({ status: 'loading' });
  const load = useCallback(async () => {
    if (!supabase || !d.session) { setSt({ status: 'signedout' }); return; }
    const who = await supabase.rpc('am_owner');
    if (who.error) { setSt({ status: /could not find|does not exist/i.test(who.error.message) || who.error.code === 'PGRST202' ? 'missing' : 'error', error: who.error.message }); return; }
    if (!who.data.owner) { setSt({ status: who.data.claimable ? 'claimable' : 'notowner' }); return; }
    const r = await supabase.rpc('owner_stats');
    if (r.error) setSt({ status: 'error', error: r.error.message }); else setSt({ status: 'ok', s: r.data });
  }, [d.session]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const claim = async () => { const r = await supabase.rpc('claim_owner'); if (r.error) toast(r.error.message); else { toast(r.data ? 'You’re the owner now' : 'Someone else is already the owner'); load(); } };
  const setSwap = async (id, status) => { const r = await supabase.rpc('owner_set_swap', { rid: id, new_status: status }); if (r.error) toast(r.error.message); else { toast(status === 'sent' ? 'Marked as sent' : 'Cancelled, points returned'); load(); } };

  const s = st.s;
  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ padding: 18, paddingBottom: 60, gap: 14, width: '100%', maxWidth: 820, alignSelf: 'center' }}>
      <View style={{ gap: 4 }}>
        <T w="bold" size={30}>Owner stats</T>
        <T mute size={14}>Is the app working? Only your account can see this.</T>
      </View>

      {st.status === 'loading' ? <T mute>Loading…</T> : null}
      {st.status === 'signedout' ? <Panel><T>Sign in with the owner account to see stats.</T><Button onPress={() => router.push({ pathname: '/account', params: { back: '1' } })}>Sign in</Button></Panel> : null}
      {st.status === 'missing' ? <Panel><T w="semi">One step first</T><T mute size={14}>Run supabase/2026-11-25-rewards.sql in Supabase → SQL Editor, then come back.</T><Button ghost onPress={load}>Check again</Button></Panel> : null}
      {st.status === 'error' ? <Panel><T w="semi">Couldn’t load stats</T><T mute size={13.5}>{st.error}</T><Button ghost onPress={load}>Try again</Button></Panel> : null}
      {st.status === 'notowner' ? <Panel><T>Only the owner can see this page.</T></Panel> : null}
      {st.status === 'claimable' ? <Panel>
        <T w="semi" size={16}>No owner set yet</T>
        <T mute size={14}>The first account to press this becomes the owner and is the only one that can see stats and manage swaps. Do it from your own account.</T>
        <Button onPress={claim}>Make me the owner</Button>
      </Panel> : null}

      {s ? <>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <Big label="Accounts" value={s.users} sub={`${s.new7} new this week`} />
          <Big label="Active today" value={s.active_today} sub={`${s.active7} this week · ${s.active30} this month`} />
          <Big label="Points owed" value={`A$${(s.points.outstanding * POINT_AUD).toFixed(2)}`} sub={`${s.points.outstanding.toLocaleString()} pts across ${s.points.holders} people`} />
        </View>

        <Panel title="Do people come back?">
          <T mute size={12.5}>Of the people who signed up long enough ago, how many used the app again on day 1, in week 2 (days 7–13) and in month 2 (days 30–59).</T>
          <Row label="Next day (D1)" value={pct(s.retention.d1)} sub={`${s.retention.d1[0]} of ${s.retention.d1[1]}`} />
          <Row label="Week 2 (D7)" value={pct(s.retention.d7)} sub={`${s.retention.d7[0]} of ${s.retention.d7[1]}`} />
          <Row label="Month 2 (D30)" value={pct(s.retention.d30)} sub={`${s.retention.d30[0]} of ${s.retention.d30[1]}`} />
          <View style={{ height: 1, backgroundColor: c.line }} />
          <Row label="Week 2, people who used Rewards" value={pct(s.retention.d7_rewards)} sub={`${s.retention.d7_rewards[0]} of ${s.retention.d7_rewards[1]}`} />
          <Row label="Week 2, people who didn’t" value={pct(s.retention.d7_no_rewards)} sub={`${s.retention.d7_no_rewards[0]} of ${s.retention.d7_no_rewards[1]}`} />
          <T mute size={12}>If Rewards users come back clearly more often, points are doing their job. With only a few testers, treat these as hints.</T>
        </Panel>

        <Panel title="Check-ins, last 14 days">
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 4, height: 90 }}>
            {s.checkins14.map(x => {
              const max = Math.max(1, ...s.checkins14.map(y => y.n));
              return <View key={x.day} style={{ flex: 1, alignItems: 'center', gap: 4 }}>
                <T size={10.5} mute>{x.n || ''}</T>
                <View style={{ width: '100%', height: Math.max(2, (x.n / max) * 60), borderRadius: 4, backgroundColor: x.n ? c.accent : c.soft }} />
              </View>;
            })}
          </View>
          <T mute size={12}>{`${s.checkins14[0].day} to ${s.checkins14[s.checkins14.length - 1].day}`}</T>
        </Panel>

        <Panel title="Points">
          <Row label="Given out" value={s.points.issued.toLocaleString()} sub={`A$${(s.points.issued * POINT_AUD).toFixed(2)}`} />
          <Row label="Swapped" value={s.points.spent.toLocaleString()} sub={`A$${(s.points.spent * POINT_AUD).toFixed(2)} · ${s.points.issued ? Math.round((s.points.spent / s.points.issued) * 100) : 0}% of points given`} />
          <Row label="Still owed" value={s.points.outstanding.toLocaleString()} sub={`A$${(s.points.outstanding * POINT_AUD).toFixed(2)} you could be asked for`} />
          {Object.keys(s.milestones || {}).length ? <T mute size={12.5}>{'Milestones claimed: ' + Object.entries(s.milestones).map(([k, n]) => `${k} ${n}`).join(' · ')}</T> : null}
        </Panel>

        <Panel title={`Swaps (${s.swaps.filter(x => x.status === 'requested').length} waiting)`}>
          {!s.swaps.length ? <T mute size={13.5}>No swaps yet.</T> : s.swaps.map(x => (
            <View key={x.id} style={{ gap: 6, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: c.line }}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 10 }}>
                <T w="semi" size={14} style={{ flex: 1 }}>{x.label}</T>
                <T size={13} style={{ color: x.status === 'requested' ? c.accent : c.mute }}>{x.status === 'requested' ? 'waiting' : x.status}</T>
              </View>
              <T mute size={12}>{`${x.email || 'unknown'} · ${x.cost.toLocaleString()} pts · ${new Date(x.at).toLocaleString('en-AU', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}`}</T>
              {x.status === 'requested' ? <View style={{ flexDirection: 'row', gap: 14 }}>
                <Pressable onPress={() => setSwap(x.id, 'sent')} hitSlop={8}><T w="semi" size={13.5} style={{ color: c.accent }}>Mark sent</T></Pressable>
                <Pressable onPress={() => setSwap(x.id, 'cancelled')} hitSlop={8}><T w="semi" size={13.5} style={{ color: c.down }}>Cancel and refund</T></Pressable>
              </View> : null}
            </View>
          ))}
        </Panel>

        <Panel title="What people use (last 30 days)">
          {!s.features.length ? <T mute size={13.5}>Nothing recorded yet.</T> : s.features.map(f => (
            <Row key={f.name} label={FEATURE[f.name] || f.name} value={`${f.people} ${f.people === 1 ? 'person' : 'people'}`} sub={`${f.times} times`} />
          ))}
        </Panel>
        <T mute size={12}>{`As of ${s.today} (Melbourne). Pull down or reopen to refresh.`}</T>
        <Button ghost onPress={load}>Refresh</Button>
      </> : null}
    </ScrollView>
  );
}

function Big({ label, value, sub }) {
  const c = useTheme();
  return (
    <View style={{ flexGrow: 1, flexBasis: 200, padding: 14, borderRadius: 18, backgroundColor: c.panel, gap: 2 }}>
      <T mute size={12.5}>{label}</T>
      <T w="bold" size={26}>{String(value)}</T>
      <T mute size={12}>{sub}</T>
    </View>
  );
}

function Row({ label, value, sub }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
      <T size={14} style={{ flex: 1 }}>{label}</T>
      <View style={{ alignItems: 'flex-end' }}>
        <T w="bold" size={15}>{value}</T>
        {sub ? <T mute size={11.5}>{sub}</T> : null}
      </View>
    </View>
  );
}
