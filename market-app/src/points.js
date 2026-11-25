// Points from the daily spin, and the points shop (PREVIEW: kept on this device only, nothing real is sent).
// Rules that keep it a free promotion, not gambling: points are only ever earned (never bought, sold or
// transferred), members earn exactly the same, and redeeming is always free, postage included.
import { useCallback } from 'react';
import { usePref } from './prefs';

export const POINT_AUD = 0.01;            // 100 points ≈ A$1 of shop value
export const STREAK = [[30, 500], [7, 100]];   // every 7th day in a row +100; day 30 +500 instead

const EMPTY = { pts: 0, days: [], log: [] };
export const dayKey = (t = new Date()) => `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`;

// days spun in a row, ending today (or yesterday, if you haven't spun yet today)
export function streakOf(days) {
  const set = new Set(days || []);
  const t = new Date();
  if (!set.has(dayKey(t))) t.setDate(t.getDate() - 1);
  let n = 0;
  while (set.has(dayKey(t))) { n++; t.setDate(t.getDate() - 1); }
  return n;
}
export const bonusFor = n => { for (const [at, pts] of STREAK) if (at === 30 ? n === 30 : n > 0 && n % at === 0) return pts; return 0; };
export function nextBonus(n) {
  let k = n + 1;
  while (!bonusFor(k)) k++;
  return { inDays: k - n, pts: bonusFor(k), day: k };
}

export function usePoints() {
  const [p, set] = usePref('spinPoints', EMPTY);
  const v = p || EMPTY;
  const add = useCallback((delta, why) => set(x => {
    const o = x || EMPTY;
    return { ...o, pts: Math.max(0, (o.pts || 0) + delta), log: [{ at: Date.now(), delta, why }, ...(o.log || [])].slice(0, 60) };
  }), [set]);
  // a spin: points won + today's streak day (and its bonus, the first spin of the day only)
  const spun = useCallback(won => {
    let bonus = 0, streak = 0;
    set(x => {
      const o = x || EMPTY, today = dayKey();
      const first = !(o.days || []).includes(today);
      const days = first ? [...(o.days || []), today].slice(-60) : o.days || [];
      streak = streakOf(days);
      bonus = first ? bonusFor(streak) : 0;
      const log = [...(bonus ? [{ at: Date.now() + 1, delta: bonus, why: `${streak}-day streak bonus` }] : []), ...(won ? [{ at: Date.now(), delta: won, why: 'Daily spin' }] : []), ...(o.log || [])].slice(0, 60);
      return { ...o, days, pts: (o.pts || 0) + won + bonus, log };
    });
    return { bonus, streak };
  }, [set]);
  return { pts: v.pts || 0, days: v.days || [], log: v.log || [], streak: streakOf(v.days), add, spun };
}

// The shop. aud = fixed value; k = a product whose live price sets the cost (100 points per A$1, rounded up to 50).
export const SHOP = [
  { id: 'c5', label: 'A$5 store credit', sub: 'Off anything in the store', icon: 'pricetag-outline', aud: 5 },
  { id: 'c10', label: 'A$10 store credit', sub: 'Off anything in the store', icon: 'pricetag-outline', aud: 10 },
  { id: 'pack', label: 'OP-18 booster pack', sub: 'Sealed, shipped free', k: 't:712904' },
  { id: 'single20', label: 'Any single up to A$20', sub: 'You pick the card', icon: 'albums-outline', aud: 20 },
  { id: 'c25', label: 'A$25 store credit', sub: 'Off anything in the store', icon: 'pricetag-outline', aud: 25 },
  { id: 'single50', label: 'Any single up to A$50', sub: 'You pick the card', icon: 'albums-outline', aud: 50 },
  { id: 'box', label: 'OP-18 booster box', sub: 'Sealed, shipped free', k: 't:712901' },
];
export const costOf = (aud) => (aud ? Math.ceil(aud / POINT_AUD / 50) * 50 : null);
