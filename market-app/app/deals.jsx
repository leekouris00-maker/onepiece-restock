// Every deal found for your deal alerts, newest first. Tap to open the listing on eBay.
import React from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { useData } from '../src/data';
import { Button, Empty, Note, Panel, T } from '../src/ui';
import { Screen } from '../src/screen';
import { DealRow, useDeals } from '../src/deals';
import { toast } from '../src/toast';

export default function Deals() {
  const d = useData();
  const { list, err, reload, setList } = useDeals();
  const dismiss = async x => { try { await d.dismissDeal(x.item_id); setList(l => l.filter(y => y.item_id !== x.item_id)); } catch (e) { toast(e.message); } };
  const n = d.favs.filter(f => f.deal_below != null).length;
  return (
    <Screen max={820} onRefresh={reload}>
      <T mute size={13.5}>Set a deal price on any card (its page → Price alert). Every 2 hours, live eBay AU Buy It Now listings at or below it show up here and on your phone.</T>
      {err === 'NOT_SET_UP' ? <Note tone="warn" style={{ marginTop: 12 }} title="One database step first">Run supabase/2026-11-24b.sql in Supabase.</Note> : err ? <Note tone="warn" style={{ marginTop: 12 }}>{err}</Note> : null}
      <T size={13} w="semi" style={{ marginTop: 12 }}>{n ? `${n} card${n === 1 ? '' : 's'} with a deal price` : 'No deal prices set yet'}</T>
      {list && !list.length && !err ? <Empty>No deals found yet. They appear when someone lists a card at or under your price.</Empty> : null}
      {list && list.length ? <Panel style={{ marginTop: 12, gap: 2 }}>{list.map(x => <DealRow key={x.item_id} x={x} onDismiss={dismiss} />)}</Panel> : null}
      {!n ? <Button ghost icon="star-outline" onPress={() => router.push('/watchlist')} style={{ marginTop: 14 }}>Open my watchlist</Button> : null}
      <T mute size={11.5} style={{ marginTop: 14 }}>Matched by card number in the listing title, raw cards only. Check the photos: a listing can be a different version of the same number.</T>
    </Screen>
  );
}
