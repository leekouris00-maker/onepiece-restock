// Binders (26 Nov 2026): page-by-page views of cards, like a real 9-pocket binder.
// Saved to your account (supabase/2026-11-26-binders.sql); until that's run, kept on this device.
// A binder's cards come from:  a collection group  |  a whole set (missing cards shown faded)  |  cards you pick.
import { useCallback, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { supabase, useData, newId } from './data';

export const COLORS = [['lime', '#c6f432'], ['red', '#ff5b5b'], ['blue', '#4da3ff'], ['gold', '#e6b450'], ['purple', '#a78bfa'], ['teal', '#2dd4bf'], ['black', '#3a403c']];
export const colorOf = name => (COLORS.find(([n]) => n === name) || COLORS[0])[1];
export const GRIDS = { '2x2': [2, 2], '3x3': [3, 3], '4x3': [4, 3] };   // [columns, rows]

const fromRow = r => ({ id: r.id, name: r.name, color: r.color, grid: r.grid, source: r.source || { kind: 'pick' }, sort: r.sort, slots: r.slots || [], showPrices: r.show_prices !== false, position: r.position || 0 });
const toRow = b => ({ id: b.id, name: b.name, color: b.color, grid: b.grid, source: b.source, sort: b.sort, slots: b.slots, show_prices: b.showPrices, position: b.position || 0, updated_at: new Date().toISOString() });
const missingTable = e => e && (e.code === '42P01' || e.code === 'PGRST205' || /could not find the table|does not exist/i.test(e.message || ''));

// shared between screens
let cache = { uid: null, list: [], local: false, ready: false };
const subs = new Set();
const publish = next => { cache = { ...cache, ...next }; subs.forEach(f => f(cache)); };
const localKey = uid => 'binders:' + (uid || 'guest');
async function load(uid) {
  publish({ uid, ready: cache.uid === uid && cache.ready });
  if (supabase && uid) {
    const r = await supabase.from('binders').select('*').order('position').order('created_at');
    if (!r.error) { publish({ list: r.data.map(fromRow), local: false, ready: true }); return; }
    if (!missingTable(r.error)) { publish({ ready: true, error: r.error.message }); return; }
  }
  const raw = await AsyncStorage.getItem(localKey(uid));
  publish({ list: raw ? JSON.parse(raw) : [], local: true, ready: true });
}
async function persist(list) {
  publish({ list });
  if (cache.local) await AsyncStorage.setItem(localKey(cache.uid), JSON.stringify(list));
}

export function useBinders() {
  const d = useData();
  const uid = d.session?.user?.id || null;
  const [c, setC] = useState(cache);
  useEffect(() => { subs.add(setC); setC(cache); return () => { subs.delete(setC); }; }, []);
  useEffect(() => { if (cache.uid !== uid || !cache.ready) load(uid); }, [uid]);
  const save = useCallback(async b => {
    const list = cache.list.some(x => x.id === b.id) ? cache.list.map(x => (x.id === b.id ? b : x)) : [...cache.list, b];
    await persist(list);
    if (!cache.local) { const r = await supabase.from('binders').upsert(toRow(b)); if (r.error) throw new Error(r.error.message); }
    return b;
  }, []);
  // Merge a change into the latest copy, so quick taps never undo each other
  const update = useCallback(async (id, patch) => {
    const cur = cache.list.find(x => x.id === id);
    if (!cur) return null;
    return save({ ...cur, ...(typeof patch === 'function' ? patch(cur) : patch) });
  }, [save]);
  const remove = useCallback(async id => {
    const gone = cache.list.find(x => x.id === id);
    await persist(cache.list.filter(x => x.id !== id));
    if (!cache.local) { const r = await supabase.from('binders').delete().eq('id', id); if (r.error) throw new Error(r.error.message); }
    return gone;
  }, []);
  // Put one binder first in the list
  const moveTop = useCallback(async id => {
    const me = cache.list.find(x => x.id === id);
    if (!me) return;
    const list = [me, ...cache.list.filter(x => x.id !== id)].map((x, i) => ({ ...x, position: i }));
    await persist(list);
    if (!cache.local) { const r = await supabase.from('binders').upsert(list.map(toRow)); if (r.error) throw new Error(r.error.message); }
  }, []);
  const create = useCallback(async (init = {}) => save({ id: newId(), name: 'My binder', color: 'lime', grid: '3x3', source: { kind: 'pick' }, sort: 'number', slots: [], showPrices: true, position: cache.list.length, ...init }), [save]);
  return { binders: c.list, ready: c.ready, local: c.local, error: c.error, save, update, remove, create, moveTop, reload: () => load(uid) };
}

const numCmp = (a, b) => String(a || '').localeCompare(String(b || ''), undefined, { numeric: true });

// What's in the binder, in order. Each pocket: { key, own (owned row) | card (catalogue card, missing), have } or null (empty)
// Cards taken out of a group or set binder are remembered in its slots as "x:<key>"
export const hiddenOf = b => (b?.slots || []).filter(k => typeof k === 'string' && k.startsWith('x:'));
const isHidden = k => typeof k === 'string' && k.startsWith('x:');

// Slots after taking one card out: a picked binder just closes the gap; a group or set binder remembers it
export function slotsWithout(b, key) {
  const slots = (b.slots || []).filter(k => k !== key && k !== 'x:' + key);
  return (b.source?.kind || 'pick') === 'pick' ? slots : [...slots, 'x:' + key];
}

export function binderPockets(d, b) {
  const hidden = new Set(hiddenOf(b).map(k => k.slice(2)));
  const live = (d.owned || []).filter(o => o.status !== 'sold');
  const ownEntry = o => { const card = o.card ? d.card(o.card) : null; return { key: 'o:' + o.id, own: o, card, num: o.num || card?.num || '', price: d.unitAt(o, 0), added: o.added || '', have: true }; };
  let list = [];
  const src = b.source || { kind: 'pick' };
  if (src.kind === 'group') list = live.filter(o => (o.group || 'Other') === src.group).map(ownEntry);
  else if (src.kind === 'set') {
    const cards = (d.cat?.list || []).filter(x => x.g === src.set && x.t === 'card');
    const mine = new Map();
    for (const o of live) if (o.card) mine.set(o.card, o);
    if (src.master) list = cards.map(x => (mine.has(x.k) ? ownEntry(mine.get(x.k)) : { key: 'k:' + x.k, card: x, num: x.num, price: d.aud ? (x.m || 0) * (d.cat?.meta?.fx || 1.5) : 0, have: false }));
    else {
      // one pocket per card number from the set itself (owned version if you have one, else the cheapest)
      const code = d.cat?.byId[src.set]?.code || '';
      const pre = code.split(/[-\s]/).filter(p => /^[A-Z]+\d+$/.test(p)).map(p => p + '-');
      const own = pre.length ? cards.filter(x => pre.some(p => x.num.startsWith(p))) : cards;
      const byNum = new Map();
      for (const x of own.length ? own : cards) (byNum.get(x.num) || byNum.set(x.num, []).get(x.num)).push(x);
      for (const [num, vs] of byNum) {
        const got = vs.find(x => mine.has(x.k));
        if (got) list.push(ownEntry(mine.get(got.k)));
        else { const x = vs.filter(v => v.m != null).sort((p, q) => p.m - q.m)[0] || vs[0]; list.push({ key: 'k:' + x.k, card: x, num, price: (x.m || 0) * (d.cat?.meta?.fx || 1.5), have: false }); }
      }
    }
  }
  list = list.filter(e => !hidden.has(e.key));
  if (src.kind === 'pick' || b.sort === 'custom') {
    // custom order: the saved slots first (null = empty pocket), then anything new at the end
    const byKey = new Map(list.map(e => [e.key, e]));
    const out = [];
    for (const k of b.slots || []) {
      if (k == null) { out.push(null); continue; }
      if (isHidden(k) || hidden.has(k)) continue;
      let e = byKey.get(k);
      if (!e && k.startsWith('o:')) { const o = live.find(x => 'o:' + x.id === k); if (o) e = ownEntry(o); }
      if (e) { out.push(e); byKey.delete(k); }
    }
    if (src.kind !== 'pick') for (const e of byKey.values()) out.push(e);
    while (out.length && out[out.length - 1] == null) out.pop();
    return out;
  }
  const by = { number: (p, q) => numCmp(p.num, q.num), price: (p, q) => (q.price || 0) - (p.price || 0), added: (p, q) => String(q.added).localeCompare(String(p.added)) }[b.sort] || ((p, q) => numCmp(p.num, q.num));
  return list.sort(by);
}

export function binderStats(pockets) {
  const filled = pockets.filter(Boolean);
  const have = filled.filter(p => p.have);
  const value = have.reduce((s, p) => s + (p.price || 0) * (Number(p.own?.qty) || 1), 0);
  const missingCost = filled.filter(p => !p.have).reduce((s, p) => s + (p.price || 0), 0);
  return { total: filled.length, have: have.length, value, missingCost };
}
