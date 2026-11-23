// A shared binder: read-only view of one group from someone's collection, priced with today's prices
import React, { useEffect, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { Stack, router, useLocalSearchParams } from 'expo-router';
import { clean, supabase, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, CardArt, Empty, Panel, Skel, T } from '../../src/ui';
import { Screen } from '../../src/screen';
import { useLayout } from '../../src/layout';
import { versionTag } from '../../src/find';

export default function Shared() {
  const { id } = useLocalSearchParams();
  const d = useData(), c = useTheme();
  const [rows, setRows] = useState(null), [err, setErr] = useState('');
  useEffect(() => {
    if (!supabase) { setErr('Sharing isn’t set up in this build.'); return; }
    supabase.rpc('get_share', { sid: String(id) }).then(r => { if (r.error) setErr('This link isn’t working.'); else setRows(r.data || []); });
  }, [id]);
  const { inner } = useLayout(900), gap = 12, cols = Math.max(3, Math.min(6, Math.floor((inner + gap) / (130 + gap)))), w = Math.floor((inner - gap * (cols - 1)) / cols);
  const items = useMemo(() => (rows || []).map(r => {
    const card = d.card(r.card), p = d.refPrice(card).usd;
    return { r, card, each: p == null ? null : p * d.fx };
  }).sort((a, b) => (b.each || 0) * b.r.qty - (a.each || 0) * a.r.qty), [rows, d.cat, d.comps]);
  const total = items.reduce((n, x) => n + (x.each || 0) * x.r.qty, 0), count = items.reduce((n, x) => n + x.r.qty, 0);
  const title = rows && rows[0] ? rows[0].title || rows[0].grp : 'Shared cards';
  return (
    <Screen max={900}>
      <Stack.Screen options={{ title: '' }} />
      {err ? <Empty>{err}</Empty> : !rows ? <View style={{ gap: 12 }}><Skel w={200} h={30} /><Skel w={140} h={14} /></View> : !rows.length ? <Empty>Nothing in this group right now, or the link was switched off.</Empty> : <>
        <T mute size={13}>Shared from One Piece Market</T>
        <T head size={28}>{title}</T>
        <T mute size={14} style={{ marginTop: 2 }}>{count} cards · worth about <T w="bold" size={14}>{d.cat ? d.aud(total) : '…'}</T> at today’s prices</T>
        <Panel style={{ marginTop: 16 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap, rowGap: 16 }}>
            {items.map(({ r, card, each }, i) => (
              <Pressable key={i} onPress={() => card && router.push({ pathname: '/card/[k]', params: { k: card.k } })} style={{ width: w, gap: 3 }}>
                <CardArt k={r.card} num={card?.num || r.num} width={w} qty={r.qty} big />
                <T w="semi" size={13} numberOfLines={1} style={{ marginTop: 6 }}>{clean(r.name)}</T>
                <T mute size={11.5} numberOfLines={1}>{[card?.num || r.num, card ? versionTag(d.cat, card) : null, r.cond !== 'Raw' ? r.cond : null, r.lang !== 'EN' ? r.lang : null].filter(Boolean).join(' · ')}</T>
                <T w="bold" size={14}>{each == null ? '–' : d.aud(each * r.qty)}</T>
              </Pressable>
            ))}
          </View>
        </Panel>
        <Button ghost icon="compass-outline" onPress={() => router.replace('/')} style={{ marginTop: 16 }}>Open One Piece Market</Button>
      </>}
    </Screen>
  );
}
