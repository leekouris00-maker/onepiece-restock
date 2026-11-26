import React, { useMemo, useState } from 'react';
import { FlatList, ScrollView, View } from 'react-native';
import { useData, useTrack } from '../src/data';
import { CardRow } from '../src/rows';
import { OwnedRow } from '../src/tiles';
import { Chip, Empty, T } from '../src/ui';

const TABS = [['mine', 'My cards'], ['up', 'Market risers'], ['down', 'Market fallers']];

export default function Movers() {
  useTrack('movers');
  const d = useData();
  const [tab, setTab] = useState(d.session ? 'mine' : 'up');
  const data = useMemo(() => {
    if (!d.cat) return [];
    if (tab === 'mine') return d.owned.filter(o => o.status !== 'sold').map(o => ({ o, a: d.unitAt(o, 0), b: d.unitAt(o, 7) }))
      .filter(x => x.a && x.b && x.a !== x.b).sort((x, y) => Math.abs(y.a - y.b) / y.b - Math.abs(x.a - x.b) / x.b).map(x => ({ key: x.o.id, o: x.o }));
    const l = d.cat.list.filter(x => x.t === 'card' && x.m >= 2 && d.move(x) != null && (tab === 'up' ? d.move(x) > 0 : d.move(x) < 0));
    return l.sort((a, b) => (tab === 'up' ? d.move(b) - d.move(a) : d.move(a) - d.move(b))).slice(0, 100).map(x => ({ key: x.k, card: x }));
  }, [tab, d.cat, d.owned]);
  return (
    <FlatList data={data} keyExtractor={x => x.key} style={{ width: '100%', maxWidth: 900, alignSelf: 'center' }}
      ListHeaderComponent={<View style={{ padding: 18, gap: 10 }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {TABS.map(([v, l]) => <Chip key={v} on={tab === v} onPress={() => setTab(v)}>{l}</Chip>)}
        </ScrollView>
        <T mute size={13}>{tab === 'mine' ? 'Your items with a price change over the last 7 days, biggest first.' : 'Cards worth US$2 or more, biggest 7-day change first.'}</T>
      </View>}
      ListEmptyComponent={<Empty>{tab === 'mine' ? 'None of your items changed price this week.' : 'No changes yet.'}</Empty>}
      renderItem={({ item }) => item.o ? <View style={{ paddingHorizontal: 18 }}><OwnedRow o={item.o} /></View> : <CardRow card={item.card} showSet />}
      contentContainerStyle={{ paddingBottom: 60 }} />
  );
}
