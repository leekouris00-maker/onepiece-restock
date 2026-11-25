import 'react-native-url-polyfill/auto';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { createClient } from '@supabase/supabase-js';
import { manipulateAsync, SaveFormat } from 'expo-image-manipulator';
import { buildIndex } from './find';

const RAW = 'https://raw.githubusercontent.com/leekouris00-maker/onepiece-restock/master/';
const SB_URL = process.env.EXPO_PUBLIC_SUPABASE_URL;
const SB_KEY = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY;

export const RAW_BASE = RAW;
export const supabase = SB_URL && SB_KEY
  ? createClient(SB_URL, SB_KEY, { auth: { storage: AsyncStorage, autoRefreshToken: true, persistSession: true, detectSessionInUrl: false } })
  : null;

export const KINDS = [
  ['promo', 'Promos'], ['event', 'Release event cards'], ['booster', 'Booster sets'], ['extra', 'Extra boosters'],
  ['premium', 'Premium boosters'], ['pre-release', 'Pre-release'], ['starter', 'Starter decks'], ['other', 'Deck sets'],
];

// Count one use of a key feature for the owner's stats page (see supabase/2026-11-25-rewards.sql).
// Only for signed-in people; only the names the database accepts; the same name at most every 15 s; errors ignored.
const lastTrack = {};
export function track(what) {
  if (!supabase) return;
  const now = Date.now();
  if (lastTrack[what] && now - lastTrack[what] < 15000) return;
  lastTrack[what] = now;
  supabase.auth.getSession().then(({ data }) => { if (data && data.session) supabase.rpc('track', { what }).then(() => {}, () => {}); }).catch(() => {});
}
export function useTrack(what) { useEffect(() => { track(what); }, []); }

export const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
export const today = () => new Date().toISOString().slice(0, 10);
export const clean = n => String(n || '').replace(/\s*\((?:\d{3})\)/, '');
export const tcgImage = (k, size = 200) => (k && k.startsWith('t:') ? `https://tcgplayer-cdn.tcgplayer.com/product/${k.slice(2)}_${size}w.jpg` : null);
export const median = a => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

// Prices: the saved copy shows at once (and offline); a fresh copy is fetched behind it.
// Returns [data, failed] where failed = the network fetch didn't work and the saved copy was used.
async function loadJSON(name, fresh) {
  const key = 'cache:' + name;
  if (!fresh) {
    const c = await AsyncStorage.getItem(key).catch(() => null);
    if (c) { refreshLater(name); try { return [JSON.parse(c), false]; } catch {} }
  }
  try {
    const r = await fetch(RAW + name + '?h=' + Math.floor(Date.now() / 36e5));
    if (!r.ok) throw new Error(String(r.status));
    const txt = await r.text();
    AsyncStorage.setItem(key, txt).catch(() => {});
    return [JSON.parse(txt), false];
  } catch (e) {
    const c = await AsyncStorage.getItem(key).catch(() => null);
    return [c ? JSON.parse(c) : null, true];
  }
}
const pending = {};
let onFresh = null;                       // set by the provider: swap in newer prices when they arrive
function refreshLater(name) {
  if (pending[name]) return;
  pending[name] = fetch(RAW + name + '?h=' + Math.floor(Date.now() / 36e5)).then(r => (r.ok ? r.text() : null))
    .then(t => { if (t) { AsyncStorage.setItem('cache:' + name, t); onFresh && onFresh(name, t); } }).catch(() => {});
}

const isOnline = () => (typeof navigator === 'undefined' || navigator.onLine !== false);

// database rows <-> app objects
// Columns added by later database updates: only sent once the database has them (supabase/2026-11-24.sql)
export const cols = { soldAt: false, notified: false, deal: false };
const fromOwned = r => ({ id: r.id, card: r.card, name: r.name, qty: r.qty, kind: r.kind, cond: r.cond, lang: r.lang, group: r.grp || 'Other', paid: r.paid, value: r.value, notes: r.notes || '', status: r.status, soldFor: r.sold_for, added: r.added, num: r.num, photo: r.photo,
  soldAt: r.sold_at || null, updated: r.updated_at ? String(r.updated_at).slice(0, 10) : null });
