import 'react-native-url-polyfill/auto';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { manipulateAsync, SaveFormat } from 'expo-image-manipulator';

const RAW = 'https://raw.githubusercontent.com/leekouris00-maker/onepiece-restock/master/';
const SB_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
const SB_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

export const supabase = SB_URL && SB_KEY
  ? createClient(SB_URL, SB_KEY, { auth: { storage: AsyncStorage, autoRefreshToken: true, persistSession: true, detectSessionInUrl: false } })
  : null;

export const KINDS = [
  ['promo', 'Promos'], ['event', 'Release event cards'], ['booster', 'Booster sets'], ['extra', 'Extra boosters'],
  ['premium', 'Premium boosters'], ['pre-release', 'Pre-release'], ['starter', 'Starter decks'], ['other', 'Deck sets'],
];

export const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
export const today = () => new Date().toISOString().slice(0, 10);
export const clean = n => String(n || '').replace(/\s*\((?:\d{3})\)/, '');
export const tcgImage = (k, size = 200) => (k && k.startsWith('t:') ? `https://tcgplayer-cdn.tcgplayer.com/product/${k.slice(2)}_${size}w.jpg` : null);
export const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

async function loadJSON(name, fresh) {
  const key = 'cache:' + name;
  if (!fresh) {
    const c = await AsyncStorage.getItem(key).catch(() => null);
    if (c) { refreshLater(name); try { return JSON.parse(c); } catch {} }
  }
  try {
    const r = await fetch(RAW + name + '?h=' + Math.floor(Date.now() / 36e5));
    if (!r.ok) throw new Error(String(r.status));
    const txt = await r.text();
    AsyncStorage.setItem(key, txt).catch(() => {});
    return JSON.parse(txt);
  } catch (e) {
    const c = await AsyncStorage.getItem(key).catch(() => null);
    return c ? JSON.parse(c) : null;
  }
}
const pending = {};
function refreshLater(name) {
  if (pending[name]) return;
  pending[name] = fetch(RAW + name + '?h=' + Math.floor(Date.now() / 36e5)).then(r => (r.ok ? r.text() : null))
    .then(t => t && AsyncStorage.setItem('cache:' + name, t)).catch(() => {});
}

// database rows <-> app objects
const fromOwned = r => ({ id: r.id, card: r.card, name: r.name, qty: r.qty, kind: r.kind, cond: r.cond, lang: r.lang, group: r.grp || 'Other', paid: r.paid, value: r.value, notes: r.notes || '', status: r.status, soldFor: r.sold_for, added: r.added, num: r.num, photo: r.photo });
const toOwned = o => ({ id: o.id, card: o.card || null, name: o.name, qty: o.qty || 1, kind: o.kind, cond: o.cond, lang: o.lang || 'EN', grp: o.group || 'Other', paid: o.paid ?? null, value: o.value ?? null, notes: o.notes || '', status: o.status || 'owned', sold_for: o.soldFor ?? null, added: o.added || today(), num: o.num || null, photo: o.photo || null, updated_at: new Date().toISOString() });
const fromCard = r => ({ id: r.id, lang: r.lang, num: r.num, name: r.name, set: r.set_name, rar: r.rar, note: r.note });

const Ctx = createContext(null);
export const useData = () => useContext(Ctx);

