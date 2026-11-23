// Worth grading? Compares keeping the card raw with sending it to PSA: chance of each grade × its price,
// minus grading and postage. Defaults are editable (PSA through an Australian group submission is
// roughly A$80+ a card in Nov 2026, more for valuable cards).
import React, { useState } from 'react';
import { View } from 'react-native';
import { median, useData } from './data';
import { useTheme } from './theme';
import { Field, Panel, T } from './ui';
import { usePref } from './prefs';

const n = v => { const x = parseFloat(String(v ?? '').replace(',', '.')); return isNaN(x) ? null : x; };
const fmt = a => (a < 0 ? '-' : '') + 'A$' + Math.abs(a).toLocaleString('en-AU', { maximumFractionDigits: Math.abs(a) >= 100 ? 0 : 2 });

export function GradeCalc({ card, raw }) {
  const d = useData(), c = useTheme();
  const graded = g => { const l = d.salesOf(card.k).filter(s => s.grade === g).map(s => d.toUsd(s.price, s.cur) * d.fx); return l.length ? median(l) : null; };
  const [p10, setP10] = useState(graded('PSA 10') != null ? graded('PSA 10').toFixed(0) : '');
  const [p9, setP9] = useState(graded('PSA 9') != null ? graded('PSA 9').toFixed(0) : '');
  const [c10, setC10] = usePref('gradeChance10', '40');
  const [c9, setC9] = usePref('gradeChance9', '40');
  const [fee, setFee] = usePref('gradeFee', '80');
  const [post, setPost] = usePref('gradePost', '25');
  if (raw == null || card.t !== 'card') return null;
  const P10 = n(p10), P9 = n(p9), a10 = Math.min(100, n(c10) || 0) / 100, a9 = Math.min(1 - a10, (n(c9) || 0) / 100), rest = Math.max(0, 1 - a10 - a9);
  const cost = (n(fee) || 0) + (n(post) || 0);
  const ready = P10 != null;
  const ev = ready ? a10 * P10 + a9 * (P9 ?? raw) + rest * raw - cost : null;
  const gain = ev == null ? null : ev - raw;
  const even = a10 > 0 ? (raw + cost - a9 * (P9 ?? raw) - rest * raw) / a10 : null;
  return (
    <Panel title="Worth grading?">
      <T mute size={13}>Raw it’s worth about {fmt(raw)}. Put in what PSA 10 and 9 copies sell for (eBay sold, graded only) and your odds.</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <Field label="PSA 10 sells for (A$)" value={p10} onChangeText={setP10} keyboardType="decimal-pad" placeholder={String(Math.round(raw * 3))} />
        <Field label="PSA 9 sells for (A$)" value={p9} onChangeText={setP9} keyboardType="decimal-pad" placeholder={String(Math.round(raw * 1.2))} />
        <Field label="Chance of a 10 (%)" value={String(c10)} onChangeText={setC10} keyboardType="decimal-pad" />
        <Field label="Chance of a 9 (%)" value={String(c9)} onChangeText={setC9} keyboardType="decimal-pad" />
        <Field label="Grading fee (A$)" value={String(fee)} onChangeText={setFee} keyboardType="decimal-pad" />
        <Field label="Postage + insurance (A$)" value={String(post)} onChangeText={setPost} keyboardType="decimal-pad" />
      </View>
      {ready ? <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flexGrow: 1, flexBasis: 140, borderRadius: 14, padding: 12, backgroundColor: gain > 0 ? c.accentDim : 'rgba(255,91,91,0.14)' }}>
          <T size={12} mute>On average, after costs</T>
          <T w="bold" size={19} style={{ color: gain > 0 ? c.up : c.down }}>{gain > 0 ? `+${fmt(gain)} grading` : `${fmt(gain)}: keep it raw`}</T>
        </View>
        {even != null ? <View style={{ flexGrow: 1, flexBasis: 140, borderRadius: 14, padding: 12, backgroundColor: c.soft }}>
          <T size={12} mute>Breaks even if a PSA 10 sells for</T>
          <T w="bold" size={19}>{fmt(even)}</T>
        </View> : null}
      </View> : <T mute size={12.5}>Add a PSA 10 price to see the answer.</T>}
      <T mute size={11.5}>Grades below 9 are counted at the raw price. Grading takes months, and PSA can charge more if the graded card is worth more than the tier you picked.</T>
    </Panel>
  );
}
