// Forgiving card search + version labels.
// "op17 84", "OP17-084", "op1784" all find OP17-084; "chopper re" finds the Release Event Chopper;
// one typo in a longer word is fine ("chpper", "shanks" vs "shankz").
const clean = n => String(n || '').replace(/\s*\((?:\d{3})\)/, '');

// What each kind of set is called, plus the short words people type for it
const KIND_WORDS = {
  event: 'release event re', 'pre-release': 'pre-release prerelease pre release pr', promo: 'promo promotion',
  starter: 'starter deck st', extra: 'extra booster eb', premium: 'premium booster prb', booster: 'booster',
};
// Extra words for versions printed in the name, e.g. "(Alternate Art)"
const VERSION_WORDS = [
  [/alternate art/i, 'alt aa alternate art'], [/parallel/i, 'parallel alt aa'], [/\bsp\b/i, 'sp special'],
  [/manga/i, 'manga'], [/full art/i, 'full art fa'], [/gold/i, 'gold'], [/foil/i, 'foil'], [/reprint/i, 'reprint'],
];

const pad = (s, n) => String(s).padStart(n, '0');

// Turn the ways people type card numbers into the printed form
export function normQuery(q) {
  let s = ' ' + String(q || '').toLowerCase().replace(/[–—_]/g, '-') + ' ';
  s = s.replace(/(^|[^a-z])(op|eb|st|prb)\s*-?\s*(\d{1,2})\s*[-\s]\s*(\d{1,3})(?=[^\d]|$)/g, (m, a, p, x, y) => `${a}${p}${pad(x, 2)}-${pad(y, 3)}`);
  s = s.replace(/(^|[^a-z])(op|eb|st|prb)(\d{2})(\d{1,3})(?=[^\d]|$)/g, (m, a, p, x, y) => `${a}${p}${x}-${pad(y, 3)}`);
  s = s.replace(/(^|[^a-z])p\s*-?\s*(\d{1,3})(?=[^\d]|$)/g, (m, a, x) => `${a}p-${pad(x, 3)}`);
  return s.trim().replace(/\s+/g, ' ');
}

function lev1(a, b) {                       // differ by at most one edit
  if (a === b) return true;
  const la = a.length, lb = b.length;
  if (Math.abs(la - lb) > 1) return false;
  let i = 0, j = 0, e = 0;
  while (i < la && j < lb) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++e > 1) return false;
    if (la > lb) i++; else if (lb > la) j++; else { i++; j++; }
  }
  return e + (la - i) + (lb - j) <= 1;
}

// One label that tells versions of the same card number apart: "Release Event", "Alternate Art", "P-105 · Store Tournament"
export function versionTag(cat, x) {
  if (!x) return '';
  if (x.mine) return x.setName || 'Your card';
  const set = cat?.byId[x.g], parts = [];
  const paren = (clean(x.n).match(/\(([^)]*)\)/g) || []).map(p => p.slice(1, -1)).filter(p => !/^\d+$/.test(p) && !/^[A-Z]{1,3}\d{0,2}-\d{3}$/i.test(p));
  if (set?.kind === 'event') parts.push('Release Event');
  else if (set?.kind === 'pre-release') parts.push('Pre-release');
  parts.push(...paren);
  if (!parts.length) parts.push(set?.kind === 'promo' ? 'Promo' : set?.kind === 'starter' ? 'Starter deck' : 'Regular');
  return parts.join(' · ');
}

// Built once per catalog: every card's searchable text and words
export function buildIndex(list, cat) {
  return list.map(x => {
    const set = x.mine ? null : cat?.byId[x.g];
    const name = clean(x.n);
    let extra = '';
    for (const [re, w] of VERSION_WORDS) if (re.test(name)) extra += ' ' + w;
    const num = String(x.num || '').toLowerCase();
    const hay = [name.toLowerCase(), num, num.replace('-', ''), (x.r || '').toLowerCase(), set ? `${set.code} ${set.name}`.toLowerCase() : (x.setName || '').toLowerCase(),
      set ? KIND_WORDS[set.kind] || '' : x.mine ? 'mine my card ' + (x.lang || '').toLowerCase() + (x.lang === 'JP' ? ' japanese jp' : '') : '', extra].join(' ');
    const words = [...new Set(hay.split(/[^a-z0-9-]+/).filter(Boolean))];
    return { x, hay, words, num, name: name.toLowerCase() };
  });
}

// Matches, best first: exact number, then name starting with the words, then highest price
export function searchCards(index, q, limit = 300) {
  const s = normQuery(q);
  if (s.length < 2) return [];
  const toks = s.split(' ').filter(Boolean);
  const out = [];
  for (const e of index) {
    let score = 0, ok = true;
    for (const t of toks) {
      if (t === e.num) { score += 10; continue; }
      if (t.length <= 2) { if (e.words.includes(t)) { score += 1; continue; } ok = false; break; }
      if (e.hay.includes(t)) { score += e.words.some(w => w.startsWith(t)) ? 2 : 1; continue; }
      if (t.length >= 4 && !/\d/.test(t) && e.words.some(w => w.length >= 3 && lev1(w, t))) { score += 0.5; continue; }
      ok = false; break;
    }
    if (ok) out.push([score, e.x]);
  }
  out.sort((a, b) => b[0] - a[0] || (b[1].m ?? -1) - (a[1].m ?? -1));
  return out.slice(0, limit).map(p => p[1]);
}
