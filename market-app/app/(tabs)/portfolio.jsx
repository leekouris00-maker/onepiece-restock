import React, { useCallback, useMemo, useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData, clean } from '../../src/data';
import { F, useTheme } from '../../src/theme';
import { Button, CardArt, ChangePill, Change, Empty, MenuItem, Note, Panel, SearchBar, Select, Sheet, SkelRows, Skel, T } from '../../src/ui';
import { IconBtn, Screen, Title } from '../../src/screen';
import { OwnedRow, OwnedTile, PL, plOf } from '../../src/tiles';
import { useLayout } from '../../src/layout';
import { ItemMenu, MoveTo, SetPaid, useOwnedActions } from '../../src/ownact';
import { usePref } from '../../src/prefs';
import { exportCollection } from '../../src/csv';
import { setToastLift, toast } from '../../src/toast';

const SORTS = [['value', 'Highest value'], ['profit', 'Profit / loss'], ['move', 'Biggest change'], ['name', 'Name'], ['new', 'Newest']];
const SHOW = [['owned', 'Owned'], ['sold', 'Sold']];

export default function Collection() {
  const d = useData(), c = useTheme(), act = useOwnedActions();
  const [q, setQ] = useState('');
  const [show, setShow] = useState('owned');
  const [grid, setGrid] = usePref('colGrid', false);
  const [sort, setSort] = usePref('colSort', 'value');
  const [shut, setShut] = useState({});
  const [menu, setMenu] = useState(null);          // entry whose long-press menu is open
  const [more, setMore] = useState(false);
  const [sel, setSel] = useState(null);            // Set of ids when selecting, else null
  const [bulk, setBulk] = useState(null);          // 'move' | 'paid'
  const sold = show === 'sold';
  useFocusEffect(useCallback(() => { if (d.session) d.refresh(); }, [d.session]));
  const { inner, wide } = useLayout(), avail = inner - 32, gap = 12;
  const cols = Math.max(3, Math.min(8, Math.floor((avail + gap) / (130 + gap))));
  const tileW = Math.floor((avail - gap * (cols - 1)) / cols);

  const live = d.owned.filter(o => o.status !== 'sold');
  const tot = o => (d.unitAt(o, 0) || 0) * (Number(o.qty) || 1);
  const sumAt = a => live.reduce((n, o) => n + (d.unitAt(o, a) || 0) * (Number(o.qty) || 1), 0);
  const worth = useMemo(() => [sumAt(0), sumAt(7)], [d.owned, d.cat, d.comps, d.sales, d.watch]);
  const units = live.reduce((n, o) => n + (Number(o.qty) || 1), 0);
  const paidSum = useMemo(() => {
    let paid = 0, now = 0;
    for (const o of live) if (o.paid != null && o.paid !== '') { paid += Number(o.paid) * (Number(o.qty) || 1); now += tot(o); }
    return { paid, d: now - paid, p: paid ? ((now - paid) / paid) * 100 : null };
  }, [d.owned, d.cat, d.comps]);

  const groups = useMemo(() => {
    const s = q.trim().toLowerCase();
    let l = sold ? d.owned.filter(o => o.status === 'sold') : live;
    if (s) l = l.filter(o => { const k = d.card(o.card); return (clean(o.name) + ' ' + (k?.num || o.num || '') + ' ' + (o.group || '') + ' ' + (o.notes || '')).toLowerCase().includes(s); });
    const chg = o => { const a = d.unitAt(o, 0), b = d.unitAt(o, 7); return a && b ? (a - b) / b : 0; };
    const pl = o => plOf(d, o)?.d ?? -Infinity;
    const by = { value: (a, b) => tot(b) - tot(a), profit: (a, b) => pl(b) - pl(a), move: (a, b) => Math.abs(chg(b)) - Math.abs(chg(a)), name: (a, b) => clean(a.name).localeCompare(clean(b.name)), new: (a, b) => String(b.added || '').localeCompare(String(a.added || '')) };
    const m = {}; for (const o of l) (m[sold ? 'Sold' : o.group || 'Other'] ??= []).push(o);
    return Object.entries(m).map(([g, items]) => ({ g, items: items.sort(by[sort] || by.value), total: items.reduce((n, o) => n + (sold ? (Number(o.soldFor) || 0) * (Number(o.qty) || 1) : tot(o)), 0) }))
      .sort((a, b) => b.total - a.total);
  }, [q, sold, sort, d.owned, d.cat, d.comps]);

  const liftBy = sel ? 120 : wide ? 0 : 66;
  useFocusEffect(useCallback(() => { setToastLift(liftBy); return () => setToastLift(0); }, [liftBy]));
  const toggle = o => setSel(s => { const n = new Set(s || []); n.has(o.id) ? n.delete(o.id) : n.add(o.id); return n; });
  const startSel = o => setSel(new Set(o ? [o.id] : []));
  const chosen = sel ? d.owned.filter(o => sel.has(o.id)) : [];
  const shown = groups.flatMap(g => g.items);

  if (!d.configured || (d.authReady && !d.session)) return (
    <Screen><Title>Collection</Title><View style={{ gap: 14, marginTop: 10 }}>
      <T head size={22}>Track what you own</T>
      <T mute>{d.configured ? 'Sign in to save your cards. They follow you to your phone and computer. You can browse and scan prices without an account.' : 'Saving isn’t set up in this build yet.'}</T>
      {d.configured ? <Button onPress={() => router.push('/account')}>Sign in or create an account</Button> : null}
      <Button ghost icon="scan" onPress={() => router.push('/scan')}>Scan a card</Button>
    </View></Screen>
  );

  const firstLoad = !d.loaded && d.busy;
  const empty = !firstLoad && !d.owned.length;
  const rowProps = o => ({ swipe: !sold && !wide, actions: act, selecting: !!sel, selected: !!sel?.has(o.id), onSelect: toggle, onLong: sel ? toggle : setMenu, showPL: sort === 'profit' });

  // phone: Scan / Add within thumb reach, or the selection bar while selecting
  const bottom = sel ? <SelBar n={chosen.length} all={shown.length} onAll={() => setSel(new Set(shown.map(o => o.id)))} onDone={() => setSel(null)}
      onMove={() => setBulk('move')} onPaid={() => setBulk('paid')} onSold={() => { act.many(chosen.filter(o => o.status !== 'sold'), o => ({ status: 'sold', soldFor: d.unitAt(o, 0) == null ? null : Math.round(d.unitAt(o, 0) * 100) / 100 }), `Marked ${chosen.length} sold`); setSel(null); }}
      onRemove={() => { act.removeMany(chosen); setSel(null); }} />
    : !wide && !empty ? <View pointerEvents="box-none" style={{ position: 'absolute', right: 16, bottom: 14, flexDirection: 'row', gap: 10 }}>
        <Fab icon="scan" label="Scan" onPress={() => router.push('/scan')} />
        <Fab icon="add" label="Add" primary onPress={() => router.push('/item/new')} />
      </View> : null;

  return (
    <Screen onRefresh={async () => { d.loadCatalog(true); await d.refresh(); }} refreshing={d.busy} after={bottom}>
      <Title right={<View style={{ flexDirection: 'row', gap: 8 }}>
        {wide ? <IconBtn icon="refresh" label="Reload" onPress={() => { d.refresh(); d.loadCatalog(true); }} /> : null}
        <IconBtn icon={grid ? 'list' : 'grid-outline'} label={grid ? 'List view' : 'Grid view'} onPress={() => setGrid(!grid)} />
        <IconBtn icon={sel ? 'close' : 'checkmark-circle-outline'} label={sel ? 'Stop selecting' : 'Select several'} on={!!sel} onPress={() => (sel ? setSel(null) : startSel())} />
        {wide ? <IconBtn icon="scan" label="Scan a card" onPress={() => router.push('/scan')} /> : null}
        {wide ? <IconBtn icon="add" label="Add item" onPress={() => router.push('/item/new')} /> : null}
        <IconBtn icon="ellipsis-horizontal" label="More" onPress={() => setMore(true)} />
      </View>}>Collection</Title>

      {firstLoad ? <View style={{ gap: 10, marginTop: 4 }}><Skel w={180} h={34} /><Skel w={120} h={12} /></View> : <>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 2 }}>
          <T head size={32} style={{ letterSpacing: -1 }}>{d.cat ? d.aud(worth[0]) : '…'}</T>
          <ChangePill now={worth[0]} then={worth[1]} />
        </View>
        <T mute size={13}>{units} items · change over 7 days</T>
        {paidSum.paid ? <View style={{ flexDirection: 'row', gap: 6, marginTop: 4, flexWrap: 'wrap', alignItems: 'center' }}>
          <T size={13} mute>Paid {d.aud(paidSum.paid)} ·</T><PL v={paidSum} size={13} />
          <T size={12} mute>on items with a price paid</T>
        </View> : null}
      </>}

      {d.loadError ? <Note tone="warn" title="Couldn’t load your collection" style={{ marginTop: 14 }} action="Retry" onAction={() => d.refresh()}>{d.loadError}</Note> : null}

      {empty ? <Panel style={{ marginTop: 18, gap: 12 }}>
        <T head size={20}>Start your collection</T>
        <T mute size={14}>Scan cards with your camera, search for them by name or number, or bring in a list from Collectr or a spreadsheet.</T>
        <Button icon="scan" onPress={() => router.push('/scan')}>Scan your first card</Button>
        <Button ghost icon="search" onPress={() => router.push('/search')}>Search and add</Button>
        <Button ghost icon="cloud-upload-outline" onPress={() => router.push('/import')}>Import a CSV</Button>
      </Panel> : <>
        <View style={{ marginTop: 16 }}><SearchBar value={q} onChangeText={setQ} placeholder="Search your collection" /></View>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <Select value={sort} onChange={setSort} options={SORTS} label="Sort by" />
          <Select value={show} onChange={v => { setShow(v); setSel(null); }} options={SHOW} label="Show" />
          {!wide && !sel && !grid && !sold ? <T size={12} mute style={{ marginLeft: 4 }}>Swipe a row left for quick changes, hold for more</T> : null}
        </View>
      </>}

      {firstLoad ? <Panel style={{ marginTop: 14 }}><SkelRows n={6} art={38} /></Panel> : null}
      {!empty && !firstLoad && !groups.length ? <Empty>{q ? `Nothing in your collection matches “${q}”.` : sold ? 'Nothing sold yet.' : 'Nothing here yet.'}</Empty> : null}
      {wide && !grid && !firstLoad && groups.length ? <Table groups={groups} sel={sel} toggle={toggle} onMenu={setMenu} sold={sold} /> : groups.map(({ g, items, total }) => {
        const closed = shut[g] && !q;
        return (
          <Panel key={g} style={{ marginTop: 14, gap: closed ? 0 : 4 }}>
            <Pressable onPress={() => setShut(s => ({ ...s, [g]: !s[g] }))} accessibilityRole="button" accessibilityState={{ expanded: !closed }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 40 }}>
              <View style={{ flex: 1 }}>
                <T w="bold" size={15.5} numberOfLines={1}>{g}</T>
                <T size={12} mute>{items.length} {items.length === 1 ? 'entry' : 'entries'}</T>
              </View>
              {sel ? <Pressable hitSlop={8} onPress={() => setSel(s => { const n = new Set(s); const all = items.every(o => n.has(o.id)); items.forEach(o => (all ? n.delete(o.id) : n.add(o.id))); return n; })}>
                <T w="semi" size={13} style={{ color: c.accent }}>{items.every(o => sel.has(o.id)) ? 'None' : 'All'}</T></Pressable> : null}
              <T w="bold" size={15}>{d.aud(total)}</T>
              <Ionicons name={closed ? 'chevron-down' : 'chevron-up'} size={16} color={c.mute} />
            </Pressable>
            {closed ? null : grid ? (
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap, rowGap: 16, marginTop: 6 }}>
                {items.map(o => <OwnedTile key={o.id} o={o} width={tileW} selecting={!!sel} selected={!!sel?.has(o.id)} onSelect={toggle} onLong={sel ? toggle : setMenu} />)}
              </View>
            ) : items.map(o => <OwnedRow key={o.id} o={o} {...rowProps(o)} />)}
          </Panel>
        );
      })}
      {!empty ? <T mute size={12} style={{ marginTop: 22 }}>Values use your own estimate first, then the eBay median for cards you track, then your logged sales, then TCGplayer.</T> : null}

      {menu ? <ItemMenu o={menu} onClose={() => setMenu(null)} onSelect={o => startSel(o)} /> : null}
      <Sheet open={more} onClose={() => setMore(false)} title="Collection">
        <MenuItem icon="refresh" label="Reload" sub="Get the latest prices and your saved items" onPress={() => { setMore(false); d.refresh(); d.loadCatalog(true); }} />
        <MenuItem icon="cloud-upload-outline" label="Import a CSV" sub="From Collectr, TCGplayer or a spreadsheet" onPress={() => { setMore(false); router.push('/import'); }} />
        <MenuItem icon="download-outline" label="Export as CSV" sub="Opens in Excel or Google Sheets" onPress={() => { setMore(false); exportCollection(d); }} />
        <MenuItem icon="star-outline" label="Watchlist and price alerts" onPress={() => { setMore(false); router.push('/watchlist'); }} />
      </Sheet>
      <Sheet open={!!bulk} onClose={() => setBulk(null)} title={bulk === 'move' ? `Move ${chosen.length} to a group` : 'Price paid'}>
        {bulk === 'move' ? <MoveTo list={chosen} onDone={() => { setBulk(null); setSel(null); }} /> : bulk === 'paid' ? <SetPaid list={chosen} onDone={() => { setBulk(null); setSel(null); }} /> : null}
      </Sheet>
    </Screen>
  );
}

