// Decklist text → [{ num, n }]: "4xOP01-016", "4 OP01-016 Nami", "OP01-016 x4" (used by Deck price and the Ban & Meta page)
const NUM = '((?:OP|EB|ST|PRB)\\d{2}-\\d{3}|P-\\d{3})';
export function parseDeck(text) {
  const out = new Map();
  for (const raw of String(text || '').split(/\r?\n|,|;/)) {
    const line = raw.trim().toUpperCase();
    if (!line) continue;
    let m = new RegExp(`^(\\d{1,2})\\s*[X×]?\\s*${NUM}`).exec(line), n, num;
    if (m) { n = Number(m[1]); num = m[2]; }
    else if ((m = new RegExp(`${NUM}\\s*[X×]\\s*(\\d{1,2})`).exec(line))) { num = m[1]; n = Number(m[2]); }
    else if ((m = new RegExp(NUM).exec(line))) { num = m[1]; n = 1; }
    else continue;
    out.set(num, (out.get(num) || 0) + n);
  }
  return [...out.entries()].map(([num, n]) => ({ num, n }));
}