export function DataProvider({ children }) {
  const [cat, setCat] = useState(null);
  const [comps, setComps] = useState({});
  const [catError, setCatError] = useState(null);
  const [cur, setCurState] = useState('AUD');
  const [session, setSession] = useState(null);
  const [authReady, setAuthReady] = useState(!supabase);
  const [owned, setOwned] = useState([]);
  const [sales, setSales] = useState([]);
  const [cards, setCards] = useState([]);
  const [watch, setWatch] = useState([]);
  const [photos, setPhotos] = useState({});   // card key -> storage path
  const [urls, setUrls] = useState({});       // storage path -> signed url
  const [busy, setBusy] = useState(false);

  // prices
  const loadCatalog = useCallback(async fresh => {
    const [c, e] = await Promise.all([loadJSON('market_catalog.json', fresh), loadJSON('ebay_comps.json', fresh)]);
    if (!c) { setCatError('Prices could not load. Check your connection and pull down to try again.'); return; }
    setCatError(null);
    const list = c.cards.map(([id, g, num, n, r, t, m, l, h]) => ({ k: 't:' + id, g, num, n, r, t, m, l, h: h || [] }));
    setCat({ meta: c.meta, sets: c.sets, byId: Object.fromEntries(c.sets.map(s => [s.id, s])), list, byKey: Object.fromEntries(list.map(x => [x.k, x])) });
    setComps((e && e.items) || {});
  }, []);
  useEffect(() => { loadCatalog(false); AsyncStorage.getItem('cur').then(v => v && setCurState(v)).catch(() => {}); }, [loadCatalog]);
  const setCur = v => { setCurState(v); AsyncStorage.setItem('cur', v).catch(() => {}); };

  // account
  useEffect(() => {
    if (!supabase) return;
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setAuthReady(true); });
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => sub.subscription.unsubscribe();
  }, []);

  const signUrls = useCallback(async paths => {
    const need = paths.filter(Boolean);
    if (!supabase || !need.length) return;
    const { data } = await supabase.storage.from('photos').createSignedUrls(need, 60 * 60 * 24 * 7);
    if (data) setUrls(u => ({ ...u, ...Object.fromEntries(data.filter(d => d.signedUrl).map(d => [d.path, d.signedUrl])) }));
  }, []);

  const lastLoad = useRef(0);
  const [loadError, setLoadError] = useState('');
  const refresh = useCallback(async () => {
    if (!supabase || !session) return;
    setBusy(true);
    try {
      const [o, s, c, w, p] = await Promise.all([
        supabase.from('owned').select('*'), supabase.from('sales').select('*'), supabase.from('cards').select('*'),
        supabase.from('watch').select('*'), supabase.from('photos').select('*'),
      ]);
      const bad = [o, s, c, w, p].find(r => r.error);
      setLoadError(bad ? bad.error.message : '');
      if (o.error) return;
      const ow = (o.data || []).map(fromOwned);
      setOwned(ow); setSales(s.data || []); setCards((c.data || []).map(fromCard)); setWatch(w.data || []);
      const pm = Object.fromEntries((p.data || []).map(r => [r.card, r.path]));
      setPhotos(pm);
      await signUrls([...Object.values(pm), ...ow.map(x => x.photo)]);
    } catch (e) { setLoadError(e.message || String(e)); } finally { setBusy(false); lastLoad.current = Date.now(); }
  }, [session, signUrls]);
  useEffect(() => { if (session) refresh(); else { setOwned([]); setSales([]); setCards([]); setWatch([]); setPhotos({}); setLoadError(''); } }, [session, refresh]);
  // reload whenever the app comes back to the front (pull-to-refresh doesn't exist in the web version)
  useEffect(() => {
    const sub = AppState.addEventListener('change', st => { if (st === 'active' && Date.now() - lastLoad.current > 5000) refresh(); });
    return () => sub.remove();
  }, [refresh]);

  const need = () => { if (!supabase) throw new Error('Saving is not set up in this build yet.'); if (!session) throw new Error('Sign in first (Account tab).'); };
  const check = r => { if (r.error) throw new Error(r.error.message); return r; };

  const api = {
    async saveOwned(o) { need(); const row = toOwned(o); check(await supabase.from('owned').upsert(row)); setOwned(a => [...a.filter(x => x.id !== o.id), fromOwned(row)]); },
    async removeOwned(id) { need(); check(await supabase.from('owned').delete().eq('id', id)); setOwned(a => a.filter(x => x.id !== id)); },
    async addSale(s) { need(); const row = { id: newId(), ...s }; check(await supabase.from('sales').insert(row)); setSales(a => [...a, row]); },
    async removeSale(id) { need(); check(await supabase.from('sales').delete().eq('id', id)); setSales(a => a.filter(x => x.id !== id)); },
    async addCard(c) { need(); const row = { id: newId(), lang: c.lang, num: c.num, name: c.name, set_name: c.set, rar: c.rar, note: c.note }; check(await supabase.from('cards').insert(row)); const card = fromCard(row); setCards(a => [...a, card]); return card; },
    async removeCard(id) { need(); check(await supabase.from('cards').delete().eq('id', id)); setCards(a => a.filter(x => x.id !== id)); },
    async setTrack(card, w) { need(); const row = { card, q: w.q, lang: w.lang || null, graded: w.graded ?? null, updated_at: new Date().toISOString() }; check(await supabase.from('watch').upsert(row, { onConflict: 'user_id,card' })); setWatch(a => [...a.filter(x => x.card !== card), row]); },
    async untrack(card) { need(); check(await supabase.from('watch').delete().eq('card', card)); setWatch(a => a.filter(x => x.card !== card)); },
    async addPhoto(target, uri) {
      need();
      const small = await manipulateAsync(uri, [{ resize: { width: 1200 } }], { compress: 0.85, format: SaveFormat.JPEG });
      const body = await (await fetch(small.uri)).arrayBuffer();
      const path = `${session.user.id}/${newId()}.jpg`;
      check(await supabase.storage.from('photos').upload(path, body, { contentType: 'image/jpeg', upsert: false }));
      if (target.card) {
        check(await supabase.from('photos').upsert({ card: target.card, path, updated_at: new Date().toISOString() }, { onConflict: 'user_id,card' }));
        setPhotos(p => ({ ...p, [target.card]: path }));
      } else {
        const o = owned.find(x => x.id === target.owned);
        if (o) await api.saveOwned({ ...o, photo: path });
      }
      await signUrls([path]);
    },
  };

  // lookups
  const custom = useMemo(() => cards.map(c => ({ k: 'u:' + c.id, id: c.id, g: 'mine:' + (c.set || 'Other'), num: c.num || '', n: c.name || '', r: c.rar || '', t: 'card', m: null, l: null, h: [], lang: c.lang, note: c.note, mine: true, setName: c.set })), [cards]);
  const card = k => (k && k.startsWith('u:') ? custom.find(c => c.k === k) : cat?.byKey[k]) || null;
  const fx = cat?.meta?.fx || 1.5;
  const watchOf = k => watch.find(w => w.card === k) || null;
  const compOf = k => { const w = watchOf(k), c = comps[k]; return w && c && !c.none && c.median != null ? c : null; };
  const salesOf = k => sales.filter(s => s.card === k).sort((a, b) => String(b.date).localeCompare(String(a.date)));
  const toUsd = (p, c) => (c === 'USD' ? Number(p) : Number(p) / fx);
  const photoOf = k => { const p = photos[k]; return p ? urls[p] || null : null; };
  const ownPhoto = o => (o.card && photoOf(o.card)) || (o.photo ? urls[o.photo] || null : null);
  const ownVal = o => {
    if (o.value != null && o.value !== '') return { a: Number(o.value), src: 'your estimate' };
    const c = card(o.card); if (!c) return { a: null, src: 'no price yet' };
    const cp = compOf(c.k); if (cp) return { a: cp.median * fx, src: 'eBay median' };
    const raw = salesOf(c.k).filter(s => (s.grade || 'Raw') === 'Raw').map(s => toUsd(s.price, s.cur));
    if (raw.length) return { a: median(raw) * fx, src: 'your logged sales' };
    if (c.m != null) return { a: c.m * fx, src: 'TCGplayer' };
    return { a: null, src: 'no price yet' };
  };
  const money = usd => {
    if (usd == null || isNaN(usd)) return '–';
    const v = cur === 'AUD' ? usd * fx : usd, d = Math.abs(v) >= 1000 ? 0 : 2;
    return (cur === 'AUD' ? 'A$' : 'US$') + v.toLocaleString('en-AU', { minimumFractionDigits: d, maximumFractionDigits: d });
  };
  const aud = a => (a == null ? '–' : money(a / fx));
  const move = c => { let o = null; for (const [ago, p] of c.h) if (ago >= 7) o = p; return o && c.m != null ? ((c.m - o) / o) * 100 : null; };
  // TCGplayer price a given number of days ago (the last change on or before that day)
  const priceAt = (c, a) => { if (!c || a <= 0 || !c.h.length) return c?.m ?? null; let v = null; for (const [ago, p] of c.h) if (ago >= a) v = p; return v ?? c.h[0][1] ?? c.m; };
  // one item's A$ value each, a given number of days ago
  const unitAt = (o, a) => {
    const now = ownVal(o); if (!a || now.src !== 'TCGplayer') return now.a;
    const p = priceAt(card(o.card), a); return p == null ? now.a : p * fx;
  };
  // total collection value (A$) for each of the last `days` days, oldest first
  const series = days => {
    const live = owned.filter(o => o.status !== 'sold'), out = [];
    for (let a = days; a >= 0; a--) out.push(live.reduce((n, o) => n + (unitAt(o, a) || 0) * (Number(o.qty) || 1), 0));
    return out;
  };

  const value = {
    cat, catError, comps, loadCatalog, cur, setCur, session, authReady, configured: !!supabase, busy, refresh, loadError,
    owned, sales, cards, watch, custom, card, fx, watchOf, compOf, salesOf, toUsd, photoOf, ownPhoto, ownVal, money, aud, move, priceAt, unitAt, series, ...api,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
