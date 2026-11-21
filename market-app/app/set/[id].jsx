import React, { useMemo, useState } from 'react';
import { FlatList, View } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useData, clean } from '../../src/data';
import { useTheme } from '../../src/theme';
import { CardRow } from '../../src/rows';
import { Chip, Empty, T } from '../../src/ui';
import { ChipRow } from '../../src/screen';
import { useWide } from '../../src/layout';

const SORTS = [['price', 'Highest price'], ['num', 'Card number'], ['move', 'Biggest move']];

export default function SetScreen() {
  const { id } = useLocalSearchParams();
  const d = useData(), c = useTheme(), wide = useWide();
  const [type, setType] = useState('card');
  const [ebay, setEbay] = useState(false);
  const [sort, setSort] = useState('price');
  const mine = String(id).startsWith('mine:');
  const set = mine ? { name: String(id).slice(5), code: '' } : d.cat?.byId[id];
  const all = useMemo(() => (mine ? d.custom.filter(x => x.g === id) : (d.cat?.list || []).filter(x => x.g === id)), [d.cat, d.custom, id]);
  const list = useMemo(() => {
    let l = all;
    if (ebay) l = l.filter(x => d.salesOf(x.k).length || d.compOf(x.k));
    else if (!mine) l = l.filter(x => x.t === type);
    const by = { price: (a, b) => (b.m ?? -1) - (a.m ?? -1), num: (a, b) => a.num.localeCompare(b.num, undefined, { numeric: true }), move: (a, b) => Math.abs(d.move(b) ?? 0) - Math.abs(d.move(a) ?? 0) };
    return [...l].sort(by[sort]);
  }, [all, type, ebay, sort, d.sales, d.watch, d.comps]);
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
          <ChipRow style={{ paddingVertical: 4 }}>
            {!mine && [['card', 'Cards'], ['don', 'DON!!'], ['sealed', 'Sealed']].map(([v, l]) => <Chip key={v} on={!ebay && type === v} onPress={() => { setEbay(false); setType(v); }}>{l}</Chip>)}
            <Chip on={ebay} onPress={() => setEbay(!ebay)}>Has eBay prices</Chip>
          </ChipRow>
          <ChipRow>
            {SORTS.map(([v, l]) => <Chip key={v} on={sort === v} onPress={() => setSort(v)} style={{ minHeight: 32 }}>{l}</Chip>)}
          </ChipRow>
        </View>}
        ListEmptyComponent={<Empty>{ebay ? 'No eBay prices in this set yet. Open a card to track it or log a sale.' : 'Nothing of this type here.'}</Empty>}
        renderItem={({ item }) => (wide ? <View style={{ flex: 1, maxWidth: '50%' }}><CardRow card={item} /></View> : <CardRow card={item} />)} contentContainerStyle={{ paddingBottom: 40, backgroundColor: c.bg }} />
    </>
  );
}
