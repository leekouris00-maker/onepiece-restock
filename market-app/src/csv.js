// Collection in and out as CSV (opens in Excel / Google Sheets). Import understands this app's own export,
// Collectr and TCGplayer exports, and most hand-made sheets: columns are matched by their headings.
import { Platform } from 'react-native';
import { clean, newId, today, track } from './data';
import { versionTag } from './find';
import { toast } from './toast';

export function parseCSV(text) {
  const rows = []; let row = [], f = '', q = false;
  const t = String(text).replace(/^﻿/, '');
  const sep = (t.split('\n')[0].match(/;/g) || []).length > (t.split('\n')[0].match(/,/g) || []).length ? ';'
    : (t.split('\n')[0].match(/\t/g) || []).length > (t.split('\n')[0].match(/,/g) || []).length ? '\t' : ',';
  for (let i = 0; i < t.length; i++) {
    const ch = t[i];
    if (q) {
      if (ch === '"') { if (t[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch;
    } else if (ch === '"') q = true;
    else if (ch === sep) { row.push(f); f = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && t[i + 1] === '\n') i++; row.push(f); f = ''; if (row.some(x => x.trim())) rows.push(row); row = []; }
    else f += ch;
  }
  row.push(f); if (row.some(x => x.trim())) rows.push(row);
  return rows;
}

const cell = v => { const s = v == null ? '' : String(v); return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
export const toCSV = rows => rows.map(r => r.map(cell).join(',')).join('\r\n');

// Heading words → field. First match wins, so the more specific ones come first.
const FIELDS = [
  ['pid', /^(tcg ?player )?(product ?id|tcgplayer id|tcg id|productid)$/],
  ['num', /(card )?(number|no\.?|#)$|^num$|card ?number|collector/],
  ['name', /^(product )?name$|^card( name)?$|^product$|^title$|^item$/],
  ['set', /^set( name)?$|expansion|^group name$|^release$/],
  ['version', /variance|variant|printing|version|finish/],
  ['qty', /qty|quantity|count|amount owned|^copies$/],
  ['paid', /paid|cost|purchase price|bought/],
  ['value', /your value|value each|price override|my value/],
  ['group', /portfolio|folder|binder|^group$|collection|^list$/],
  ['cond', /grade|condition|cond$/],
  ['lang', /lang/],
  ['status', /^status$/],
  ['sold', /sold for/],
  ['added', /date added|^added$|^date$/],
  ['notes', /note/],
];

export function mapHeader(head) {
  const m = {};
  head.forEach((h, i) => {
    const k = String(h).trim().toLowerCase();
    for (const [f, re] of FIELDS) if (!(f in m) && re.test(k)) { m[f] = i; break; }
  });
  return m;
}

const money = v => { const n = parseFloat(String(v || '').replace(/[^0-9.\-]/g, '')); return isNaN(n) ? null : n; };
const words = s => String(s || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
const STOP = new Set(['the', 'of', 'and', 'normal', 'holofoil', 'foil', 'card', 'cards', 'one', 'piece', 'promotion', 'promo', 'near', 'mint']);

// Match each row to a catalog card. Returns preview rows: { row, card, item, how }
export function matchRows(rows, map, d, byNum) {
  const out = [];
  for (const r of rows) {
    const get = f => (map[f] != null ? String(r[map[f]] ?? '').trim() : '');
    const name = get('name'), num = get('num').toUpperCase().replace(/\s+/g, ''), pid = get('pid').replace(/\D/g, '');
    if (!name && !num && !pid) continue;
    let card = null, how = '';
    if (pid && d.cat?.byKey['t:' + pid]) { card = d.cat.byKey['t:' + pid]; how = 'product id'; }
    if (!card && num) {
      const opts = byNum.get(num) || [];
      if (opts.length === 1) { card = opts[0]; how = 'number'; }
      else if (opts.length > 1) {
        // pick the version whose name, set and printing words overlap the row most
        const want = new Set(words(`${name} ${get('version')} ${get('set')}`).split(' ').filter(w => !STOP.has(w)));
        let best = null, bs = -1, tie = false;
        for (const x of opts) {
          const have = new Set(words(`${x.n} ${versionTag(d.cat, x)} ${d.cat?.byId[x.g]?.name || ''}`).split(' ').filter(w => !STOP.has(w)));
          // words both share, minus words only the catalog version has (an "Alternate Art" you didn't mention)
          const both = [...have].filter(w => want.has(w)).length, extra = [...have].filter(w => !want.has(w)).length;
          const sc = both * 2 - extra * 0.25;
          if (sc > bs) { bs = sc; best = x; tie = false; } else if (sc === bs) tie = true;
        }
        card = best; how = tie ? 'best guess: check the version' : 'number + name';
      }
    }
    if (!card && name && d.cat) {
      const w = words(name);
      const hit = d.cat.list.filter(x => words(x.n) === w);
      if (hit.length === 1) { card = hit[0]; how = 'name'; }
    }
    const lang0 = get('lang').toUpperCase();
    const lang = /JA|JP/.test(lang0) ? 'JP' : /CN|ZH|CHIN/.test(lang0) ? 'CN' : /KO|KR/.test(lang0) ? 'KR' : 'EN';
    const condRaw = get('cond');
    const cond = /ungraded|^raw$|near mint|^nm$/i.test(condRaw) ? (card?.t === 'sealed' ? 'Sealed' : 'Raw') : /psa\s*10/i.test(condRaw) ? 'PSA 10' : /psa\s*9/i.test(condRaw) ? 'PSA 9' : /psa|bgs|cgc|graded/i.test(condRaw) ? 'Other graded'
      : /sealed/i.test(condRaw) ? 'Sealed' : card?.t === 'sealed' ? 'Sealed' : 'Raw';
    const status = /sold/i.test(get('status')) ? 'sold' : 'owned';
    const item = {
      id: newId(), card: card ? card.k : null, name: card ? clean(card.n) : name || num, num: card ? null : num || null,
      qty: Math.max(1, parseInt(get('qty'), 10) || 1), kind: card ? (card.t === 'sealed' ? 'Sealed' : card.t === 'don' ? 'DON!!' : 'Card') : 'Card',
      cond, lang, group: get('group') || null, paid: money(get('paid')), value: money(get('value')), notes: get('notes'),
      status, soldFor: money(get('sold')), added: /^\d{4}-\d{2}-\d{2}/.test(get('added')) ? get('added').slice(0, 10) : today(),
    };
    out.push({ row: r, card, item, how });
  }
  return out;
}

export function exportRows(d) {
  const head = ['Name', 'Number', 'Set', 'Version', 'Language', 'Condition', 'Group', 'Quantity', 'Paid each (A$)', 'Value each (A$)', 'Value source',
    'Total value (A$)', 'Status', 'Sold for each (A$)', 'Added', 'Notes', 'TCGplayer product ID'];
  const rows = [...d.owned].sort((a, b) => String(a.group).localeCompare(String(b.group)) || clean(a.name).localeCompare(clean(b.name))).map(o => {
    const c = d.card(o.card), v = d.ownVal(o), q = Number(o.qty) || 1;
    return [clean(o.name), c?.num || o.num || '', c ? (c.mine ? c.setName : d.cat?.byId[c.g]?.name || '') : '', c ? versionTag(d.cat, c) : '',
      o.lang || 'EN', o.cond || '', o.group || '', q, o.paid ?? '', v.a == null ? '' : v.a.toFixed(2), v.src, v.a == null ? '' : (v.a * q).toFixed(2),
      o.status || 'owned', o.soldFor ?? '', o.added || '', o.notes || '', o.card && o.card.startsWith('t:') ? o.card.slice(2) : ''];
  });
  return [head, ...rows];
}

// Save a file: share sheet on a phone (Save to Files, AirDrop, Mail…), download on a computer
export async function saveFile(name, text, type = 'text/csv') {
  if (Platform.OS !== 'web') return false;
  const blob = new Blob([text], { type });
  const file = typeof File !== 'undefined' ? new File([blob], name, { type }) : null;
  const touch = typeof navigator !== 'undefined' && /iPhone|iPad|Android/i.test(navigator.userAgent || '');
  if (touch && file && navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], title: name }); return true; } catch (e) { if (e && e.name === 'AbortError') return false; }
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  return true;
}

// Pick a file (web)
export function pickFile(accept = '.csv,text/csv,text/plain') {
  return new Promise(res => {
    const i = document.createElement('input');
    i.type = 'file'; i.accept = accept; i.style.display = 'none';
    i.onchange = () => { const f = i.files && i.files[0]; i.remove(); res(f || null); };
    document.body.appendChild(i); i.click();
  });
}

export async function exportCollection(d) {
  track('export');
  try {
    if (!d.owned.length) { toast('Nothing in your collection to export yet'); return; }
    const ok = await saveFile(`one-piece-collection-${new Date().toISOString().slice(0, 10)}.csv`, toCSV(exportRows(d)));
    if (ok) toast(`Exported ${d.owned.length} entries`);
  } catch (e) { toast(e.message || String(e)); }
}
