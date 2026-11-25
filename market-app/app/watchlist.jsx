// Cards you follow without owning them, and the price alerts you set on them
import React from 'react';
import { Pressable, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, CardArt, Change, Empty, Note, Panel, T } from '../src/ui';
import { Screen } from '../src/screen';
import { versionTag } from '../src/find';
import { toast } from '../src/toast';
import { AlertList } from '../src/alerts';

export default function Watchlist() {
  useTrack('watchlist');
  const d = useData(), c = useTheme();
  const list = d.favs.map(f => ({ f, card: d.card(f.card) })).filter(x => x.card)
    .sort((a, b) => (d.refPrice(b.card).usd ?? -1) - (d.refPrice(a.card).usd ?? -1));
  return (
    <Screen max={820}>
      <T mute size={13.5}>Cards you’re keeping an eye on. Star any card on its page to add it; set a price alert there too.</T>
      {d.favLocal && d.session ? <Note style={{ marginTop: 12 }}>Your watchlist is saved on this device only for now. Once supabase/watchlist.sql has been run in Supabase, it saves to your account.</Note> : null}
      <View style={{ marginTop: 14, gap: 14 }}>
        <AlertList />
        {!list.length ? <View style={{ gap: 12 }}>
          <Empty>Nothing on your watchlist yet.</Empty>
          <Button ghost icon="search" onPress={() => router.push('/search')}>Find a card</Button>
        </View> : <Panel style={{ gap: 4 }}>
          {list.map(({ f, card }) => {
            const r = d.refPrice(card), mv = d.move(card);
            return (
              <View key={f.card} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 }}>
                <Pressable onPress={() => router.push({ pathname: '/card/[k]', params: { k: card.k } })} accessibilityRole="button"
                  style={({ pressed }) => ({ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, opacity: pressed ? 0.6 : 1 })}>
                  <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={40} />
                  <View style={{ flex: 1, gap: 2 }}>
                    <T w="semi" size={14.5} numberOfLines={1}>{clean(card.n)}</T>
                    <T size={12.5} mute numberOfLines={1}>{[card.num, versionTag(d.cat, card)].filter(Boolean).join(' · ')}</T>
                    {f.below != null || f.above != null || f.deal_below != null ? <T size={12} style={{ color: c.accent }}>{[f.below != null && `alert below ${d.aud(Number(f.below))}`, f.above != null && `above ${d.aud(Number(f.above))}`, f.deal_below != null && `deals under A$${Number(f.deal_below)}`].filter(Boolean).join(' · ')}</T> : null}
                  </View>
                  <View style={{ alignItems: 'flex-end', gap: 2 }}>
                    <T w="bold" size={14.5}>{d.money(r.usd)}</T>
                    {mv != null ? <Change now={card.m} then={card.m / (1 + mv / 100)} aud={d.aud} size={12} pctOnly /> : <T size={11.5} mute>{r.src}</T>}
                  </View>
                </Pressable>
                <Pressable onPress={() => d.unFav(card.k).then(() => toast('Removed from watchlist', { action: { label: 'Undo', onPress: () => d.setFav(card.k, f) } }), e => toast(e.message))}
                  hitSlop={8} accessibilityLabel="Remove from watchlist" style={{ width: 36, height: 36, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name="star" size={20} color={c.accent} />
                </Pressable>
              </View>
            );
          })}
        </Panel>}
        <T mute size={12}>Alerts are checked each time you open the app (prices update once a day). Phone notifications aren’t set up yet.</T>
      </View>
    </Screen>
  );
}
