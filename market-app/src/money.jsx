// Selling and buying helpers: what you'd take home after eBay fees and postage, and what to offer when buying.
import React, { useState } from 'react';
import { View } from 'react-native';
import { useTheme } from './theme';
import { Choice, Field, Panel, T } from './ui';
import { usePref } from './prefs';

// eBay Australia (checked Nov 2026): private sellers with up to A$25,000 of sales a year pay no selling fees;
// otherwise the Pro Starter plan charges 13.4% of the total the buyer pays (item + postage) plus A$0.30 an order.
export const FEES = {
  free: { label: 'eBay, free selling', note: 'Private sellers under A$25k of sales a year', pct: 0, fixed: 0 },
  pro: { label: 'eBay Pro Starter', note: '13.4% of item + postage, plus A$0.30', pct: 13.4, fixed: 0.3 },
  custom: { label: 'Other', note: 'Your own fee', pct: null, fixed: 0 },
};

const n = v => { const x = parseFloat(String(v ?? '').replace(',', '.')); return isNaN(x) ? 0 : x; };
const fmt = a => (a < 0 ? '-' : '') + 'A$' + Math.abs(a).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

// value: A$ each to start from; paid: A$ each you paid (optional); qty: copies
export function SellCalc({ value, paid, qty = 1, title = 'If you sold it' }) {
  const c = useTheme();
  const [plan, setPlan] = usePref('sellPlan', 'free');
  const [custom, setCustom] = usePref('sellPct', '10');
  const [postCharge, setPostCharge] = usePref('sellPostCharge', '');
  const [postCost, setPostCost] = usePref('sellPostCost', '');
  const [price, setPrice] = useState(value != null ? value.toFixed(2) : '');
  const f = FEES[plan] || FEES.free, pct = plan === 'custom' ? n(custom) : f.pct;
  const each = n(price), q = Math.max(1, Number(qty) || 1);
  const gross = each * q + n(postCharge);
  const fee = (gross * pct) / 100 + (gross > 0 ? f.fixed : 0);
  const take = gross - fee - n(postCost);
  const profit = paid != null && paid !== '' ? take - n(paid) * q : null;
  return (
    <Panel title={title}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <Field label={q > 1 ? `Sell price each (A$) × ${q}` : 'Sell price (A$)'} value={price} onChangeText={setPrice} keyboardType="decimal-pad" />
        <Field label="Buyer pays postage (A$)" value={String(postCharge)} onChangeText={setPostCharge} keyboardType="decimal-pad" placeholder="0" />
        <Field label="Postage costs you (A$)" value={String(postCost)} onChangeText={setPostCost} keyboardType="decimal-pad" placeholder="0" />
        <Choice label="Selling on" value={plan} onChange={setPlan} options={Object.entries(FEES).map(([k, v]) => [k, v.label])} />
        {plan === 'custom' ? <Field label="Fee %" value={String(custom)} onChangeText={setCustom} keyboardType="decimal-pad" /> : null}
      </View>
      <T mute size={12}>{f.note}{plan !== 'custom' ? ' · eBay AU fees as of Nov 2026' : ''}</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <Box label="Fees" value={fmt(-fee)} />
        <Box label="You take home" value={fmt(take)} strong />
        {profit != null ? <Box label="Profit on what you paid" value={(profit >= 0 ? '+' : '') + fmt(profit)} tone={profit >= 0 ? c.up : c.down} /> : null}
      </View>
    </Panel>
  );
}

function Box({ label, value, strong, tone }) {
  const c = useTheme();
  return (
    <View style={{ flexGrow: 1, flexBasis: 110, borderRadius: 14, padding: 12, backgroundColor: c.soft }}>
      <T size={12} mute>{label}</T>
      <T w="bold" size={strong ? 20 : 16} style={[{ marginTop: 2 }, tone ? { color: tone } : strong ? { color: c.accent } : null]}>{value}</T>
    </View>
  );
}

// Buying: 70 / 80 / 90% of the card's value
export function OfferPrices({ a, src }) {
  const c = useTheme();
  if (a == null) return null;
  return (
    <Panel title="Buying? What to offer">
      <View style={{ flexDirection: 'row', gap: 10 }}>
        {[70, 80, 90].map(p => (
          <View key={p} style={{ flex: 1, borderRadius: 14, padding: 12, backgroundColor: p === 80 ? c.accentDim : c.soft, alignItems: 'center' }}>
            <T mute size={12}>{p}%</T>
            <T w="bold" size={17} style={p === 80 ? { color: c.accent } : null}>{fmt((a * p) / 100)}</T>
          </View>
        ))}
      </View>
      <T mute size={12}>Of {fmt(a)}, the {src}. Shops usually pay 60–80%; collectors 80–90%.</T>
    </Panel>
  );
}