function Fab({ icon, label, onPress, primary }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 6, height: 52, paddingHorizontal: 18, borderRadius: 26,
        backgroundColor: primary ? c.accent : c.raise, opacity: pressed ? 0.85 : 1, shadowColor: '#000', shadowOpacity: 0.4, shadowRadius: 12, shadowOffset: { width: 0, height: 4 } })}>
      <Ionicons name={icon} size={20} color={primary ? c.onAccent : c.ink} />
      <T w="bold" size={15} style={{ color: primary ? c.onAccent : c.ink }}>{label}</T>
    </Pressable>
  );
}

function SelBar({ n, all, onAll, onDone, onMove, onPaid, onSold, onRemove }) {
  const c = useTheme();
  const B = ({ icon, label, onPress, danger }) => (
    <Pressable onPress={onPress} disabled={!n} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed }) => ({ flex: 1, minWidth: 58, alignItems: 'center', justifyContent: 'center', gap: 2, paddingVertical: 6, borderRadius: 12, opacity: !n ? 0.4 : pressed ? 0.6 : 1 })}>
      <Ionicons name={icon} size={20} color={danger ? c.down : c.ink} />
      <T size={11.5} w="semi" style={danger ? { color: c.down } : null}>{label}</T>
    </Pressable>
  );
  return (
    <View style={{ position: 'absolute', left: 12, right: 12, bottom: 12, alignItems: 'center' }}>
      <View style={{ width: '100%', maxWidth: 620, borderRadius: 20, backgroundColor: c.raise, padding: 10, gap: 6, shadowColor: '#000', shadowOpacity: 0.45, shadowRadius: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 6 }}>
          <T w="bold" size={14}>{n} selected</T>
          <View style={{ flexDirection: 'row', gap: 16 }}>
            <Pressable onPress={onAll} hitSlop={8}><T w="semi" size={13.5} style={{ color: c.accent }}>All {all}</T></Pressable>
            <Pressable onPress={onDone} hitSlop={8}><T w="semi" size={13.5}>Done</T></Pressable>
          </View>
        </View>
        <View style={{ flexDirection: 'row' }}>
          <B icon="folder-open-outline" label="Move" onPress={onMove} />
          <B icon="pricetag-outline" label="Paid" onPress={onPaid} />
          <B icon="cash-outline" label="Sold" onPress={onSold} />
          <B icon="trash-outline" label="Remove" danger onPress={onRemove} />
        </View>
      </View>
    </View>
  );
}

