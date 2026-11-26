// One binder (26 Nov 2026): swipe through pages of pockets. Arrange mode: tap a card, then tap another pocket to swap.
// Customise: name, cover colour, page layout (2x2 / 3x3 / 4x3), where cards come from, order, prices on/off.
import React, { useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { clean, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, CardArt, Choice, Field, Panel, SearchBar, Select, Sheet, T } from '../../src/ui';
import { IconBtn, Screen } from '../../src/screen';
import { useWide } from '../../src/layout';
import { useKeys } from '../../src/keys';
import { toast } from '../../src/toast';
import { startedSets } from '../../src/sets';
import { COLORS, GRIDS, binderPockets, binderStats, colorOf, useBinders } from '../../src/binders';

export default function BinderScreen() {
  const { id, edit } = useLocalSearchParams();
  const d = useData(), c = useTheme(), wide = useWide(), { width, height } = useWindowDimensions();
  const bs = useBinders();
  const b = bs.binders.find(x => x.id === id);
  const [arrange, setArrange] = useState(false);
  const [sel, setSel] = useState(null);           // pocket index picked up in arrange mode
  const [custom, setCustom] = useState(edit === '1');
  const [adding, setAdding] = useState(false);
  const [page, setPage] = useState(0);
  const scroller = useRef(null);

  const pockets = useMemo(() => (b ? binderPockets(d, b) : []), [b, d.owned, d.cat]);
  const st = binderStats(pockets);
  const [cols, rows] = GRIDS[b?.grid] || GRIDS['3x3'];
  const per = cols * rows;
  const gap = 8, inner = 12;
  // On a big screen, keep a whole page in view: size pockets by the window's height too
  const fitPocket = Math.floor(((height - 230) / rows - gap - 22) / 1.4);
  const fitW = cols * fitPocket + gap * (cols - 1) + inner * 2 + 6;
  const pageW = Math.min(Math.min(width, 900) - (wide ? 64 : 36), wide ? Math.max(fitW, 420) : 9999);
  const pocketW = Math.floor((pageW - inner * 2 - 6 - gap * (cols - 1)) / cols);   // 6 = the page's borders
  const showPrices = b?.showPrices !== false;
  const kind = b?.source?.kind || 'pick';
  const canArrange = kind !== 'set';
  const pageCount = Math.max(1, Math.ceil((pockets.length + (arrange ? 1 : 0)) / per));
  const goPage = p => { const q = Math.max(0, Math.min(pageCount - 1, p)); setPage(q); scroller.current?.scrollTo({ x: q * pageW, animated: true }); };
  useKeys([
    { keys: ['arrowright'], label: 'Next page', run: () => goPage(page + 1) },
    { keys: ['arrowleft'], label: 'Previous page', run: () => goPage(page - 1) },
    { keys: ['e'], label: 'Arrange on / off', when: () => canArrange, run: () => { setArrange(a => !a); setSel(null); } },
  ]);

  if (!b) return <Screen><T mute>{bs.ready ? 'This binder isn’t here any more.' : 'Loading…'}</T></Screen>;

  const save = async next => { try { await bs.save(next); } catch (e) { toast(e.message || String(e)); } };
  const update = async patch => { try { await bs.update(b.id, patch); } catch (e) { toast(e.message || String(e)); } };
  const keysNow = () => pockets.map(p => (p ? p.key : null));
  const tapPocket = i => {
    const p = pockets[i];
    if (!arrange) {
      if (!p) return;
      if (p.own) router.push({ pathname: '/item/[id]', params: { id: p.own.id } });
      else if (p.card) router.push({ pathname: '/card/[k]', params: { k: p.card.k } });
      return;
    }
    if (sel == null) { if (p) setSel(i); return; }
    if (sel === i) { setSel(null); return; }
    const arr = keysNow();
    while (arr.length <= Math.max(i, sel)) arr.push(null);
    [arr[i], arr[sel]] = [arr[sel], arr[i]];
    setSel(null);
    save({ ...b, slots: arr, sort: kind === 'pick' ? b.sort : 'custom' });
  };
  const removeSel = () => {
    const arr = keysNow(); const gone = arr[sel]; arr[sel] = null; setSel(null);
    save({ ...b, slots: arr, sort: kind === 'pick' ? b.sort : 'custom' });
    toast('Taken out of the binder (still in your collection)', { action: { label: 'Undo', onPress: () => { const a2 = keysNow(); a2[sel] = gone; save({ ...b, slots: a2 }); } } });
  };
  const addOwned = o => {
    const k = 'o:' + o.id, base = keysNow();
    update(cur => {
      const from = kind === 'pick' ? (cur.slots || []) : base;
      return from.includes(k) ? {} : { slots: [...from, k], sort: kind === 'pick' ? cur.sort : 'custom' };
    });
    toast(`Added ${clean(o.name)}`);
  };

  const col = colorOf(b.color);
  const pages = Array.from({ length: pageCount }, (_, p) => Array.from({ length: per }, (__, j) => p * per + j));

  return (
    <Screen max={900}>
      {/* header */}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, zIndex: 5 }}>
        <View style={{ width: 8, alignSelf: 'stretch', borderRadius: 4, backgroundColor: col }} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <T w="bold" size={24} numberOfLines={1}>{b.name}</T>
          <T mute size={13}>{kind === 'set' ? `${st.have} of ${st.total} · ${d.aud(st.value)}${st.missingCost ? ` · ${d.aud(st.missingCost)} to finish` : ''}` : `${st.total} ${st.total === 1 ? 'card' : 'cards'} · ${d.aud(st.value)}`}</T>
        </View>
        {kind === 'pick' || b.sort === 'custom' || kind === 'group' ? <IconBtn icon="add" label="Add cards" onPress={() => setAdding(true)} /> : null}
        {canArrange ? <IconBtn icon="swap-horizontal" label={arrange ? 'Done arranging' : 'Arrange'} keys="e" on={arrange} onPress={() => { setArrange(a => !a); setSel(null); }} /> : null}
        <IconBtn icon="options-outline" label="Customise" onPress={() => setCustom(true)} />
      </View>
      {arrange ? <T size={13} style={{ color: c.accent, marginTop: 10 }}>{sel == null ? 'Tap a card, then tap where it should go.' : 'Now tap another pocket to swap.'}</T> : null}
      {arrange && sel != null && pockets[sel] && (kind === 'pick' || b.sort === 'custom' || kind === 'group') ? <View style={{ flexDirection: 'row', gap: 10, marginTop: 8 }}>
        <Button ghost icon="remove-circle-outline" onPress={removeSel}>Take out of binder</Button>
      </View> : null}

      {/* pages */}
      <ScrollView ref={scroller} horizontal pagingEnabled showsHorizontalScrollIndicator={false} style={{ marginTop: 14, width: pageW, alignSelf: 'center' }}
        onMomentumScrollEnd={e => setPage(Math.round(e.nativeEvent.contentOffset.x / pageW))}
        onScroll={e => { const p = Math.round(e.nativeEvent.contentOffset.x / pageW); if (p !== page) setPage(p); }} scrollEventThrottle={64}>
        {pages.map((idxs, p) => (
          <View key={p} style={{ width: pageW, padding: inner, borderRadius: 18, backgroundColor: c.panel, borderWidth: 1, borderColor: c.line, borderLeftWidth: 4, borderLeftColor: col }}>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap }}>
              {idxs.map(i => {
                const pk = pockets[i];
                const picked = arrange && sel === i;
                return (
                  <Pressable key={i} onPress={() => tapPocket(i)} accessibilityRole="button" accessibilityLabel={pk ? `${pk.num} ${pk.have ? '' : 'missing'}` : 'Empty pocket'}
                    style={{ width: pocketW, padding: 4, borderRadius: Math.max(6, pocketW / 16), backgroundColor: c.soft,
                      borderWidth: 2, borderColor: picked ? c.accent : arrange && sel != null ? c.raise : 'transparent' }}>
                    {pk ? <>
                      <View style={{ opacity: pk.have ? 1 : 0.28 }}>
                        <CardArt k={pk.card?.k || pk.own?.card} photo={pk.own ? d.ownPhoto(pk.own) : null} num={pk.num} width={pocketW - 12} qty={pk.own ? Number(pk.own.qty) || 1 : 0} />
                      </View>
                      {!pk.have ? <View pointerEvents="none" style={{ position: 'absolute', top: 8, left: 8, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6, backgroundColor: 'rgba(10,13,11,0.85)' }}>
                        <T size={11} w="bold" mute>{pk.num}</T></View> : null}
                      {showPrices ? <T size={11.5} w={pk.have ? 'semi' : 'medium'} mute={!pk.have} numberOfLines={1} style={{ textAlign: 'center', marginTop: 3 }}>{pk.price ? d.aud(pk.price) : '–'}</T> : null}
                    </> : <View style={{ width: pocketW - 12, aspectRatio: 63 / 88, borderRadius: Math.max(4, pocketW / 20), borderWidth: 1, borderStyle: 'dashed', borderColor: c.raise }} />}
                    {!pk && showPrices ? <T size={11.5} style={{ marginTop: 3 }}> </T> : null}
                  </Pressable>
                );
              })}
            </View>
          </View>
        ))}
      </ScrollView>

      {/* page controls */}
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 14, marginTop: 12 }}>
        <Pressable onPress={() => goPage(page - 1)} disabled={page === 0} hitSlop={10} accessibilityLabel="Previous page"><Ionicons name="chevron-back" size={22} color={page === 0 ? c.raise : c.ink} /></Pressable>
        <T w="semi" size={13.5}>{`Page ${page + 1} of ${pageCount}`}</T>
        <Pressable onPress={() => goPage(page + 1)} disabled={page >= pageCount - 1} hitSlop={10} accessibilityLabel="Next page"><Ionicons name="chevron-forward" size={22} color={page >= pageCount - 1 ? c.raise : c.ink} /></Pressable>
      </View>
      {!pockets.length ? <Panel style={{ marginTop: 14 }}>
        <T w="semi">This binder is empty</T>
        <T mute size={13.5}>Add cards from your collection, or open Customise to fill it from a group or a whole set.</T>
        <Button icon="add" onPress={() => setAdding(true)}>Add cards</Button>
      </Panel> : null}

      <CustomiseSheet open={custom} onClose={() => setCustom(false)} b={b} update={update} remove={async () => {
        setCustom(false); const gone = await bs.remove(b.id); router.back();
        toast(`Deleted “${b.name}”`, { action: { label: 'Undo', onPress: () => bs.save(gone) } });
      }} />
      <AddSheet open={adding} onClose={() => setAdding(false)} inBinder={new Set(pockets.filter(Boolean).map(p => p.key))} onAdd={addOwned} />
    </Screen>
  );
}

