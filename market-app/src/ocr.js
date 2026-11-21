// Card scanner text reader. tesseract.js runs on the phone (no server, no cost); its files are shipped
// with the site under /ocr/ by build-web.sh. The first scan downloads ~7 MB, which the browser then keeps.

let readerP = null;
let progress = () => {};

// The site's base address, e.g. https://…github.io/onepiece-restock/
export function siteBase() {
  if (typeof document === 'undefined') return '/';
  const s = [...document.scripts].map(x => x.src).find(x => x.includes('/_expo/static/js/'));
  return s ? s.slice(0, s.indexOf('_expo/')) : location.origin + '/';
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    if (window.Tesseract) return resolve();
    const el = document.createElement('script');
    el.src = src;
    el.async = true;
    el.onload = () => resolve();
    el.onerror = () => reject(new Error('The card reader could not load. Check your connection and try again.'));
    document.head.appendChild(el);
  });
}

// One shared reader for the whole visit. onProgress gets 0..1 while it loads.
export function getReader(onProgress) {
  if (onProgress) progress = onProgress;
  if (!readerP) {
    readerP = (async () => {
      const base = siteBase() + 'ocr/';
      await loadScript(base + 'tesseract.min.js');
      const w = await window.Tesseract.createWorker('eng', 1, {
        workerPath: base + 'worker.min.js', corePath: base, langPath: base,
        logger: m => { if (m && typeof m.progress === 'number' && /load|initializ/i.test(m.status || '')) progress(m.progress); },
      });
      // Card numbers only use capitals, digits and "-"; "11" = find scattered bits of text anywhere
      await w.setParameters({ tessedit_char_whitelist: 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-', tessedit_pageseg_mode: '11' });
      return w;
    })().catch(e => { readerP = null; throw e; });
  }
  return readerP;
}

// Letters the reader often mistakes for digits inside the number part
const AS_DIGIT = { O: '0', Q: '0', D: '0', U: '0', I: '1', L: '1', T: '1', J: '1', Z: '2', S: '5', G: '6', B: '8' };
const digits = s => s.replace(/[OQDUILTJZSGB]/g, ch => AS_DIGIT[ch]);
const D2 = '[0-9OQDUILTJZSGB]{2}', D3 = '[0-9OQDUILTJZSGB]{3}';
// Numbers always have exactly 3 digits after the dash; whatever follows (the rarity, the block mark) is ignored
const SET_CODE = new RegExp(`([O0Q]P|E[B8]|[S5]T|PR[B8])\\s?(${D2})\\s?-?\\s?(${D3})`, 'g');
const PROMO = new RegExp(`(?:^|[^A-Z0-9])P\\s?-\\s?(${D3})`, 'g');
const PREFIX = { '0P': 'OP', QP: 'OP', E8: 'EB', '5T': 'ST', PR8: 'PRB' };

// The number with its letters half-lost ("P01-016", "801-023"): rebuilt only when exactly one real card fits
const PART = new RegExp(`([A-Z0-9]?)(${D2})\\s?-\\s?(${D3})`, 'g');
const LONE = new RegExp(`(?:^|[\\s-])-\\s?(${D3})`, 'g');
const GUESS = { P: ['OP'], B: ['EB', 'PRB'], 8: ['EB', 'PRB'], T: ['ST'], 5: ['ST'] };

// Every card number in a piece of read text: "0P13-12O" -> "OP13-120", "P-1O5" -> "P-105".
// Pass the set of real card numbers as known to also rebuild numbers whose first letters were lost.
export function findCodes(text, known) {
  const t = ' ' + String(text || '').toUpperCase().replace(/[–—_=~]/g, '-') + ' ';
  const out = [];
  for (const m of t.matchAll(SET_CODE)) out.push(`${PREFIX[m[1]] || m[1]}${digits(m[2])}-${digits(m[3])}`);
  for (const m of t.matchAll(PROMO)) out.push(`P-${digits(m[1])}`);
  if (known) {
    for (const m of t.matchAll(PART)) {
      const tail = `${digits(m[2])}-${digits(m[3])}`;
      const fits = (GUESS[m[1]] || ['OP', 'EB', 'ST', 'PRB']).map(p => p + tail).filter(k => known.has(k));
      if (fits.length === 1) out.push(fits[0]);
    }
  }
  if (known && !out.length) {                       // last resort: "-105" with the P lost -> a promo, P-105
    for (const m of t.matchAll(LONE)) if (known.has(`P-${digits(m[1])}`)) out.push(`P-${digits(m[1])}`);
  }
  return [...new Set(out)].filter(k => !known || known.has(k));
}

// Copy part of an image/video into a canvas for the reader: scaled so the text is big enough,
// grey, sharpened (unsharp mask) and with the contrast stretched
export function grab(src, sx, sy, sw, sh, outH, sharpen = true) {
  const maxW = (src.videoWidth || src.naturalWidth || src.width), maxH = (src.videoHeight || src.naturalHeight || src.height);
  sx = Math.max(0, sx); sy = Math.max(0, sy);
  sw = Math.max(1, Math.min(sw, maxW - sx)); sh = Math.max(1, Math.min(sh, maxH - sy));
  const scale = Math.min(3, Math.max(0.25, outH / sh));
  const c = document.createElement('canvas');
  const w = c.width = Math.max(1, Math.round(sw * scale)), h = c.height = Math.max(1, Math.round(sh * scale));
  const g = c.getContext('2d', { willReadFrequently: true });
  g.imageSmoothingQuality = 'high';
  g.drawImage(src, sx, sy, sw, sh, 0, 0, w, h);
  const img = g.getImageData(0, 0, w, h), p = img.data, n = w * h;
  let y = new Float32Array(n);
  for (let i = 0; i < n; i++) y[i] = (p[i * 4] * 299 + p[i * 4 + 1] * 587 + p[i * 4 + 2] * 114) / 1000;
  if (sharpen) {
    const b = boxBlur(boxBlur(y, w, h, 3), w, h, 3);
    for (let i = 0; i < n; i++) y[i] = y[i] + 1.6 * (y[i] - b[i]);
  }
  const hist = new Uint32Array(256);
  for (let i = 0; i < n; i++) hist[Math.max(0, Math.min(255, y[i] | 0))]++;
  let lo = 0, hi = 255, acc = 0;
  for (; lo < 255 && (acc += hist[lo]) < n * 0.02; lo++);
  acc = 0;
  for (; hi > 0 && (acc += hist[hi]) < n * 0.02; hi--);
  const k = hi > lo ? 255 / (hi - lo) : 1;
  for (let i = 0; i < n; i++) { const v = Math.max(0, Math.min(255, (y[i] - lo) * k)); p[i * 4] = p[i * 4 + 1] = p[i * 4 + 2] = v; p[i * 4 + 3] = 255; }
  g.putImageData(img, 0, 0);
  return c;
}

// Separable box blur (two passes ~ a Gaussian), used by the sharpening above
function boxBlur(src, w, h, r) {
  const tmp = new Float32Array(src.length), out = new Float32Array(src.length), d = 2 * r + 1;
  for (let yy = 0; yy < h; yy++) {
    let s = 0; const o = yy * w;
    for (let x = -r; x <= r; x++) s += src[o + Math.min(w - 1, Math.max(0, x))];
    for (let x = 0; x < w; x++) { tmp[o + x] = s / d; s += src[o + Math.min(w - 1, x + r + 1)] - src[o + Math.max(0, x - r)]; }
  }
  for (let x = 0; x < w; x++) {
    let s = 0;
    for (let yy = -r; yy <= r; yy++) s += tmp[Math.min(h - 1, Math.max(0, yy)) * w + x];
    for (let yy = 0; yy < h; yy++) { out[yy * w + x] = s / d; s += tmp[Math.min(h - 1, yy + r + 1) * w + x] - tmp[Math.max(0, yy - r) * w + x]; }
  }
  return out;
}