// Computer: a table you can edit in place (quantity and price paid save when you leave the box)
function Table({ groups, sel, toggle, onMenu, sold }) {
  const d = useData(), c = useTheme();
  const H = ({ children, w, right }) => <T mute size={12} w="semi" style={{ width: w, flex: w ? undefined : 1, textAlign: right ? 'right' : 'left' }}>{children}</T>;
  return groups.map(({ g, items, total }) => (
    <Panel key={g} style={{ marginTop: 14, gap: 0, paddingVertical: 10 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 6 }}>
        <T w="bold" size={15.5} style={{ flex: 1 }}>{g} <T mute size={12.5}>· {items.length}</T></T>
        <T w="bold" size={15}>{d.aud(total)}</T>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: c.line }}>
        {sel ? <View style={{ width: 24 }} /> : null}
        <H>Card</H><H w={64} right>Qty</H><H w={96} right>Paid each</H><H w={96} right>Value each</H><H w={104} right>Total</H><H w={140} right>{sold ? 'Sold for' : 'Profit / loss'}</H><H w={78} right>7 days</H><View style={{ width: 32 }} />
      </View>
      {items.map(o => <TableRow key={o.id} o={o} sel={sel} toggle={toggle} onMenu={onMenu} />)}
    </Panel>
  ));
}

