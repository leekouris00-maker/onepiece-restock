// Set completion. Normal: each card number counts once (any version of it from this set).
// Master set: every version counts separately (alt arts, SPs, manga…).
export function setProgress(d, setId, master = false) {
  const list = (d.cat?.list || []).filter(x => x.g === setId && x.t === 'card');
  const mine = new Set(d.owned.filter(o => o.status !== 'sold' && o.card).map(o => o.card));
  if (master) {
    const missing = list.filter(x => !mine.has(x.k)).sort((a, b) => a.num.localeCompare(b.num, undefined, { numeric: true }));
    return { total: list.length, have: list.length - missing.length, missing, cost: missing.reduce((n, x) => n + (x.m || 0), 0), unpriced: missing.filter(x => x.m == null).length };
  }
  // the set's own numbers only (OP13-xxx for OP13): SP reprints of older cards count in the master set
  const code = d.cat?.byId[setId]?.code || '';
  const pre = code.split(/[-\s]/).filter(p => /^[A-Z]+\d+$/.test(p)).map(p => p + '-');
  const own = pre.length ? list.filter(x => pre.some(p => x.num.startsWith(p))) : list;
  const byNum = new Map();
  for (const x of own.length ? own : list) (byNum.get(x.num) || byNum.set(x.num, []).get(x.num)).push(x);
  const missing = [];
  for (const [, vs] of byNum) {
    if (vs.some(x => mine.has(x.k))) continue;
    const cheapest = vs.filter(x => x.m != null).sort((a, b) => a.m - b.m)[0] || vs[0];
    missing.push(cheapest);
  }
  missing.sort((a, b) => a.num.localeCompare(b.num, undefined, { numeric: true }));
  return { total: byNum.size, have: byNum.size - missing.length, missing, cost: missing.reduce((n, x) => n + (x.m || 0), 0), unpriced: missing.filter(x => x.m == null).length };
}

// Sets you've started: at least one card owned
export function startedSets(d) {
  const ids = new Set();
  for (const o of d.owned) if (o.status !== 'sold' && o.card) { const c = d.card(o.card); if (c && !c.mine && c.t === 'card') ids.add(c.g); }
  return [...ids].map(id => d.cat?.byId[id]).filter(Boolean);
}
