// Rewards points.
// Signed in: saved to your account in the database (supabase/2026-11-25-rewards.sql). The database does the
// counting and checks the rules: one check-in per Melbourne day, milestones really done, enough points to swap.
// Until that SQL has been run, points fall back to this device (the old preview) so nothing breaks.
// No chance anywhere: every reward is fixed and known in advance. Points are only ever earned (never bought,
// sold or transferred), have no cash value, and paid members earn exactly the same as everyone else.
import { useCallback, useEffect, useState } from 'react';
import { supabase, useData } from './data';
import { usePref } from './prefs';

export const POINT_AUD = 0.01;          // 100 points = A$1 of shop value
export const CHECKIN = 10;              // one check-in a day
export const WEEK_BONUS = 50;           // every 7th day in a row
export const MONTH_BONUS = 250;         // day 30 in a row (instead of the 7-day bonus that day)

// One-off rewards. Each pays once per account, ever (the database checks they're really done).
export const MILESTONES = [
  { id: 'card1', label: 'Add your first card', sub: 'Anything in your collection', pts: 50, icon: 'add-circle-outline', go: '/search', done: s => s.items >= 1 },
  { id: 'card10', label: '10 things in your collection', sub: 'Cards, sealed, anything', pts: 100, icon: 'albums-outline', go: '/search', done: s => s.items >= 10 },
  { id: 'card50', label: '50 things in your collection', sub: 'A proper collection', pts: 200, icon: 'library-outline', go: '/search', done: s => s.items >= 50 },
  { id: 'scan', label: 'Scan a card with the camera', sub: 'Scan one and add it', pts: 50, icon: 'scan-outline', go: '/scan', done: s => s.scanned },
  { id: 'alert', label: 'Set a price alert', sub: 'On any card you watch', pts: 25, icon: 'notifications-outline', go: '/watchlist', done: s => s.alert },
  { id: 'import', label: 'Import your collection', sub: 'From Collectr or a spreadsheet', pts: 100, icon: 'cloud-upload-outline', go: '/import', done: s => s.imported },
];
export const MILESTONE_TOTAL = MILESTONES.reduce((s, m) => s + m.pts, 0);

// The shop: fixed points prices (100 points = A$1). The database has the same list (shop_items) and charges from it.
export const SHOP = [
  { id: 'c5', label: 'A$5 store credit', sub: 'Off anything in the store', icon: 'pricetag-outline', cost: 500, aud: 5 },
  { id: 'pack', label: 'OP-18 booster pack', sub: 'Sealed, shipped free', k: 't:712904', cost: 900, aud: 9 },
  { id: 'c10', label: 'A$10 store credit', sub: 'Off anything in the store', icon: 'pricetag-outline', cost: 1000, aud: 10 },
  { id: 'single20', label: 'Any single up to A$20', sub: 'You choose the card', icon: 'albums-outline', cost: 2000, aud: 20 },
  { id: 'c25', label: 'A$25 store credit', sub: 'Off anything in the store', icon: 'pricetag-outline', cost: 2500, aud: 25 },
  { id: 'single50', label: 'Any single up to A$50', sub: 'You choose the card', icon: 'albums-outline', cost: 5000, aud: 50 },
  { id: 'box', label: 'OP-18 booster box', sub: 'Sealed, shipped free', k: 't:712901', cost: 28000, aud: 280 },
];
export const PRICES_SET = 'November 2026';

// Swaps open once an account is 30 days old (earning starts straight away). The database checks this too;
// the app's owner is exempt there so swaps can be tested.
export const SWAP_WAIT_DAYS = 30;
export function swapOpens(session) {
  const t = session?.user?.created_at ? new Date(session.user.created_at).getTime() : null;
  if (!t) return null;
  const at = new Date(t + SWAP_WAIT_DAYS * 86400000);
  return at > new Date() ? at : null;
}
export const niceDay = t => t.toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });

// ---------- bounties (27 Nov 2026) ----------
// Your bounty is every point you've ever earned plus set-completion bounty. Spending never lowers it.
// Shown in berries: 1 point = ฿1,000,000.
export const BERRIES = 1000000;
export const RANKS = [
  { id: 'rookie', label: 'Rookie', at: 0, icon: 'boat-outline' },
  { id: 'supernova', label: 'Supernova', at: 500, icon: 'flash-outline' },
  { id: 'warlord', label: 'Warlord', at: 2000, icon: 'shield-half-outline' },
  { id: 'emperor', label: 'Emperor', at: 5000, icon: 'diamond-outline' },
  { id: 'king', label: 'Pirate King', at: 10000, icon: 'trophy-outline' },
];
export function rankOf(b) {
  let i = 0;
  while (i + 1 < RANKS.length && b >= RANKS[i + 1].at) i++;
  const r = RANKS[i], next = RANKS[i + 1] || null;
  return { ...r, i, next, toNext: next ? next.at - b : 0, frac: next ? (b - r.at) / (next.at - r.at) : 1 };
}
// ฿1,250,000,000 (full) or ฿1.25B (short)
export function berries(b, short) {
  const v = Math.max(0, Math.round(b || 0)) * BERRIES;
  if (!short) return '฿' + v.toLocaleString('en-AU');
  const f = (x, u) => '฿' + (x >= 100 ? Math.round(x) : x >= 10 ? x.toFixed(1).replace(/\.0$/, '') : x.toFixed(2).replace(/\.?0+$/, '')) + u;
  return v >= 1e9 ? f(v / 1e9, 'B') : v >= 1e6 ? f(v / 1e6, 'M') : '฿' + v.toLocaleString('en-AU');
}

// Weekly bounties: the database picks 3 a week (Monday, Melbourne time) and checks they're done.
export const QUEST_PTS = 20, QUEST_ALL = 40;
export const QUESTS = {
  movers: { icon: 'trending-up', go: '/movers', sub: 'Biggest moves up and down' },
  add3: { icon: 'add-circle-outline', go: '/search', sub: 'Cards, sealed, anything' },
  alert: { icon: 'notifications-outline', go: '/watchlist', sub: 'On any card you watch' },
  binder: { icon: 'book-outline', go: '/binders', sub: 'Make one or change one' },
  scan: { icon: 'scan-outline', go: '/scan', sub: 'Scan one and add it' },
  meta: { icon: 'shield-checkmark-outline', go: { pathname: '/market', params: { tab: 'meta' } }, sub: 'Bans and what’s winning' },
  promos: { icon: 'gift-outline', go: { pathname: '/market', params: { tab: 'promos' } }, sub: 'Events and promo cards' },
  checkin5: { icon: 'calendar-outline', go: '/rewards', sub: 'Your Morning Log, 5 days' },
  search3: { icon: 'search', go: '/search', sub: 'Any 3 cards' },
  sets: { icon: 'albums-outline', go: '/sets', sub: 'Any set' },
};
// Monday that starts this week (Melbourne)
export function weekEnds() {
  const t = new Date(new Date().toLocaleString('en-US', { timeZone: 'Australia/Melbourne' }));
  const left = (8 - (t.getDay() || 7)) % 7 || 7;      // days until next Monday
  return left === 1 ? 'Resets tonight at midnight' : `Resets in ${left} days (Monday)`;
}