function CustomiseSheet({ open, onClose, b, update, remove }) {
  const d = useData(), c = useTheme();
  const [name, setName] = useState(b.name);
  const groups = [...new Set((d.owned || []).filter(o => o.status !== 'sold').map(o => o.group || 'Other'))];
  const started = startedSets(d).map(s => s.id);
  const setOpts = (d.cat?.sets || []).filter(s => s.kind === 'booster' || s.kind === 'extra' || s.kind === 'starter' || s.kind === 'premium')
    .sort((x, y) => Number(started.includes(y.id)) - Number(started.includes(x.id)) || String(y.date || '').localeCompare(String(x.date || '')))
    .map(s => [s.id, `${s.code ? s.code + ' · ' : ''}${s.name}`]);
  const src = b.source || { kind: 'pick' };
  const set = patch => update(patch);
  return (
    <Sheet open={open} onClose={() => { if (name.trim() && name !== b.name) set({ name: name.trim() }); onClose(); }} title="Customise binder">
      <View style={{ gap: 14 }}>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Field label="Name" value={name} onChangeText={setName} onBlur={() => name.trim() && set({ name: name.trim() })} returnKeyType="done" />
        </View>
        <View style={{ gap: 6 }}>
          <T size={12.5} mute>Cover colour</T>
          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
            {COLORS.map(([n, hex]) => (
              <Pressable key={n} onPress={() => set({ color: n })} accessibilityLabel={`${n} cover`}
                style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: hex, borderWidth: 3, borderColor: b.color === n ? c.ink : 'transparent' }} />
            ))}
          </View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Choice label="Pockets per page" value={b.grid} onChange={v => set({ grid: v })} options={[['2x2', '4 (big)'], ['3x3', '9 (classic)'], ['4x3', '12']]} />
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Choice label="Cards come from" value={src.kind} onChange={v => set(cur => { const s0 = cur.source || {}; return { source: v === 'group' ? { kind: 'group', group: s0.group || groups[0] || 'Other' } : v === 'set' ? { kind: 'set', set: s0.set || setOpts[0]?.[0], master: false } : { kind: 'pick' }, sort: v === 'pick' || cur.sort === 'custom' || (v === 'set' && cur.sort === 'added') ? 'number' : cur.sort }; })}
            options={[['pick', 'Cards I pick'], ['group', 'A collection group'], ['set', 'A whole set']]} />
        </View>
        {src.kind === 'group' ? <Select label="Group" value={src.group} onChange={v => set({ source: { kind: 'group', group: v } })} options={groups.map(g => [g, g])} /> : null}
        {src.kind === 'set' ? <>
          <Select label="Set" value={src.set} onChange={v => set(cur => ({ source: { ...cur.source, set: v } }))} options={setOpts} />
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            <Choice label="Pockets for" value={!!src.master} onChange={v => set(cur => ({ source: { ...cur.source, master: v } }))} options={[[false, 'Each card number'], [true, 'Every version (master set)']]} />
          </View>
          <T mute size={12.5}>Cards you don’t own show faded, with their price, so you can see what’s missing.</T>
        </> : null}
        {src.kind !== 'pick' ? <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Choice label="Order" value={b.sort} onChange={v => set({ sort: v })} options={[['number', 'Card number'], ['price', 'Price'], ...(src.kind === 'group' ? [['added', 'Recently added'], ['custom', 'My arrangement']] : [])]} />
        </View> : null}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
          <Choice label="Prices under cards" value={b.showPrices !== false} onChange={v => set({ showPrices: v })} options={[[true, 'Show'], [false, 'Hide']]} />
        </View>
        <Button ghost danger icon="trash-outline" onPress={remove}>Delete binder</Button>
        <T mute size={12}>Deleting a binder never touches your collection.</T>
      </View>
    </Sheet>
  );
}

