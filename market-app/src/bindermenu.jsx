// Binder quick actions (26 Nov 2026): one menu for a binder, the same everywhere —
// long-press a binder cover or tap its ⋯, or the ⋯ inside a binder. Delete is instant with Undo, no "are you sure".
import React from 'react';
import { router } from 'expo-router';
import { Sheet, MenuItem } from './ui';
import { toast } from './toast';
import { haptic } from './haptic';
import { useBinders } from './binders';

export function useBinderActions() {
  const bs = useBinders();
  const fail = e => toast(e?.message || String(e));
  return {
    async del(b, after) {
      try {
        const gone = await bs.remove(b.id); haptic('warn'); after?.();
        toast(`Deleted “${b.name}”. Your cards are untouched.`, { action: { label: 'Undo', onPress: () => bs.save(gone).catch(fail) } });
      } catch (e) { fail(e); }
    },
    async dup(b) {
      try {
        const { id, position, ...rest } = b;
        const x = await bs.create({ ...rest, name: `${b.name} copy` }); haptic();
        toast(`Made “${x.name}”`, { action: { label: 'Open', onPress: () => router.push({ pathname: '/binder/[id]', params: { id: x.id } }) } });
      } catch (e) { fail(e); }
    },
    async top(b) {
      try { await bs.moveTop(b.id); haptic(); toast(`“${b.name}” is now first`); } catch (e) { fail(e); }
    },
  };
}

// inside: shown from within the binder (hides "Open", adds Arrange)
export function BinderMenu({ b, onClose, inside, onCustomise, onArrange, onAdd }) {
  const a = useBinderActions();
  if (!b) return null;
  const go = f => () => { onClose(); f(); };
  const kind = b.source?.kind || 'pick';
  return (
    <Sheet open onClose={onClose} title={b.name}>
      {!inside ? <MenuItem icon="book-outline" label="Open" onPress={go(() => router.push({ pathname: '/binder/[id]', params: { id: b.id } }))} /> : null}
      {inside && onAdd && kind !== 'set' ? <MenuItem icon="add-circle-outline" label="Add cards" onPress={go(onAdd)} /> : null}
      {inside && onArrange && kind !== 'set' ? <MenuItem icon="swap-horizontal" label="Arrange or remove cards" sub="Tap the − on a card to take it out" onPress={go(onArrange)} /> : null}
      <MenuItem icon="options-outline" label="Customise" sub="Name, colour, page size, where cards come from" onPress={go(() => (onCustomise ? onCustomise() : router.push({ pathname: '/binder/[id]', params: { id: b.id, edit: '1' } })))} />
      <MenuItem icon="copy-outline" label="Duplicate" onPress={go(() => a.dup(b))} />
      {!inside ? <MenuItem icon="arrow-up-circle-outline" label="Move to top" onPress={go(() => a.top(b))} /> : null}
      <MenuItem icon="trash-outline" label="Delete binder" sub="Your collection isn’t changed" danger onPress={go(() => a.del(b, inside ? () => router.back() : null))} />
    </Sheet>
  );
}
