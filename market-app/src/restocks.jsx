// Restocks (27 Nov 2026): the Restocks tab of Market. One live feed of retail restocks across Australia:
// sightings from collectors (photo required, others confirm "still there" / "gone"), shop posts (later),
// and the restock watcher (only shops that let it in). Confirmed sightings add bounty only, no points.
// Database: supabase/2026-11-27-restocks.sql. Alerts are sent by restock_alerts.py.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Image, Linking, Platform, Pressable, TextInput, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { manipulateAsync, SaveFormat } from 'expo-image-manipulator';
import { clean, newId, supabase, useData, useTrack } from './data';
import { useTheme } from './theme';
import { Button, Chip, Field, MenuItem, Note, Panel, SearchBar, Select, Sheet, T } from './ui';
import { ChipRow } from './screen';
import { usePref } from './prefs';
import { toast } from './toast';
import { haptic } from './haptic';
import { pickPhoto } from './photo';
import { currentSub, pushState, turnOn } from './push';
import { berries, rankOf } from './points';

export const STATES = ['VIC', 'NSW', 'QLD', 'WA', 'SA', 'TAS', 'ACT', 'NT'];
export const KINDS = [['box', 'Booster boxes'], ['pack', 'Packs'], ['case', 'Cases'], ['deck', 'Starter decks'], ['promo', 'Promos'], ['other', 'Other']];
const KIND_SHORT = { box: 'Boxes', pack: 'Packs', case: 'Cases', deck: 'Decks', promo: 'Promos', other: 'Other' };
export const CHAINS = ['Kmart', 'Big W', 'Target', 'JB Hi-Fi', 'EB Games', 'Toymate', 'Zing', 'Gametraders'];
const SOURCE = { sighting: ['eye-outline', 'Sighting'], shop: ['storefront-outline', 'Shop post'], bot: ['radio-outline', 'Found by our watcher'] };

