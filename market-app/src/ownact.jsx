// Quick changes to collection entries, each with Undo: +1 / −1 / mark sold / move / price paid / remove.
import React, { useState } from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { clean, useData } from './data';
import { Button, Chip, Field, MenuItem, Sheet, T } from './ui';
import { toast } from './toast';
import { haptic } from './haptic';

const nm = o => clean(o.name);
const fail = e => toast(e.message || String(e));

export function useOwnedActions() {
  const d = useData();
  const undo = (text, restore) => toast(text, { action: { label: 'Undo', onPress: () => restore().catch(fail) } });
  const a = {
    async plus(o) {
      try { const q = (Number(o.qty) || 1) + 1; await d.saveOwned({ ...o, qty: q }); haptic(); undo(`${nm(o)} ×${q}`, () => d.saveOwned(o)); } catch (e) { fail(e); }
    },
    async minus(o) {
      try {
        const q = Number(o.qty) || 1;
        if (q > 1) { await d.saveOwned({ ...o, qty: q - 1 }); haptic(); undo(`${nm(o)} ×${q - 1}`, () => d.saveOwned(o)); }
        else await a.remove(o);
      } catch (e) { fail(e); }
    },
    async sold(o) {
      try {
        const each = d.unitAt(o, 0);
        await d.saveOwned({ ...o, status: 'sold', soldFor: each == null ? null : Math.round(each * 100) / 100 });
        haptic('success');
        undo(`Marked sold${each != null ? ` at ${d.aud(each * (Number(o.qty) || 1))}` : ''}. Edit the price in the item.`, () => d.saveOwned(o));
      } catch (e) { fail(e); }
    },
    async remove(o) {
      try { await d.removeOwned(o.id); haptic('warn'); undo(`Removed ${nm(o)}`, () => d.saveOwned(o)); } catch (e) { fail(e); }
    },
    // several at once
    async many(list, change, text) {
      try {
        const before = list.map(o => ({ ...o }));
        await d.saveMany(list.map(o => ({ ...o, ...change(o) })));
        haptic('success'); undo(text, () => d.saveMany(before));
      } catch (e) { fail(e); }
    },
    async removeMany(list) {
      try {
        const before = list.map(o => ({ ...o }));
        await d.removeMany(list.map(o => o.id));
        haptic('warn'); undo(`Removed ${list.length} ${list.length === 1 ? 'entry' : 'entries'}`, () => d.saveMany(before));
      } catch (e) { fail(e); }
    },
  };
  return a;
}

// Long-press menu for one entry
export function ItemMenu({ o, onClose, onSelect }) {
  const a = useOwnedActions();
  const [step, setStep] = useState('menu');
  if (!o) return null;
  const q = Number(o.qty) || 1, sold = o.status === 'sold';
  const go = f => () => { onClose(); f(o); };
  return (
    <Sheet open onClose={onClose} title={step === 'menu' ? nm(o) : 'Move to group'}>
      {step === 'menu' ? <>
        <MenuItem icon="add-circle-outline" label="Add one" sub={`Now ×${q}`} onPress={go(a.plus)} />
        <MenuItem icon="remove-circle-outline" label={q > 1 ? 'Remove one' : 'Remove from collection'} onPress={go(a.minus)} danger={q === 1} />
        {!sold ? <MenuItem icon="cash-outline" label="Mark sold" sub="At today’s value. You can change it after." onPress={go(a.sold)} /> : null}
        <MenuItem icon="folder-open-outline" label="Move to group" sub={o.group || 'Other'} onPress={() => setStep('move')} />
        <MenuItem icon="create-outline" label="Edit" onPress={() => { onClose(); router.push({ pathname: '/item/[id]', params: { id: o.id } }); }} />
        {o.card ? <MenuItem icon="pricetags-outline" label="Card prices" onPress={() => { onClose(); router.push({ pathname: '/card/[k]', params: { k: o.card } }); }} /> : null}
        {onSelect ? <MenuItem icon="checkmark-circle-outline" label="Select several" onPress={() => { onClose(); onSelect(o); }} /> : null}
        {q > 1 ? <MenuItem icon="trash-outline" label="Remove all" danger onPress={go(a.remove)} /> : null}
      </> : <MoveTo list={[o]} onDone={onClose} />}
    </Sheet>
  );
}

// Pick a group (or type a new one) for one or more entries
export function MoveTo({ list, onDone }) {
  const d = useData(), a = useOwnedActions();
  const groups = [...new Set(d.owned.map(o => o.group || 'Other'))].sort();
  const [g, setG] = useState('');
  const move = to => { onDone(); a.many(list, () => ({ group: to }), `Moved ${list.length === 1 ? nm(list[0]) : list.length + ' entries'} to ${to}`); };
  return (
    <View style={{ gap: 12 }}>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{groups.map(x => <Chip key={x} onPress={() => move(x)}>{x}</Chip>)}</View>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
        <Field label="Or a new group" value={g} onChangeText={setG} placeholder="Trade binder" onSubmitEditing={() => g.trim() && move(g.trim())} />
        <Button disabled={!g.trim()} onPress={() => move(g.trim())}>Move</Button>
      </View>
    </View>
  );
}

// Set the price paid for several entries
export function SetPaid({ list, onDone }) {
  const a = useOwnedActions();
  const [v, setV] = useState('');
  const n = parseFloat(String(v).replace(',', '.'));
  return (
    <View style={{ gap: 12 }}>
      <T mute size={13.5}>Price paid for each copy, in A$. Applies to all {list.length} selected.</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, alignItems: 'flex-end' }}>
        <Field label="Paid each (A$)" value={v} onChangeText={setV} keyboardType="decimal-pad" autoFocus />
        <Button disabled={!(n >= 0)} onPress={() => { onDone(); a.many(list, () => ({ paid: n }), `Set paid A$${n} each on ${list.length} ${list.length === 1 ? 'entry' : 'entries'}`); }}>Set</Button>
      </View>
    </View>
  );
}
