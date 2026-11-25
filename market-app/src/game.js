// Game news for the app: Bandai's ban list, ban news and prize events (game.json, kept by hand from Bandai's site)
// and the weekly Meta Radar from Limitless TCG tournaments (meta.json, written by meta_radar.py).
// Both are files in the repo, fetched like the price files, so they update without a new app build.
import { useEffect, useState } from 'react';
import { clean, loadJSON } from './data';
import { parseDeck } from './deckparse';

let cache = { game: null, meta: null, metaError: null, ready: false };
const subs = new Set();
let started = false;
async function start() {
  if (started) return;
  started = true;
  const [[g], [m]] = await Promise.all([loadJSON('game.json'), loadJSON('meta.json')]);
  cache = { game: g || null, meta: m && !m.error && m.leaders ? m : null, metaError: m && m.error ? m.error : null, ready: true };
  subs.forEach(f => f(cache));
}
export function useGame() {
  const [c, setC] = useState(cache);
  useEffect(() => { subs.add(setC); setC(cache); start(); return () => { subs.delete(setC); }; }, []);
  return c;
}

export const todayIso = () => { const t = new Date(); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`; };
export const niceDate = iso => (iso ? new Date(iso + 'T12:00:00').toLocaleDateString('en-AU', { day: 'numeric', month: 'short' }) : '');
const U = s => String(s || '').toUpperCase();

// What the ban list says about one card number: { banned, restricted, pairs: [{ with: [{num,name}], since }] }
export function banInfo(game, num) {
  if (!game || !num) return null;
  const n = U(num);
  const banned = (game.banned || []).find(b => U(b.num) === n);
  const restricted = (game.restricted || []).find(b => U(b.num) === n);
  const pairs = [];
  for (const p of game.pairs || []) {
    if (U(p.a.num) === n) pairs.push({ with: p.b, since: p.since });
    else if (p.b.some(b => U(b.num) === n)) pairs.push({ with: [p.a], since: p.since });
  }
  if (!banned && !restricted && !pairs.length) return null;
  return { banned, restricted, pairs };
}
export function banText(info) {
  if (!info) return '';
  if (info.banned) return `Banned in official tournaments${info.banned.since ? ` (since ${niceDate(info.banned.since)})` : ''}`;
  if (info.restricted) return `Restricted to ${info.restricted.limit || 1} copy`;
  const p = info.pairs[0];
  const upcoming = p.since && p.since > todayIso();
  return `${upcoming ? `From ${niceDate(p.since)}: c` : 'C'}an’t share a deck with ${p.with.map(w => `${w.name} (${w.num})`).join(' or ')}`;
}

// card numbers you own (not sold) and in the deck you pasted into Deck price
export function myNums(d, deckText) {
  const own = new Set();
  for (const o of d.owned || []) {
    if (o.status === 'sold') continue;
    const num = o.num || (o.card && d.card(o.card)?.num);
    if (num) own.add(U(num));
  }
  const deck = new Set(parseDeck(deckText || '').map(x => U(x.num)));
  return { own, deck };
}
// every ban-list entry that touches your cards or your deck
export function affected(game, own, deck) {
  if (!game) return [];
  const out = [];
  for (const num of new Set([...own, ...deck])) {
    const info = banInfo(game, num);
    if (!info) continue;
    // a banned pair only matters for a deck holding both halves; for a collection, it's worth knowing either way
    const inDeckClash = info.pairs.some(p => deck.has(num) && p.with.some(w => deck.has(U(w.num))));
    out.push({ num, info, owned: own.has(num), inDeck: deck.has(num), clash: inDeckClash || (!!info.banned && deck.has(num)) });
  }
  return out.sort((a, b) => Number(b.clash) - Number(a.clash) || a.num.localeCompare(b.num));
}

export const newsWithin = (game, days = 21) => {
  const t = todayIso(), from = new Date(); from.setDate(from.getDate() - days);
  const f = `${from.getFullYear()}-${String(from.getMonth() + 1).padStart(2, '0')}-${String(from.getDate()).padStart(2, '0')}`;
  return (game?.news || []).filter(n => (n.effective || n.announced) >= f || (n.effective && n.effective >= t));
};
export const eventsNow = game => (game?.events || []).filter(e => e.start <= todayIso() && e.end >= todayIso());
export const eventsSoon = (game, days = 45) => {
  const t = todayIso(), to = new Date(); to.setDate(to.getDate() + days);
  const lim = `${to.getFullYear()}-${String(to.getMonth() + 1).padStart(2, '0')}-${String(to.getDate()).padStart(2, '0')}`;
  return (game?.events || []).filter(e => e.start > t && e.start <= lim).sort((a, b) => a.start.localeCompare(b.start));
};

// the catalogue cards for a card number, most valuable first
export function cardsFor(d, num) {
  const list = (d.byNum && d.byNum.get(U(num))) || [];
  return [...list].sort((a, b) => (b.m || 0) - (a.m || 0));
}
export const nameFor = (d, num) => { const c = cardsFor(d, num)[0]; return c ? clean(c.n).replace(/\s*\(.*\)\s*$/, '') : num; };