// Set completion: bounty only (no spendable points), at 25 / 50 / 75 / 100% of a set's card numbers.
export const SET_STEPS = [[25, 25], [50, 50], [75, 100], [100, 250]];
// every main set (booster / extra / starter) with its card-number prefix and size, and how many numbers you own
export function setProgress(d) {
  if (!d.cat) return [];
  const byPre = new Map();
  const kinds = new Set(['booster', 'extra', 'starter']);
  const groups = new Map();
  for (const x of d.cat.list) if (x.t === 'card' && x.num) (groups.get(x.g) || groups.set(x.g, []).get(x.g)).push(x);
  for (const s of d.cat.sets) {
    if (!kinds.has(s.kind)) continue;
    const cards = groups.get(s.id) || [];
    const count = new Map();
    for (const x of cards) { const p = x.num.split('-')[0].toUpperCase(); count.set(p, (count.get(p) || 0) + 1); }
    const pre = [...count.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    if (!pre || !/^[A-Z]{2,4}\d{2}$/.test(pre)) continue;
    const size = new Set(cards.filter(x => x.num.toUpperCase().startsWith(pre + '-')).map(x => x.num.toUpperCase())).size;
    if (size < 10 || size > 400) continue;
    const had = byPre.get(pre);
    if (!had || size > had.size) byPre.set(pre, { code: pre, size, name: s.name.replace(/^ST-\d+:\s*/, ''), set: s.id });
  }
  const mine = new Map();
  for (const o of d.owned || []) {
    if (o.status === 'sold' || !o.num) continue;
    const n = String(o.num).toUpperCase(), p = n.split('-')[0];
    if (byPre.has(p)) (mine.get(p) || mine.set(p, new Set()).get(p)).add(n);
  }
  return [...byPre.values()].map(x => ({ ...x, have: mine.get(x.code)?.size || 0 })).map(x => ({ ...x, pct: x.have / x.size }));
}
export const stepsReady = (x, got) => SET_STEPS.filter(([p]) => x.have >= Math.ceil((x.size * p) / 100) && !got.has(`set:${x.code}:${p}`));

export const dayKey = (t = new Date()) => `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
const back = (t, n = 1) => { const x = new Date(t); x.setDate(x.getDate() - n); return x; };

// Days checked in a row, ending today (or yesterday if not checked in yet today). One missed day a calendar
// month is covered automatically (a "streak freeze") and doesn't add to the count. Same rule as the database.
export function streakInfo(days) {
  const set = new Set(days || []);
  let t = new Date();
  if (!set.has(dayKey(t))) t = back(t);
  let n = 0;
  const frozen = new Set();
  for (;;) {
    if (set.has(dayKey(t))) { n++; t = back(t); continue; }
    const month = dayKey(t).slice(0, 7);
    if (!frozen.has(month) && set.has(dayKey(back(t)))) { frozen.add(month); t = back(t); continue; }
    break;
  }
  return { n, freezeLeft: !frozen.has(dayKey().slice(0, 7)) };
}
export const bonusFor = n => (n === 30 ? MONTH_BONUS : n > 0 && n % 7 === 0 ? WEEK_BONUS : 0);
export function nextBonus(n) { let k = n + 1; while (!bonusFor(k)) k++; return { inDays: k - n, pts: bonusFor(k), day: k }; }

// friendlier words for the database's refusals
const nice = e => {
  const m = (e && (e.message || String(e))) || 'Something went wrong';
  if (/Not done yet/.test(m)) return 'Not done yet on your account. Do it once more, then claim.';
  if (/Not enough points/.test(m)) return 'Not enough points for that yet.';
  if (/Not there yet/.test(m)) return 'Your account doesn’t have enough of that set yet. Check the card numbers on your items.';
  return m;
};
const missingFn = e => e && (e.code === 'PGRST202' || e.code === '42883' || /could not find the function|does not exist/i.test(e.message || ''));

// ---------- the account (database) copy, shared by every screen ----------
let cache = { uid: null, status: 'idle', data: null };
const subs = new Set();
const publish = next => { cache = { ...cache, ...next }; subs.forEach(f => f(cache)); };
async function load(uid) {
  if (!supabase || !uid) return;
  publish({ uid, status: cache.uid === uid && cache.data ? 'ok' : 'loading', data: cache.uid === uid ? cache.data : null });
  const r = await supabase.rpc('my_points');
  if (cache.uid !== uid) return;
  if (r.error) publish({ status: missingFn(r.error) ? 'missing' : 'error', error: r.error.message });
  else publish({ status: 'ok', data: r.data });
}
async function call(fn, args) {
  const r = await supabase.rpc(fn, args);
  if (r.error) throw new Error(nice(r.error));
  publish({ status: 'ok', data: r.data });
  return r.data;
}

// ---------- the device copy (only used until the SQL has been run) ----------
const EMPTY = { pts: 0, days: [], log: [], ms: {}, swaps: [] };
function useDevice() {
  const [p, set] = usePref('rewards', EMPTY);
  const v = { ...EMPTY, ...(p || {}) };
  const change = useCallback(fn => { let out; set(x => { const r = fn({ ...EMPTY, ...(x || {}) }); out = r.out; return r.state; }); return out; }, [set]);
  const entry = (delta, why) => ({ at: Date.now() + Math.random(), delta, why });
  return {
    v,
    checkIn: async () => change(o => {
      if (o.days.includes(dayKey())) return { state: o, out: { already: true } };
      const days = [...o.days, dayKey()].slice(-90), { n } = streakInfo(days), bonus = bonusFor(n);
      return { state: { ...o, days, pts: o.pts + CHECKIN + bonus, log: [...(bonus ? [entry(bonus, `${n} days in a row`)] : []), entry(CHECKIN, 'Daily check-in'), ...o.log].slice(0, 80) }, out: { streak: n, bonus } };
    }),
    claim: async m => change(o => (o.ms[m.id] ? { state: o, out: false }
      : { state: { ...o, ms: { ...o.ms, [m.id]: new Date().toISOString() }, pts: o.pts + m.pts, log: [entry(m.pts, m.label), ...o.log].slice(0, 80) }, out: true })),
    redeem: async it => {
      let short = false;
      const id = change(o => {
        if (o.pts < it.cost) { short = true; return { state: o, out: null }; }
        const sid = 'dev' + Date.now();
        return { state: { ...o, pts: o.pts - it.cost, swaps: [{ id: sid, label: it.label, cost: it.cost, status: 'requested', at: new Date().toISOString() }, ...o.swaps].slice(0, 10), log: [entry(-it.cost, `Swapped for ${it.label}`), ...o.log].slice(0, 80) }, out: sid };
      });
      if (short) throw new Error('Not enough points for that yet.');
      return id;
    },
    cancel: async id => change(o => {
      const s = o.swaps.find(x => x.id === id && x.status === 'requested'); if (!s) return { state: o, out: false };
      return { state: { ...o, pts: o.pts + s.cost, swaps: o.swaps.map(x => (x.id === id ? { ...x, status: 'cancelled' } : x)), log: [entry(s.cost, `Swap undone: ${s.label}`), ...o.log].slice(0, 80) }, out: true };
    }),
  };
}

// mode: 'server' (saved to your account) | 'device' (SQL not run yet) | 'loading' | 'signedout'
export function usePoints() {
  const d = useData();
  const uid = d.session?.user?.id || null;
  const [c, setC] = useState(cache);
  useEffect(() => { subs.add(setC); setC(cache); return () => { subs.delete(setC); }; }, []);
  useEffect(() => { if (uid && (cache.uid !== uid || cache.status === 'idle')) load(uid); }, [uid]);
  const dev = useDevice();
  const reload = useCallback(() => uid && load(uid), [uid]);

  const mine = uid && c.uid === uid;
  const mode = !uid || !supabase ? 'signedout' : !mine || c.status === 'loading' || c.status === 'idle' ? 'loading' : c.status === 'missing' ? 'device' : 'server';
  if (mode === 'server' && c.data) {
    const s = c.data;
    return {
      mode, error: null, reload,
      pts: s.pts || 0, days: s.days || [], log: s.log || [], ms: s.ms || {}, swaps: s.swaps || [],
      checkedIn: !!s.checked_in, streak: s.streak || 0, freezeLeft: s.freeze_left !== false,
      checkIn: async () => { const r = await call('check_in'); return { already: !!r.already, bonus: r.bonus || 0, streak: r.streak }; },
      claim: async m => { const r = await call('claim_milestone', { mid: m.id }); return !!r.claimed; },
      redeem: async it => { const r = await call('redeem', { item_id: it.id }); return r.redemption; },
      cancel: async id => { await call('cancel_redemption', { rid: id }); return true; },
      // bounties: null until supabase/2026-11-27-bounty.sql has been run
      bounty: s.bounty != null ? s.bounty : null, quests: s.quests || null, week: s.week || null,
      sets: new Set(s.sets || []), remind: !!s.remind,
      claimQuest: async id => { const r = await call('claim_quest', { qid: id }); return !!r.claimed; },
      claimSet: async (x, pct) => { await call('claim_set', { code: x.code, size: x.size, pct }); return true; },
      setRemind: async on => { const r = await supabase.rpc('set_streak_reminder', { onoff: on }); if (r.error) throw new Error(nice(r.error)); publish({ data: { ...cache.data, remind: on } }); },
    };
  }
  const v = dev.v, st = streakInfo(v.days);
  return {
    mode: mode === 'server' ? (c.status === 'error' ? 'error' : 'loading') : mode, error: mine && c.status === 'error' ? c.error : null, reload,
    pts: v.pts, days: v.days, log: v.log, ms: v.ms, swaps: v.swaps,
    checkedIn: v.days.includes(dayKey()), streak: st.n, freezeLeft: st.freezeLeft,
    checkIn: dev.checkIn, claim: dev.claim, redeem: dev.redeem, cancel: dev.cancel,
    bounty: null, quests: null, week: null, sets: new Set(), remind: false,
  };
}
