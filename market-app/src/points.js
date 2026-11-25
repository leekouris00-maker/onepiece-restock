// Points (PREVIEW: kept on this device only, nothing real is sent).
// No chance anywhere: every reward is fixed and known in advance, so it's an ordinary loyalty scheme,
// not a lottery. Points are only ever earned (never bought, sold or transferred), have no cash value,
// and paid members earn exactly the same as everyone else.
import { useCallback } from 'react';
import { usePref } from './prefs';

export const POINT_AUD = 0.01;          // 100 points = A$1 of shop value
export const CHECKIN = 10;              // one check-in a day
export const WEEK_BONUS = 50;           // every 7th day in a row
export const MONTH_BONUS = 250;         // day 30 in a row (instead of the 7-day bonus that day)

// One-off rewards for using the app properly. Each pays once per account, ever, so they can't be farmed.
export const MILESTONES = [
  { id: 'card1', label: 'Add your first card', sub: 'Anything in your collection', pts: 50, icon: 'add-circle-outline', go: '/search', done: s => s.items >= 1 },
  { id: 'card10', label: '10 things in your collection', sub: 'Cards, sealed, anything', pts: 100, icon: 'albums-outline', go: '/search', done: s => s.items >= 10 },
  { id: 'card50', label: '50 things in your collection', sub: 'A proper collection', pts: 200, icon: 'library-outline', go: '/search', done: s => s.items >= 50 },
  { id: 'scan', label: 'Scan a card with the camera', sub: 'Point it at any card', pts: 50, icon: 'scan-outline', go: '/scan', done: s => s.scanned },
  { id: 'alert', label: 'Set a price alert', sub: 'On any card you watch', pts: 25, icon: 'notifications-outline', go: '/watchlist', done: s => s.alert },
  { id: 'import', label: 'Import your collection', sub: 'From Collectr or a spreadsheet', pts: 100, icon: 'cloud-upload-outline', go: '/import', done: s => s.imported },
];
export const MILESTONE_TOTAL = MILESTONES.reduce((s, m) => s + m.pts, 0);

const EMPTY = { pts: 0, days: [], log: [], ms: {} };
export const dayKey = (t = new Date()) => `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;
const back = (t, n = 1) => { const x = new Date(t); x.setDate(x.getDate() - n); return x; };

// Days checked in a row, ending today (or yesterday if you haven't checked in yet today).
// One missed day a calendar month is covered automatically (a "streak freeze"); it doesn't add to the count.
export function streakInfo(days) {
  const set = new Set(days || []);
  let t = new Date();
  if (!set.has(dayKey(t))) t = back(t);
  let n = 0;
  const frozen = new Set();
  for (;;) {
    if (set.has(dayKey(t))) { n++; t = back(t); continue; }
    const month = dayKey(t).slice(0, 7);
    // a single missed day, with the day before it checked in, and this month's freeze unused
    if (!frozen.has(month) && set.has(dayKey(back(t)))) { frozen.add(month); t = back(t); continue; }
    break;
  }
  const thisMonth = dayKey().slice(0, 7);
  return { n, freezeLeft: !frozen.has(thisMonth), frozen: [...frozen] };
}
export const bonusFor = n => (n === 30 ? MONTH_BONUS : n > 0 && n % 7 === 0 ? WEEK_BONUS : 0);
export function nextBonus(n) { let k = n + 1; while (!bonusFor(k)) k++; return { inDays: k - n, pts: bonusFor(k), day: k }; }

export function usePoints() {
  const [p, set] = usePref('rewards', EMPTY);
  const v = { ...EMPTY, ...(p || {}) };
  const today = dayKey();
  const add = useCallback((delta, why) => set(x => {
    const o = { ...EMPTY, ...(x || {}) };
    return { ...o, pts: Math.max(0, o.pts + delta), log: [{ at: Date.now(), delta, why }, ...o.log].slice(0, 80) };
  }), [set]);
  // the daily check-in: once a day, +10, plus a streak bonus on the 7th / 30th day in a row
  const checkIn = useCallback(() => {
    let res = null;
    set(x => {
      const o = { ...EMPTY, ...(x || {}) };
      if (o.days.includes(dayKey())) { res = { already: true }; return o; }
      const days = [...o.days, dayKey()].slice(-90);
      const { n } = streakInfo(days);
      const bonus = bonusFor(n);
      const log = [...(bonus ? [{ at: Date.now() + 1, delta: bonus, why: `${n} days in a row` }] : []), { at: Date.now(), delta: CHECKIN, why: 'Daily check-in' }, ...o.log].slice(0, 80);
      res = { streak: n, bonus };
      return { ...o, days, pts: o.pts + CHECKIN + bonus, log };
    });
    return res;
  }, [set]);
  const claim = useCallback(m => {
    let ok = false;
    set(x => {
      const o = { ...EMPTY, ...(x || {}) };
      if (o.ms[m.id]) return o;
      ok = true;
      return { ...o, ms: { ...o.ms, [m.id]: Date.now() }, pts: o.pts + m.pts, log: [{ at: Date.now(), delta: m.pts, why: m.label }, ...o.log].slice(0, 80) };
    });
    return ok;
  }, [set]);
  const st = streakInfo(v.days);
  return { pts: v.pts, days: v.days, log: v.log, ms: v.ms, checkedIn: v.days.includes(today), streak: st.n, freezeLeft: st.freezeLeft, add, checkIn, claim };
}

// The shop: fixed points prices (100 points = A$1), reviewed monthly with notice. No mystery or random items.
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