// guess the kind from a product's name
export function kindOf(name) {
  const n = String(name || '').toLowerCase();
  if (/case/.test(n)) return 'case';
  if (/booster box|display|box\b/.test(n)) return 'box';
  if (/starter deck|deck\b/.test(n)) return 'deck';
  if (/pack|sleeve|blister/.test(n)) return 'pack';
  if (/promo/.test(n)) return 'promo';
  return 'other';
}
export const photoUrl = path => (path && supabase ? supabase.storage.from('sightings').getPublicUrl(path).data.publicUrl : null);
function since(t) {
  const m = Math.max(0, Math.round((Date.now() - new Date(t).getTime()) / 60000));
  return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 24 * 60 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago`;
}
const missing = e => e && (e.code === 'PGRST202' || e.code === '42883' || /could not find the function|does not exist/i.test(e.message || ''));
const nice = e => {
  const m = (e && (e.message || String(e))) || 'Something went wrong';
  return m.replace(/^.*?ERROR:\s*/, '');
};

export function RestocksView() {
  const d = useData(), c = useTheme();
  useTrack('restocks');
  const [state, setState] = usePref('restockState', 'ALL');
  const [kind, setKind] = useState('all');
  const [list, setList] = useState(null);
  const [err, setErr] = useState('');
  const [notSetUp, setNotSetUp] = useState(false);
  const [posting, setPosting] = useState(false);
  const [alerts, setAlerts] = useState(false);
  const [menu, setMenu] = useState(null);
  const [owner, setOwner] = useState(false);
  const [spotters, setSpotters] = useState([]);

  const load = useCallback(async () => {
    if (!supabase) { setList([]); return; }
    const r = await supabase.rpc('restock_feed', { st: state === 'ALL' ? null : state, lim: 100 });
    if (r.error) { if (missing(r.error)) setNotSetUp(true); else setErr(r.error.message); setList(l => l || []); return; }
    setErr(''); setNotSetUp(false); setList(r.data || []);
    supabase.rpc('restock_top_spotters').then(x => !x.error && setSpotters(x.data || []), () => {});
  }, [state]);
  useEffect(() => { load(); }, [load]);
  useFocusEffect(useCallback(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]));
  useEffect(() => { if (d.session && supabase) supabase.rpc('am_owner').then(r => setOwner(!!r.data?.owner), () => {}); }, [d.session]);

  const shown = (list || []).filter(p => kind === 'all' || p.kind === kind);
  const kindsHere = useMemo(() => new Set((list || []).map(p => p.kind)), [list]);
  const needSignIn = () => { toast('Sign in to do that'); router.push({ pathname: '/account', params: { back: '1' } }); };

  const vote = async (p, still) => {
    if (!d.session) return needSignIn();
    const r = await supabase.rpc('vote_restock', { pid: p.id, still });
    if (r.error) { toast(nice(r.error)); return; }
    haptic(); toast(still ? 'Thanks: marked still there' : 'Thanks: marked gone');
    load();
  };

  return (
    <View style={{ gap: 14, marginTop: 10 }}>
      <T mute size={13.5}>Live retail restocks across Australia, from collectors who saw the stock, shops and our watcher. Retail stock only.</T>
      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}><Button icon="camera-outline" onPress={() => (d.session ? setPosting(true) : needSignIn())}>Report a restock</Button></View>
        <Button ghost icon="notifications-outline" onPress={() => (d.session ? setAlerts(true) : needSignIn())}>Alerts</Button>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Select label="Where" value={state} onChange={setState} options={[['ALL', 'All of Australia'], ...STATES.map(s => [s, s])]} />
        <T mute size={12.5} style={{ flex: 1, textAlign: 'right' }}>{list ? `${shown.length} live` : 'Loading…'}</T>
      </View>
      <ChipRow>
        <Chip on={kind === 'all'} onPress={() => setKind('all')}>All</Chip>
        {KINDS.filter(([k]) => kindsHere.has(k) || kind === k).map(([k]) => <Chip key={k} on={kind === k} onPress={() => setKind(k)}>{KIND_SHORT[k]}</Chip>)}
      </ChipRow>

      {notSetUp ? <Note title="One database step first">Restocks switch on once supabase/2026-11-27-restocks.sql has been run in Supabase.</Note> : null}
      {err ? <Note tone="warn" title="Couldn’t load restocks">{err}</Note> : null}
      {list && !shown.length && !notSetUp ? <Panel>
        <T w="semi" size={15}>No live restocks {state === 'ALL' ? 'right now' : `in ${state} right now`}</T>
        <T mute size={13.5}>Seen One Piece stock in a shop? Post a photo of the shelf. When two people confirm it, you get ฿10M bounty.</T>
      </Panel> : null}
      {shown.map(p => <RestockCard key={p.id} p={p} onVote={vote} onMenu={() => setMenu(p)} />)}

      {spotters.length ? <Panel title="Top spotters this week" right={<T mute size={12}>Confirmed sightings</T>}>
        {spotters.map((s, i) => {
          const r = rankOf(s.bounty || 0);
          return (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 34 }}>
              <T w="bold" size={14} style={{ width: 22, color: i < 3 ? c.accent : c.mute }}>{i + 1}</T>
              <T size={14} style={{ flex: 1 }} w={s.me ? 'bold' : 'medium'}>{s.me ? 'You' : `${r.label} from ${s.state}`}</T>
              <T w="semi" size={14}>{s.n}</T>
            </View>
          );
        })}
      </Panel> : null}

      <PostSheet open={posting} onClose={() => setPosting(false)} onPosted={() => { setPosting(false); setKind('all'); load(); }} defaultState={state === 'ALL' ? null : state} />
      <AlertSheet open={alerts} onClose={() => setAlerts(false)} />
      {menu ? <PostMenu p={menu} owner={owner} onClose={() => setMenu(null)} onDone={load} /> : null}
    </View>
  );
}

function RestockCard({ p, onVote, onMenu }) {
  const d = useData(), c = useTheme();
  const card = p.k && d.card ? d.card(p.k) : null;
  const market = card && card.m ? card.m * (d.fx || 1.5) : null;
  const diff = market && p.price ? Math.round(((p.price - market) / market) * 100) : null;
  const [icon, label] = SOURCE[p.source] || SOURCE.sighting;
  const img = photoUrl(p.photo);
  const voted = p.my_vote;
  return (
    <View style={{ borderRadius: 18, backgroundColor: c.panel, borderWidth: 1, borderColor: c.line, overflow: 'hidden' }}>
      <View style={{ flexDirection: 'row', gap: 12, padding: 12 }}>
        <Pressable onPress={() => img && Linking.openURL(img)} disabled={!img} accessibilityLabel="Shelf photo"
          style={{ width: 76, height: 96, borderRadius: 10, overflow: 'hidden', backgroundColor: c.raise, alignItems: 'center', justifyContent: 'center' }}>
          {img ? <Image source={{ uri: img }} style={{ width: '100%', height: '100%' }} resizeMode="cover" />
            : <Ionicons name={icon} size={26} color={c.mute} />}
        </Pressable>
        <View style={{ flex: 1, gap: 3, minWidth: 0 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
            <Ionicons name={icon} size={13} color={c.accent} />
            <T size={11.5} w="semi" style={{ color: c.accent, flex: 1 }} numberOfLines={1}>{label.toUpperCase()} · {since(p.created_at)}</T>
            <Pressable onPress={onMenu} hitSlop={10} accessibilityRole="button" accessibilityLabel={`More for ${p.title}`}>
              <Ionicons name="ellipsis-horizontal" size={18} color={c.mute} />
            </Pressable>
          </View>
          <T w="bold" size={15.5} numberOfLines={2}>{p.title}</T>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {p.price ? <T w="bold" size={16}>{`A$${Number(p.price).toLocaleString('en-AU', { maximumFractionDigits: 2 })}`}</T> : <T mute size={13}>Price not given</T>}
            {diff != null && Math.abs(diff) >= 3 ? <View style={{ paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, backgroundColor: diff < 0 ? c.accentDim : 'rgba(255,91,91,0.14)' }}>
              <T w="bold" size={12} style={{ color: diff < 0 ? c.up : c.down }}>{diff < 0 ? `${-diff}% under market` : `${diff}% over market`}</T>
            </View> : null}
          </View>
          <T size={13} numberOfLines={1}>{[p.store, p.suburb, p.state === 'ONLINE' ? 'Online' : p.state].filter(Boolean).join(' · ')}</T>
          {p.note ? <T mute size={12.5} numberOfLines={2}>{p.note}</T> : null}
        </View>
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, paddingBottom: 12 }}>
        {p.source !== 'bot' ? <T mute size={12.5} style={{ flex: 1 }}>{p.still ? `${p.still} ${p.still === 1 ? 'person says' : 'people say'} still there` : 'Not confirmed yet'}{p.gone ? ` · ${p.gone} gone` : ''}</T>
          : <T mute size={12.5} style={{ flex: 1 }}>Checked automatically</T>}
        {p.url ? <Pressable onPress={() => Linking.openURL(p.url)} accessibilityRole="link" accessibilityLabel={`Open ${p.store}`}
          style={({ pressed }) => ({ paddingHorizontal: 12, minHeight: 34, borderRadius: 17, justifyContent: 'center', backgroundColor: pressed ? c.raise : c.soft })}>
          <T w="semi" size={13}>Shop ›</T>
        </Pressable> : null}
        {!p.mine && p.source !== 'bot' ? <>
          <Pressable onPress={() => onVote(p, true)} accessibilityRole="button" accessibilityLabel="Still there" accessibilityState={{ selected: voted === true }}
            style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 11, minHeight: 34, borderRadius: 17, backgroundColor: voted === true ? c.accent : pressed ? c.raise : c.soft })}>
            <Ionicons name="checkmark" size={15} color={voted === true ? c.onAccent : c.ink} />
            <T w="semi" size={13} style={{ color: voted === true ? c.onAccent : c.ink }}>Still there</T>
          </Pressable>
          <Pressable onPress={() => onVote(p, false)} accessibilityRole="button" accessibilityLabel="Gone" accessibilityState={{ selected: voted === false }}
            style={({ pressed }) => ({ paddingHorizontal: 11, minHeight: 34, borderRadius: 17, justifyContent: 'center', backgroundColor: voted === false ? c.down : pressed ? c.raise : c.soft })}>
            <T w="semi" size={13} style={{ color: voted === false ? '#fff' : c.ink }}>Gone</T>
          </Pressable>
        </> : null}
      </View>
    </View>
  );
}

function PostMenu({ p, owner, onClose, onDone }) {
  const d = useData();
  const go = f => async () => { onClose(); try { await f(); } catch (e) { toast(nice(e)); } };
  const rpc = async (fn, args, msg) => { const r = await supabase.rpc(fn, args); if (r.error) throw r.error; toast(msg); onDone(); };
  return (
    <Sheet open onClose={onClose} title={p.title}>
      {p.url ? <MenuItem icon="open-outline" label={`Open ${p.store}`} onPress={go(() => Linking.openURL(p.url))} /> : null}
      {p.photo ? <MenuItem icon="image-outline" label="See the photo" onPress={go(() => Linking.openURL(photoUrl(p.photo)))} /> : null}
      {p.k ? <MenuItem icon="pricetags-outline" label="Market price" onPress={go(() => router.push({ pathname: '/card/[k]', params: { k: p.k } }))} /> : null}
      {p.mine ? <>
        <MenuItem icon="close-circle-outline" label="Sold out" sub="Take it off the feed" onPress={go(() => rpc('close_restock', { pid: p.id, remove: false }, 'Marked sold out'))} />
        <MenuItem icon="trash-outline" label="Delete my post" danger onPress={go(() => rpc('close_restock', { pid: p.id, remove: true }, 'Post deleted'))} />
      </> : d.session ? <MenuItem icon="flag-outline" label="Report this post" sub="Fake, wrong, resale or not One Piece" onPress={go(() => rpc('report_restock', { pid: p.id, reason: 'reported' }, 'Reported. Thanks.'))} /> : null}
      {owner ? <>
        <MenuItem icon="eye-off-outline" label="Owner: hide this post" danger onPress={go(() => rpc('owner_restock', { pid: p.id, action: 'hide' }, 'Hidden'))} />
        {p.source === 'sighting' && !p.mine ? <MenuItem icon="ban-outline" label="Owner: ban this poster" sub="Hides all their posts" danger onPress={go(() => rpc('owner_restock', { pid: p.id, action: 'ban' }, 'Poster banned'))} /> : null}
      </> : null}
    </Sheet>
  );
}

function PostSheet({ open, onClose, onPosted, defaultState }) {
  const d = useData(), c = useTheme();
  const [q, setQ] = useState('');
  const [prod, setProd] = useState(null);           // { k, title }
  const [title, setTitle] = useState('');
  const [kind, setKind] = useState('box');
  const [price, setPrice] = useState('');
  const [chain, setChain] = useState('');
  const [store, setStore] = useState('');
  const [suburb, setSuburb] = useState('');
  const [lastState, setLastState] = usePref('restockPostState', 'VIC');
  const [st, setSt] = useState(defaultState || lastState || 'VIC');
  const [uri, setUri] = useState(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) setSt(defaultState || lastState || 'VIC'); }, [open]);
  const reset = () => { setQ(''); setProd(null); setTitle(''); setPrice(''); setChain(''); setStore(''); setSuburb(''); setUri(null); setNote(''); };
  const sealed = useMemo(() => (d.cat ? d.cat.list.filter(x => x.t === 'sealed') : []), [d.cat]);
  const hits = useMemo(() => {
    // "OP-14", "op14" and "OP14" all match (hyphens ignored); newest sets first
    const w = q.trim().toLowerCase().replace(/-/g, '').split(/\s+/).filter(Boolean);
    if (!w.length) return [];
    return sealed.filter(x => { const n = (x.n + ' ' + (d.cat.byId[x.g]?.code || '')).toLowerCase().replace(/-/g, ''); return w.every(t => n.includes(t)); })
      .sort((a, b) => String(d.cat.byId[b.g]?.date || '').localeCompare(String(d.cat.byId[a.g]?.date || ''))).slice(0, 6);
  }, [q, sealed]);
  // "OP-14 The Azure Sea's Seven Booster Box": the set code first, as people say it
  const named = x => { const m = String(d.cat.byId[x.g]?.code || '').match(/^([A-Z]+)-?(\d+)/); const n = clean(x.n); return m && !n.toUpperCase().includes(`${m[1]}-${m[2]}`) ? `${m[1]}-${m[2]} ${n}` : n; };
  const pick = x => { const n = named(x); setProd({ k: x.k, title: n }); setTitle(n); setKind(kindOf(n)); setQ(''); };
  const storeName = chain && chain !== 'Other' ? chain : store.trim();
  const ok = title.trim().length >= 3 && storeName.length >= 2 && uri && st;

  const post = async () => {
    if (!ok || busy) return;
    setBusy(true);
    try {
      const uid = d.session.user.id;
      const small = await manipulateAsync(uri, [{ resize: { width: 1200 } }], { compress: 0.75, format: SaveFormat.JPEG });
      const body = await (await fetch(small.uri)).arrayBuffer();
      const path = `${uid}/${newId()}.jpg`;
      const up = await supabase.storage.from('sightings').upload(path, body, { contentType: 'image/jpeg' });
      if (up.error) throw new Error(/bucket/i.test(up.error.message) ? 'Restocks need the database update first (supabase/2026-11-27-restocks.sql).' : up.error.message);
      const n = price.replace(/[^0-9.]/g, '');
      const r = await supabase.rpc('post_sighting', {
        k: prod?.k || null, title: title.trim(), kind, price: n ? Number(n) : null, store: storeName, chain: chain && chain !== 'Other' ? chain : null,
        suburb: suburb.trim() || null, state: st, url: null, photo: path, note: note.trim() || null,
      });
      if (r.error) { supabase.storage.from('sightings').remove([path]).catch(() => {}); throw r.error; }
      setLastState(st);
      haptic('success');
      toast('Posted. When 2 people confirm it’s still there, you get ฿10M bounty.');
      reset(); onPosted();
    } catch (e) { toast(nice(e)); } finally { setBusy(false); }
  };

  return (
    <Sheet open={open} onClose={onClose} title="Report a restock">
      <T mute size={13}>Seen One Piece stock on a shop shelf? Retail stock only, no resale listings.</T>
      {prod ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: 12, backgroundColor: c.soft }}>
        <Ionicons name="cube-outline" size={18} color={c.accent} />
        <T w="semi" size={14} style={{ flex: 1 }} numberOfLines={2}>{prod.title}</T>
        <Pressable onPress={() => { setProd(null); setTitle(''); }} hitSlop={8} accessibilityLabel="Change product"><T w="semi" size={13} style={{ color: c.accent }}>Change</T></Pressable>
      </View> : <>
        <SearchBar value={q} onChangeText={setQ} placeholder="What did you see? e.g. OP-14 box" />
        {hits.map(x => (
          <Pressable key={x.k} onPress={() => pick(x)} accessibilityRole="button" style={({ pressed }) => ({ paddingVertical: 10, paddingHorizontal: 6, borderRadius: 10, backgroundColor: pressed ? c.soft : 'transparent' })}>
            <T size={14} numberOfLines={1}>{named(x)}</T>
          </Pressable>
        ))}
        {q.trim().length >= 3 ? <Pressable onPress={() => { setTitle(q.trim()); setProd({ k: null, title: q.trim() }); setKind(kindOf(q)); setQ(''); }} style={{ paddingVertical: 8, paddingHorizontal: 6 }}>
          <T size={13.5} style={{ color: c.accent }}>{`Use “${q.trim()}”`}</T>
        </Pressable> : null}
      </>}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
        <View style={{ flexBasis: '100%', gap: 6 }}>
          <T size={12.5} mute>What is it</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{KINDS.map(([k, l]) => <Chip key={k} on={kind === k} onPress={() => setKind(k)}>{l}</Chip>)}</View>
        </View>
        <Field label="Price each (A$)" value={price} onChangeText={setPrice} keyboardType="decimal-pad" placeholder="e.g. 179" />
        <View style={{ flexBasis: '100%', gap: 6 }}>
          <T size={12.5} mute>Shop</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{[...CHAINS, 'Other'].map(x => <Chip key={x} on={chain === x} onPress={() => setChain(x)}>{x === 'Other' ? 'Other shop' : x}</Chip>)}</View>
        </View>
        {chain === 'Other' ? <Field label="Shop name" value={store} onChangeText={setStore} placeholder="e.g. Good Games Melbourne" /> : null}
        <Field label="Suburb" value={suburb} onChangeText={setSuburb} placeholder="e.g. Box Hill" />
        <View style={{ flexBasis: '100%', gap: 6 }}>
          <T size={12.5} mute>State</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{STATES.map(s => <Chip key={s} on={st === s} onPress={() => setSt(s)}>{s}</Chip>)}</View>
        </View>
        <Field label="Note (optional)" value={note} onChangeText={setNote} placeholder="e.g. 2 per customer, back of the toy aisle" maxLength={200} />
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        {uri ? <Image source={{ uri }} style={{ width: 64, height: 80, borderRadius: 8 }} /> : null}
        <View style={{ flex: 1 }}><Button ghost icon="camera-outline" onPress={() => pickPhoto(setUri)}>{uri ? 'Change photo' : 'Add a photo of the shelf'}</Button></View>
      </View>
      <T mute size={12}>Your photo is shown to everyone. Don’t include people’s faces. Your post shows the shop and suburb, never where you are.</T>
      <Button icon="send-outline" disabled={!ok || busy} onPress={post}>{busy ? 'Posting…' : !uri ? 'Add a photo to post' : 'Post restock'}</Button>
    </Sheet>
  );
}

function AlertSheet({ open, onClose }) {
  const d = useData(), c = useTheme();
  const [row, setRow] = useState(null);
  const [push, setPush] = useState(null);
  const [busy, setBusy] = useState(false);
  const [max, setMax] = useState('');
  useEffect(() => {
    if (!open || !supabase || !d.session) return;
    supabase.from('restock_alerts').select('*').maybeSingle().then(r => {
      const x = r.data || { enabled: false, kinds: ['box'], max_price: null, states: [], sources: ['sighting', 'shop', 'bot'], fresh: true };
      setRow(x); setMax(x.max_price ? String(x.max_price) : '');
    }, () => setRow({ enabled: false, kinds: ['box'], states: [], sources: ['sighting', 'shop', 'bot'] }));
    currentSub().then(s => setPush(!!s));
  }, [open]);
  const ps = pushState();
  const flip = (key, v) => setRow(r => ({ ...r, [key]: r[key].includes(v) ? r[key].filter(x => x !== v) : [...r[key], v] }));
  const save = async on => {
    setBusy(true);
    try {
      if (on && !push) { await turnOn(d); setPush(true); }
      const n = max.replace(/[^0-9.]/g, '');
      const body = { user_id: d.session.user.id, enabled: on, kinds: row.kinds.length ? row.kinds : ['box'], max_price: n ? Number(n) : null, states: row.states, sources: row.sources.length ? row.sources : ['sighting'], updated_at: new Date().toISOString() };
      const r = await supabase.from('restock_alerts').upsert(body);
      if (r.error) throw new Error(/restock_alerts|schema cache/i.test(r.error.message) ? 'Restocks need the database update first (supabase/2026-11-27-restocks.sql).' : r.error.message);
      setRow(x => ({ ...x, ...body, fresh: false }));
      haptic('success'); toast(on ? 'Restock alerts on' : 'Restock alerts off'); if (on) onClose();
    } catch (e) { toast(nice(e)); } finally { setBusy(false); }
  };
  return (
    <Sheet open={open} onClose={onClose} title="Restock alerts">
      <T mute size={13}>Get a phone notification when a restock you care about is posted. While this is in testing, alerts can take a few minutes, sometimes longer.</T>
      {ps === 'homescreen' ? <Note title="Open the app from your home screen">On iPhone, notifications only work in the home-screen app: in Safari tap Share → Add to Home Screen, open it from there, then come back.</Note>
        : ps === 'denied' ? <Note tone="warn" title="Notifications are blocked">Allow them for this app in your phone’s Settings → Notifications.</Note>
        : ps === 'unsupported' ? <Note>This browser can’t show notifications.</Note> : null}
      {row ? <>
        <View style={{ gap: 6 }}>
          <T size={12.5} mute>What to tell me about</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{KINDS.filter(([k]) => k !== 'other').map(([k, l]) => <Chip key={k} on={row.kinds.includes(k)} onPress={() => flip('kinds', k)}>{l}</Chip>)}</View>
        </View>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <Field label="Only if the price is at most (A$, optional)" value={max} onChangeText={setMax} keyboardType="decimal-pad" placeholder="e.g. 300" />
        </View>
        <View style={{ gap: 6 }}>
          <T size={12.5} mute>{row.states.length ? 'Only these states (online always included)' : 'Where: all of Australia (tap states to narrow it)'}</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>{STATES.map(s => <Chip key={s} on={row.states.includes(s)} onPress={() => flip('states', s)}>{s}</Chip>)}</View>
        </View>
        <View style={{ gap: 6 }}>
          <T size={12.5} mute>From</T>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {[['sighting', 'Collector sightings'], ['shop', 'Shop posts'], ['bot', 'Our watcher']].map(([k, l]) => <Chip key={k} on={row.sources.includes(k)} onPress={() => flip('sources', k)}>{l}</Chip>)}
          </View>
        </View>
        <Button icon="notifications-outline" disabled={busy || ps === 'unsupported' || ps === 'homescreen' || ps === 'denied'} onPress={() => save(true)}>
          {busy ? 'One moment…' : row.enabled && !row.fresh ? 'Save alerts' : push ? 'Turn on restock alerts' : 'Allow notifications and turn on'}</Button>
        {row.enabled && !row.fresh ? <Button ghost disabled={busy} onPress={() => save(false)}>Turn restock alerts off</Button> : null}
      </> : <T mute>Loading…</T>}
    </Sheet>
  );
}