function AddSheet({ open, onClose, inBinder, onAdd }) {
  const d = useData(), c = useTheme();
  const [q, setQ] = useState('');
  const s = q.trim().toLowerCase();
  const list = (d.owned || []).filter(o => o.status !== 'sold' && !inBinder.has('o:' + o.id) && (!s || `${o.name} ${o.num || ''} ${o.group || ''}`.toLowerCase().includes(s))).slice(0, 60);
  return (
    <Sheet open={open} onClose={onClose} title="Add from your collection">
      <View style={{ gap: 10 }}>
        <SearchBar value={q} onChangeText={setQ} placeholder="Search your collection" />
        {!list.length ? <T mute size={13.5}>{d.session ? 'Everything that matches is already in this binder.' : 'Sign in and add cards to your collection first.'}</T> : null}
        {list.map(o => (
          <Pressable key={o.id} onPress={() => onAdd(o)} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 52 }}>
            <CardArt k={o.card} photo={d.ownPhoto(o)} num={o.num} width={30} />
            <View style={{ flex: 1 }}><T size={14} numberOfLines={1}>{clean(o.name)}</T><T mute size={12}>{[o.num, o.group || 'Other', `×${o.qty || 1}`].filter(Boolean).join(' · ')}</T></View>
            <Ionicons name="add-circle" size={24} color={c.accent} />
          </Pressable>
        ))}
      </View>
    </Sheet>
  );
}