const toOwned = o => {
  const row = { id: o.id, card: o.card || null, name: o.name, qty: o.qty || 1, kind: o.kind, cond: o.cond, lang: o.lang || 'EN', grp: o.group || 'Other', paid: o.paid ?? null, value: o.value ?? null, notes: o.notes || '', status: o.status || 'owned', sold_for: o.soldFor ?? null, added: o.added || today(), num: o.num || null, photo: o.photo || null, updated_at: new Date().toISOString() };
  // the day it was sold: kept when it has one, today when it's newly marked sold
  if (cols.soldAt) row.sold_at = row.status === 'sold' ? o.soldAt || today() : null;
  return row;
};
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
  const [stale, setStale] = useState(false);        // prices came from the saved copy because the update failed
  const [offline, setOffline] = useState(!isOnline());
  const [cachedAt, setCachedAt] = useState(null);   // your collection is the saved copy from this time
  const [favs, setFavs] = useState([]);             // watchlist: { card, below, above, created_at }
  const [favLocal, setFavLocal] = useState(false);  // watchlist table not in the database yet: kept on this device

  // prices
  const applyCat = useCallback(c => {
    const list = c.cards.map(([id, g, num, n, r, t, m, l, h]) => ({ k: 't:' + id, g, num, n, r, t, m, l, h: h || [] }));
    setCat({ meta: c.meta, sets: c.sets, byId: Object.fromEntries(c.sets.map(s => [s.id, s])), list, byKey: Object.fromEntries(list.map(x => [x.k, x])) });
  }, []);
  const loadCatalog = useCallback(async fresh => {
    const [[c, f1], [e, f2]] = await Promise.all([loadJSON('market_catalog.json', fresh), loadJSON('ebay_comps.json', fresh)]);
    setStale(f1 || f2);
    if (!c) { setCatError('Prices could not load. Check your connection and pull down to try again.'); return; }
    setCatError(null);
    applyCat(c);
    setComps((e && e.items) || {});
  }, [applyCat]);
  useEffect(() => {
    onFresh = (name, t) => { try { const j = JSON.parse(t); if (name === 'market_catalog.json') applyCat(j); else setComps(j.items || {}); setStale(false); } catch {} };
    return () => { onFresh = null; };
  }, [applyCat]);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.addEventListener) return undefined;
    const on = () => { setOffline(false); loadCatalog(true); }, off = () => setOffline(true);
    window.addEventListener('online', on); window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, [loadCatalog]);
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
  const [loaded, setLoaded] = useState(false);        // first load of this account done (saved copy or fresh)
  const uid = session?.user?.id;
  const cacheKey = uid ? 'mine:' + uid : null;
  const loadFavs = useCallback(async () => {
    const local = async () => { setFavLocal(true); try { setFavs(JSON.parse(await AsyncStorage.getItem('favs:' + (uid || 'guest')) || '[]')); } catch { setFavs([]); } };
    if (!supabase || !session) return local();
    const r = await supabase.from('watchlist').select('*');
    if (r.error) return local();                       // table not created yet (run supabase/watchlist.sql)
    if (r.data && r.data[0]) { cols.notified = 'notified' in r.data[0]; cols.deal = 'deal_below' in r.data[0]; }
    else if (!r.error) { const t = await supabase.from('watchlist').select('deal_below').limit(1); cols.deal = !t.error; const t2 = await supabase.from('watchlist').select('notified').limit(1); cols.notified = !t2.error; }
    setFavLocal(false); setFavs(r.data || []);
  }, [session, uid]);
  const refresh = useCallback(async () => {
    if (!supabase || !session) return;
    setBusy(true);
    try {
      if (!isOnline()) throw new Error('offline');
      const [o, s, c, w, p] = await Promise.all([
        supabase.from('owned').select('*'), supabase.from('sales').select('*'), supabase.from('cards').select('*'),
        supabase.from('watch').select('*'), supabase.from('photos').select('*'),
      ]);
      const bad = [o, s, c, w, p].find(r => r.error);
      setLoadError(bad ? bad.error.message : '');
      if (o.error) return;
      if (o.data && o.data[0]) cols.soldAt = 'sold_at' in o.data[0];
      const ow = (o.data || []).map(fromOwned);
      setOwned(ow); setSales(s.data || []); setCards((c.data || []).map(fromCard)); setWatch(w.data || []);
      const pm = Object.fromEntries((p.data || []).map(r => [r.card, r.path]));
      setPhotos(pm); setCachedAt(null); setLoaded(true);
      AsyncStorage.setItem(cacheKey, JSON.stringify({ at: new Date().toISOString(), o: o.data || [], s: s.data || [], c: c.data || [], w: w.data || [], p: p.data || [] })).catch(() => {});
      await signUrls([...Object.values(pm), ...ow.map(x => x.photo)]);
      loadFavs();
    } catch (e) {
      const msg = e.message || String(e);
      if (msg === 'offline' || /fetch|network/i.test(msg)) { setOffline(!isOnline() || offline); setLoadError(''); }
      else setLoadError(msg);
    } finally { setBusy(false); lastLoad.current = Date.now(); }
  }, [session, signUrls, cacheKey, loadFavs]);
  // the saved copy first, so the collection shows instantly and works without signal
  useEffect(() => {
    if (!cacheKey) return;
    AsyncStorage.getItem(cacheKey).then(t => {
      if (!t) return;
      const m = JSON.parse(t);
      setOwned(cur => (cur.length ? cur : (m.o || []).map(fromOwned)));
      setSales(cur => (cur.length ? cur : m.s || [])); setCards(cur => (cur.length ? cur : (m.c || []).map(fromCard)));
      setWatch(cur => (cur.length ? cur : m.w || [])); setPhotos(cur => (Object.keys(cur).length ? cur : Object.fromEntries((m.p || []).map(r => [r.card, r.path]))));
      setCachedAt(m.at); setLoaded(true);
    }).catch(() => {});
  }, [cacheKey]);
  useEffect(() => { if (session) track('open'); }, [session]);
  useEffect(() => { if (session) refresh(); else { setOwned([]); setSales([]); setCards([]); setWatch([]); setPhotos({}); setLoadError(''); setLoaded(false); loadFavs(); } }, [session, refresh]);
  // reload whenever the app comes back to the front (pull-to-refresh doesn't exist in the web version)
  useEffect(() => {
    const sub = AppState.addEventListener('change', st => { if (st === 'active') track('open'); if (st === 'active' && Date.now() - lastLoad.current > 5000) refresh(); });
    return () => sub.remove();
  }, [refresh]);

  const need = () => {
    if (!supabase) throw new Error('Saving is not set up in this build yet.');
    if (!session) throw new Error('Sign in first (Profile tab).');
    if (!isOnline()) throw new Error('You’re offline. Changes can be saved once you have signal again.');
  };
  const saveCache = (o) => cacheKey && AsyncStorage.getItem(cacheKey).then(t => { const m = t ? JSON.parse(t) : {}; m.o = o.map(toOwned); return AsyncStorage.setItem(cacheKey, JSON.stringify(m)); }).catch(() => {});
  useEffect(() => { if (loaded && cacheKey && !busy) saveCache(owned); }, [owned]);
  const check = r => { if (r.error) throw new Error(r.error.message); return r; };

  const api = {
    async saveOwned(o) { need(); const row = toOwned(o); const isNew = !owned.some(x => x.id === o.id); check(await supabase.from('owned').upsert(row)); if (isNew) track('card_add'); setOwned(a => [...a.filter(x => x.id !== o.id), fromOwned(row)]); },
    // several at once (bulk edits, scanned stacks, imports): one request
    async saveMany(list) {
      need(); if (!list.length) return;
      const rows = list.map(toOwned);
      for (let i = 0; i < rows.length; i += 200) check(await supabase.from('owned').upsert(rows.slice(i, i + 200)));
      if (rows.some(r => !owned.some(x => x.id === r.id))) track('card_add');
      const ids = new Set(rows.map(r => r.id));
      setOwned(a => [...a.filter(x => !ids.has(x.id)), ...rows.map(fromOwned)]);
    },
    async removeOwned(id) { need(); check(await supabase.from('owned').delete().eq('id', id)); setOwned(a => a.filter(x => x.id !== id)); },
    async removeMany(ids) { need(); if (!ids.length) return; check(await supabase.from('owned').delete().in('id', ids)); const s = new Set(ids); setOwned(a => a.filter(x => !s.has(x.id))); },
    // watchlist + price alerts (A$). Kept in the database when supabase/watchlist.sql has been run, else on this device.
    async setFav(card, f) {
      // fields left out keep their current value; pass null to clear one
      const old = favs.find(x => x.card === card) || {};
      const pick = k => (f && k in f ? f[k] : old[k] ?? null);
      const row = { card, below: pick('below'), above: pick('above'), created_at: old.created_at || new Date().toISOString() };
      if (cols.deal) row.deal_below = pick('deal_below');
      if (cols.notified) { row.notified = null; row.notified_at = null; }   // a new price = a new alert
      const next = [...favs.filter(x => x.card !== card), row];
      if (!favLocal && supabase && session) { need(); check(await supabase.from('watchlist').upsert(row, { onConflict: 'user_id,card' })); if (row.below != null || row.above != null) track('alert_set'); }
      else await AsyncStorage.setItem('favs:' + (uid || 'guest'), JSON.stringify(next));
      setFavs(next);
    },
    async unFav(card) {
      const next = favs.filter(x => x.card !== card);
      if (!favLocal && supabase && session) { need(); check(await supabase.from('watchlist').delete().eq('card', card)); }
      else await AsyncStorage.setItem('favs:' + (uid || 'guest'), JSON.stringify(next));
      setFavs(next);
    },
    async addSale(s) { need(); const row = { id: newId(), ...s }; check(await supabase.from('sales').insert(row)); setSales(a => [...a, row]); },
    async removeSale(id) { need(); check(await supabase.from('sales').delete().eq('id', id)); setSales(a => a.filter(x => x.id !== id)); },
    async addCard(c) { need(); const row = { id: newId(), lang: c.lang, num: c.num, name: c.name, set_name: c.set, rar: c.rar, note: c.note }; check(await supabase.from('cards').insert(row)); const card = fromCard(row); setCards(a => [...a, card]); return card; },
    async removeCard(id) { need(); check(await supabase.from('cards').delete().eq('id', id)); setCards(a => a.filter(x => x.id !== id)); },
    async setTrack(card, w) { need(); const row = { card, q: w.q, lang: w.lang || null, graded: w.graded ?? null, updated_at: new Date().toISOString() }; check(await supabase.from('watch').upsert(row, { onConflict: 'user_id,card' })); setWatch(a => [...a.filter(x => x.card !== card), row]); },
    // Delete the account: photo files first (only the app can remove those), then the login, which takes
    // every row with it (cascade). Needs supabase/delete-account.sql to have been run once.
    async deleteAccount() {
      need();
      const uid = session.user.id;
      for (;;) {
        const { data, error } = await supabase.storage.from('photos').list(uid, { limit: 100 });
        if (error || !data || !data.length) break;
        const { error: e2 } = await supabase.storage.from('photos').remove(data.map(f => `${uid}/${f.name}`));
        if (e2) throw new Error('Could not delete your photos: ' + e2.message);
        if (data.length < 100) break;
      }
      const r = await supabase.rpc('delete_my_account');
      if (r.error) {
        if (/delete_my_account|function|schema cache/i.test(r.error.message)) throw new Error('Account deletion isn\'t switched on in the database yet (run supabase/delete-account.sql once).');
        throw new Error(r.error.message);
      }
      await supabase.auth.signOut({ scope: 'local' }).catch(() => {});
      for (const k of ['owned', 'sales', 'cards', 'watch', 'photos', 'mine:' + uid, 'favs:' + uid]) await AsyncStorage.removeItem(k).catch(() => {});
      setOwned([]); setSales([]); setCards([]); setWatch([]); setPhotos({});
    },
    // Tester feedback: anyone can send; a picture only when signed in (it goes in your photo folder)
    async sendFeedback({ note, page, uri, device }) {
      if (!supabase) throw new Error('Feedback isn’t set up in this build.');
      if (!isOnline()) throw new Error('You’re offline. Try again when you have signal.');
      let photo = null;
      if (uri && session) {
        const small = await manipulateAsync(uri, [{ resize: { width: 1000 } }], { compress: 0.8, format: SaveFormat.JPEG });
        const body = await (await fetch(small.uri)).arrayBuffer();
        photo = `${session.user.id}/feedback-${newId()}.jpg`;
        const up = await supabase.storage.from('photos').upload(photo, body, { contentType: 'image/jpeg' });
        if (up.error) photo = null;
      }
      const r = await supabase.from('feedback').insert({ note, page, device, photo, email: session?.user?.email || null, user_id: session?.user?.id || null });
      if (r.error) {
        if (/feedback|schema cache|relation/i.test(r.error.message)) throw new Error('NOT_SET_UP');
        throw new Error(r.error.message);
      }
    },
    // Read-only links to one group of your collection
    async listShares() { if (!supabase || !session) return []; const r = await supabase.from('shares').select('*'); if (r.error) throw new Error(/shares|schema cache/i.test(r.error.message) ? 'NOT_SET_UP' : r.error.message); return r.data || []; },
    async createShare(grp, title) {
      need();
      const id = Array.from({ length: 10 }, () => 'abcdefghijkmnpqrstuvwxyz23456789'[Math.floor(Math.random() * 32)]).join('');
      const r = await supabase.from('shares').insert({ id, grp, title: title || grp });
      if (r.error) throw new Error(/shares|schema cache/i.test(r.error.message) ? 'NOT_SET_UP' : r.error.message);
      return id;
    },
    async removeShare(id) { need(); check(await supabase.from('shares').delete().eq('id', id)); },
    // Phone notifications
    async savePushSub(sub, device) { need(); const j = sub.toJSON ? sub.toJSON() : sub; const r = await supabase.from('push_subs').upsert({ endpoint: j.endpoint, sub: j, device }); if (r.error) throw new Error(/push_subs|schema cache/i.test(r.error.message) ? 'NOT_SET_UP' : r.error.message); },
    async listDeals() { if (!supabase || !session) return []; const r = await supabase.from('deals').select('*').order('found_at', { ascending: false }).limit(100); if (r.error) throw new Error(/deals|schema cache/i.test(r.error.message) ? 'NOT_SET_UP' : r.error.message); return r.data || []; },
    async dismissDeal(item) { need(); check(await supabase.from('deals').delete().eq('item_id', item)); },
    async removePushSub(endpoint) { if (supabase && session) await supabase.from('push_subs').delete().eq('endpoint', endpoint); },
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
  // card number -> every version (TCGplayer + your own cards), and the search index
  const byNum = useMemo(() => {
    const m = new Map();
    for (const x of [...(cat?.list || []), ...custom]) { const n = String(x.num || '').toUpperCase(); if (n) (m.get(n) || m.set(n, []).get(n)).push(x); }
    return m;
  }, [cat, custom]);
  const index = useMemo(() => (cat ? buildIndex([...custom, ...cat.list], cat) : []), [cat, custom]);
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
    // TCGplayer only prices English cards; a Japanese copy uses Japanese-only eBay prices when the card is tracked that way
    const jp = (o.lang || 'EN') !== 'EN' && !c.mine, w = watchOf(c.k), jpSearch = w?.lang === 'ja';
    const cp = compOf(c.k); if (cp && jp === jpSearch) return { a: cp.median * fx, src: jp ? 'eBay median, Japanese' : 'eBay median' };
    const raw = salesOf(c.k).filter(s => (s.grade || 'Raw') === 'Raw').map(s => toUsd(s.price, s.cur));
    if (raw.length) return { a: median(raw) * fx, src: 'your logged sales' };
    if (c.m != null) return { a: c.m * fx, src: jp ? 'TCGplayer English price, no Japanese price yet' : 'TCGplayer' };
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
    const now = ownVal(o); if (!a || !now.src.startsWith('TCGplayer')) return now.a;
    const p = priceAt(card(o.card), a); return p == null ? now.a : p * fx;
  };
  // total collection value (A$) for each of the last `days` days, oldest first
  const series = days => {
    const live = owned.filter(o => o.status !== 'sold'), out = [];
    for (let a = days; a >= 0; a--) out.push(live.reduce((n, o) => n + (unitAt(o, a) || 0) * (Number(o.qty) || 1), 0));
    return out;
  };

  // Best price to compare against for a card (US$): eBay sold median when there are sales, else TCGplayer market
  const refPrice = c => {
    if (!c) return { usd: null, src: '', n: null };
    const e = comps[c.k];
    // an eBay median 4× away from TCGplayer is nearly always a search catching another version: don't trust it
    const off = e && e.median != null && c.m != null && c.m >= 3 && (e.median < c.m / 4 || e.median > c.m * 4);
    if (e && !e.none && e.median != null && e.count >= 3 && !off) return { usd: e.median, src: 'eBay sold median', n: e.count };
    if (c.m != null) return { usd: c.m, src: 'TCGplayer market', n: null };
    if (e && !e.none && e.median != null && !off) return { usd: e.median, src: 'eBay sold median', n: e.count };
    return { usd: null, src: '', n: null };
  };
  // How many sales an owned item's value rests on (null = not from sales)
  const valCount = o => {
    const v = ownVal(o); const c = card(o.card);
    if (!c) return null;
    if (v.src.startsWith('eBay')) return comps[c.k]?.count ?? null;
    if (v.src === 'your logged sales') return salesOf(c.k).filter(s => (s.grade || 'Raw') === 'Raw').length;
    return null;
  };
  const isFav = k => favs.some(f => f.card === k);
  // Watchlist cards whose price crossed an alert you set
  const alerts = useMemo(() => favs.map(f => {
    const c = card(f.card); const p = refPrice(c).usd; if (p == null) return null;
    const a = p * fx;
    if (f.below != null && a <= Number(f.below)) return { f, c, a, dir: 'below', at: Number(f.below) };
    if (f.above != null && a >= Number(f.above)) return { f, c, a, dir: 'above', at: Number(f.above) };
    return null;
  }).filter(Boolean), [favs, cat, comps, cards, fx]);

  const value = {
    cat, catError, comps, loadCatalog, cur, setCur, session, authReady, configured: !!supabase, busy, refresh, loadError, loaded,
    stale, offline, cachedAt, byNum, index, favs, favLocal, isFav, alerts, refPrice, valCount,
    owned, sales, cards, watch, custom, card, fx, watchOf, compOf, salesOf, toUsd, photoOf, ownPhoto, ownVal, money, aud, move, priceAt, unitAt, series, ...api,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