function Cell({ value, onSave, w, prefix }) {
  const c = useTheme();
  const [v, setV] = useState(null);
  const [focus, setFocus] = useState(false);
  const shown = v ?? (value == null ? '' : String(value));
  const commit = () => { if (v != null && v !== String(value ?? '')) onSave(v); setV(null); };
  return (
    <View style={{ width: w, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 2, borderRadius: 8, borderWidth: 1, borderColor: focus ? c.accent : 'transparent', backgroundColor: focus ? c.soft : 'transparent', paddingHorizontal: 6 }}>
      {prefix && shown !== '' ? <T mute size={13}>{prefix}</T> : null}
      <TextInput value={shown} onChangeText={setV} onFocus={() => setFocus(true)} onBlur={() => { setFocus(false); commit(); }} onSubmitEditing={commit}
        placeholder="–" placeholderTextColor={c.mute} keyboardType="decimal-pad" selectTextOnFocus
        style={{ flex: 1, minWidth: 0, height: 34, textAlign: 'right', color: c.ink, fontFamily: F.semi, fontSize: 14, outlineStyle: 'none' }} />
    </View>
  );
}

function TableRow({ o, sel, toggle, onMenu }) {
  const d = useData(), c = useTheme(), act = useOwnedActions();
  const card = d.card(o.card), q = Number(o.qty) || 1, each = d.unitAt(o, 0), soldIt = o.status === 'sold';
  const save = ch => d.saveOwned({ ...o, ...ch }).then(() => toast('Saved'), e => toast(e.message || String(e)));
  const num = s => { const n = parseFloat(String(s).replace(',', '.')); return isNaN(n) ? null : n; };
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: c.line }}>
      {sel ? <Pressable onPress={() => toggle(o)} hitSlop={6} accessibilityRole="checkbox" accessibilityState={{ checked: sel.has(o.id) }}>
        <Ionicons name={sel.has(o.id) ? 'checkmark-circle' : 'ellipse-outline'} size={22} color={sel.has(o.id) ? c.accent : c.mute} /></Pressable> : null}
      <Pressable onPress={() => (sel ? toggle(o) : router.push({ pathname: '/item/[id]', params: { id: o.id } }))} accessibilityRole="link"
        style={({ hovered }) => ({ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10, minWidth: 0, borderRadius: 8, padding: 2, backgroundColor: hovered ? c.soft : 'transparent' })}>
        <CardArt k={o.card} photo={d.ownPhoto(o)} num={card?.num || o.num} width={30} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <T w="semi" size={14} numberOfLines={1}>{clean(o.name)}</T>
          <T mute size={12} numberOfLines={1}>{[card?.num || o.num, o.cond !== 'Raw' ? o.cond : null, o.lang !== 'EN' ? o.lang : null].filter(Boolean).join(' · ')}</T>
        </View>
      </Pressable>
      <Cell w={64} value={q} onSave={v => { const n = parseInt(v, 10); if (n > 0) save({ qty: n }); else if (n === 0) act.remove(o); }} />
      <Cell w={96} prefix="A$" value={o.paid} onSave={v => save({ paid: num(v) })} />
      <T size={14} style={{ width: 96, textAlign: 'right' }}>{soldIt ? d.aud(Number(o.soldFor) || 0) : d.aud(each)}</T>
      <T size={14} w="bold" style={{ width: 104, textAlign: 'right' }}>{soldIt ? d.aud((Number(o.soldFor) || 0) * q) : d.aud(each == null ? null : each * q)}</T>
      <View style={{ width: 140, alignItems: 'flex-end' }}>{plOf(d, o) ? <PL v={plOf(d, o)} size={13} /> : <T mute size={13}>–</T>}</View>
      <View style={{ width: 78, alignItems: 'flex-end' }}>{soldIt ? <T mute size={12.5}>Sold</T> : <Change now={each} then={d.unitAt(o, 7)} aud={d.aud} size={12.5} pctOnly />}</View>
      <Pressable onPress={() => onMenu(o)} hitSlop={6} accessibilityLabel="More" style={({ hovered }) => ({ width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: hovered ? c.raise : 'transparent' })}>
        <Ionicons name="ellipsis-horizontal" size={18} color={c.mute} />
      </Pressable>
    </View>
  );
}
