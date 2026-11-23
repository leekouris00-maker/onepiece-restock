import React, { useMemo, useState } from 'react';
import { FlatList, View } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useData, clean } from '../../src/data';
import { useTheme } from '../../src/theme';
import { CardRow } from '../../src/rows';
import { Chip, Empty, T } from '../../src/ui';
import { setProgress } from '../../src/sets';
import { usePref } from '../../src/prefs';
import { BoxEV } from '../../src/ev';
import { Progress } from '../../src/progress';
import { ChipRow } from '../../src/screen';
import { useWide } from '../../src/layout';

const SORTS = [['price', 'Highest price'], ['num', 'Card number'], ['move', 'Biggest move']];

export default function SetScreen() {
  const { id } = useLocalSearchParams();
  const d = useData(), c = useTheme(), wide = useWide();
  const [type, setType] = useState('card');
  const [ebay, setEbay] = useState(false);
  const [sort, setSort] = useState('price');
  const [missingOnly, setMissingOnly] = useState(false);
  const [master, setMaster] = usePref('masterSet', false);
  const mine = String(id).startsWith('mine:');
  const set = mine ? { name: String(id).slice(5), code: '' } : d.cat?.byId[id];
  const all = useMemo(() => (mine ? d.custom.filter(x => x.g === id) : (d.cat?.list || []).filter(x => x.g === id)), [d.cat, d.custom, id]);
  const prog = useMemo(() => (mine || !d.cat ? null : setProgress(d, id, master)), [d.cat, d.owned, id, master]);
  const list = useMemo(() => {
    let l = all;
    if (missingOnly && prog) { const miss = new Set(prog.missing.map(x => x.k)); l = master ? l.filter(x => miss.has(x.k)) : prog.missing; }
    else if (ebay) l = l.filter(x => d.salesOf(x.k).length || d.compOf(x.k));
    else if (!mine) l = l.filter(x => x.t === type);
    const by = { price: (a, b) => (b.m ?? -1) - (a.m ?? -1), num: (a, b) => a.num.localeCompare(b.num, undefined, { numeric: true }), move: (a, b) => Math.abs(d.move(b) ?? 0) - Math.abs(d.move(a) ?? 0) };
    return [...l].sort(by[sort]);
  }, [all, type, ebay, sort, d.sales, d.watch, d.comps, missingOnly, prog, master]);
  if (!set) return <Empty>{d.catError || 'Loading…'}</Empty>;
  const top = list.filter(x => x.m != null).reduce((a, x) => (!a || x.m > a.m ? x : a), null);
  return (
    <>
      <Stack.Screen options={{ title: set.code || 'My cards' }} />
      <FlatList key={wide ? 'wide' : 'phone'} numColumns={wide ? 2 : 1} columnWrapperStyle={wide ? { paddingHorizontal: 14, gap: 12 } : undefined}
        data={list} keyExtractor={x => x.k} initialNumToRender={20} windowSize={9}
        style={{ width: '100%', maxWidth: wide ? 1100 : undefined, alignSelf: 'center' }}
        ListHeaderComponent={<View style={{ padding: wide ? 32 : 18, paddingBottom: 18, gap: 10 }}>
          <T serif size={32} style={{ lineHeight: 36 }}>{set.name}</T>
          <T mute size={13.5}>{[set.date && 'released ' + set.date, `${list.length} ${type === 'sealed' ? 'products' : 'cards'}`, top && `top ${clean(top.n)} ${d.money(top.m)}`].filter(Boolean).join(' · ')}</T>
          {prog && prog.total && d.session ? <View style={{ gap: 8, padding: 14, borderRadius: 16, backgroundColor: c.panel }}>
            <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}>
              <T w="bold" size={15}>{master ? 'Master set' : 'Set'}: {prog.have} of {prog.total}</T>
              <T w="bold" size={15} style={{ color: c.accent }}>{Math.round((prog.have / prog.total) * 100)}%</T>
            </View>
            <Progress v={prog.have / prog.total} />
            <T mute size={12.5}>{prog.missing.length ? `${prog.missing.length} to go · about ${d.money(prog.cost)} to finish at TCGplayer prices${master ? '' : ', cheapest version of each'}${prog.unpriced ? ` (${prog.unpriced} without a price)` : ''}` : 'Complete!'}</T>
            <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>
              <Chip on={missingOnly} onPress={() => { setMissingOnly(!missingOnly); setEbay(false); setType('card'); }}>{`Missing ${prog.missing.length}`}</Chip>
              <Chip on={!!master} onPress={() => setMaster(!master)}>Count every version</Chip>
            </View>
          </View> : null}
          {!mine && d.cat ? <BoxEV setId={id} compact /> : null}
          <ChipRow style={{ paddingVertical: 4 }}>
            {!mine && [['card', 'Cards'], ['don', 'DON!!'], ['sealed', 'Sealed']].map(([v, l]) => <Chip key={v} on={!ebay && !missingOnly && type === v} onPress={() => { setEbay(false); setMissingOnly(false); setType(v); }}>{l}</Chip>)}
            <Chip on={ebay} onPress={() => { setEbay(!ebay); setMissingOnly(false); }}>Has eBay prices</Chip>
          </ChipRow>
          <ChipRow>
            {SORTS.map(([v, l]) => <Chip key={v} on={sort === v} onPress={() => setSort(v)} style={{ minHeight: 32 }}>{l}</Chip>)}
          </ChipRow>
        </View>}
        ListEmptyComponent={<Empty>{missingOnly ? 'Nothing missing. Set complete!' : ebay ? 'No eBay prices in this set yet. Open a card to track it or log a sale.' : 'Nothing of this type here.'}</Empty>}
        renderItem={({ item }) => (wide ? <View style={{ flex: 1, maxWidth: '50%' }}><CardRow card={item} /></View> : <CardRow card={item} />)} contentContainerStyle={{ paddingBottom: 40, backgroundColor: c.bg }} />
    </>
  );
}
