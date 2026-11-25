// Everything you sold in a year: what you got, what you paid, the profit. Australian financial year
// (1 July – 30 June) or calendar year. Not tax advice: a summary to hand to whoever does your tax.
import React, { useMemo, useState } from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { clean, cols, useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, CardArt, Chip, Empty, Note, Panel, T } from '../src/ui';
import { Screen } from '../src/screen';
import { ChipRow } from '../src/screen';
import { saveFile, toCSV } from '../src/csv';
import { toast } from '../src/toast';

const soldDay = o => o.soldAt || o.updated || o.added || '';
const fyOf = day => { const y = Number(day.slice(0, 4)), m = Number(day.slice(5, 7)); return m >= 7 ? y + 1 : y; };   // FY2027 = Jul 2026 – Jun 2027

export default function Sales() {
  useTrack('sales');
  const d = useData(), c = useTheme();
  const [mode, setMode] = useState('fy');
  const sold = d.owned.filter(o => o.status === 'sold');
  const yearOf = o => { const day = soldDay(o); return day ? (mode === 'fy' ? fyOf(day) : Number(day.slice(0, 4))) : null; };
  const years = [...new Set(sold.map(yearOf).filter(Boolean))].sort((a, b) => b - a);
  const now = mode === 'fy' ? fyOf(new Date().toISOString().slice(0, 10)) : new Date().getFullYear();
  const [year, setYear] = useState(null);
  const y = year ?? years[0] ?? now;
  const label = v => (mode === 'fy' ? `FY ${v - 1}–${String(v).slice(2)}` : String(v));
  const rows = useMemo(() => sold.filter(o => yearOf(o) === y).sort((a, b) => soldDay(b).localeCompare(soldDay(a))), [d.owned, y, mode]);
  const t = rows.reduce((a, o) => {
    const q = Number(o.qty) || 1, got = (Number(o.soldFor) || 0) * q, paid = o.paid != null && o.paid !== '' ? Number(o.paid) * q : null;
    a.got += got; if (paid != null) { a.paid += paid; a.profit += got - paid; } else a.unknown++;
    return a;
  }, { got: 0, paid: 0, profit: 0, unknown: 0 });

  const exportIt = async () => {
    const head = ['Date sold', 'Name', 'Number', 'Quantity', 'Sold for each (A$)', 'Total received (A$)', 'Paid each (A$)', 'Total paid (A$)', 'Profit (A$)', 'Group', 'Notes'];
    const body = rows.map(o => { const q = Number(o.qty) || 1, s = Number(o.soldFor) || 0, p = o.paid != null && o.paid !== '' ? Number(o.paid) : null;
      return [soldDay(o), clean(o.name), d.card(o.card)?.num || o.num || '', q, s.toFixed(2), (s * q).toFixed(2), p == null ? '' : p.toFixed(2), p == null ? '' : (p * q).toFixed(2), p == null ? '' : ((s - p) * q).toFixed(2), o.group || '', o.notes || '']; });
    body.push([], ['Total', '', '', '', '', t.got.toFixed(2), '', t.paid.toFixed(2), t.profit.toFixed(2)]);
    if (await saveFile(`sales-${label(y).replace(/\s+/g, '')}.csv`, toCSV([head, ...body]))) toast('Sales exported');
  };

  if (!d.session) return <Screen><Empty>Sign in to see your sales.</Empty></Screen>;
  return (
    <Screen max={900}>
      <ChipRow>
        <Chip on={mode === 'fy'} onPress={() => { setMode('fy'); setYear(null); }}>Financial year</Chip>
        <Chip on={mode === 'cal'} onPress={() => { setMode('cal'); setYear(null); }}>Calendar year</Chip>
      </ChipRow>
      <ChipRow style={{ marginTop: 10 }}>
        {(years.length ? years : [now]).map(v => <Chip key={v} on={v === y} onPress={() => setYear(v)}>{label(v)}</Chip>)}
      </ChipRow>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 14 }}>
        <Box label="Received" value={d.aud(t.got)} />
        <Box label="Paid for those" value={d.aud(t.paid)} />
        <Box label="Profit" value={(t.profit >= 0 ? '+' : '-') + d.aud(Math.abs(t.profit))} tone={t.profit >= 0 ? c.up : c.down} />
      </View>
      {t.unknown ? <Note style={{ marginTop: 12 }} title={`${t.unknown} sold ${t.unknown === 1 ? 'item has' : 'items have'} no price paid`}>They count as received but not in the profit. Open them below to add what you paid.</Note> : null}
      {!cols.soldAt && sold.length ? <Note style={{ marginTop: 12 }}>Sale dates are estimated from when each item was last changed. Run the 24 Nov database update so new sales keep their exact date.</Note> : null}
      <Panel style={{ marginTop: 14, gap: 2 }}>
        {!rows.length ? <Empty>Nothing sold in {label(y)}.</Empty> : rows.map(o => {
          const q = Number(o.qty) || 1, got = (Number(o.soldFor) || 0) * q, paid = o.paid != null && o.paid !== '' ? Number(o.paid) * q : null;
          return (
            <View key={o.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8 }}>
              <CardArt k={o.card} photo={d.ownPhoto(o)} num={d.card(o.card)?.num || o.num} width={32} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <T w="semi" size={14} numberOfLines={1} onPress={() => router.push({ pathname: '/item/[id]', params: { id: o.id } })}>{clean(o.name)}{q > 1 ? ` ×${q}` : ''}</T>
                <T mute size={12}>{soldDay(o)}{paid != null ? ` · paid ${d.aud(paid)}` : ' · price paid unknown'}</T>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <T w="bold" size={14}>{d.aud(got)}</T>
                {paid != null ? <T size={12} w="semi" style={{ color: got - paid >= 0 ? c.up : c.down }}>{got - paid >= 0 ? '▲ +' : '▼ -'}{d.aud(Math.abs(got - paid))}</T> : null}
              </View>
            </View>
          );
        })}
      </Panel>
      {rows.length ? <Button ghost icon="download-outline" onPress={exportIt} style={{ marginTop: 14 }}>Export {label(y)} as CSV</Button> : null}
      <T mute size={11.5} style={{ marginTop: 14 }}>A summary of what you logged, not tax advice. Whether card sales count as a hobby or a business for tax depends on your situation; an accountant can tell you.</T>
    </Screen>
  );
}

function Box({ label, value, tone }) {
  const c = useTheme();
  return (
    <View style={{ flexGrow: 1, flexBasis: 130, borderRadius: 16, padding: 14, backgroundColor: c.panel }}>
      <T size={12.5} mute>{label}</T>
      <T w="bold" size={19} style={[{ marginTop: 3 }, tone ? { color: tone } : null]}>{value}</T>
    </View>
  );
}
