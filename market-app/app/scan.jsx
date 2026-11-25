// Card scanner: point the camera at a card, read the number in its bottom-right corner (OP13-120, P-105…),
// then show every version of that card with prices and a one-tap add to the collection.
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, Pressable, ScrollView, TextInput, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { clean, newId, today, useData } from '../src/data';
import { F, useTheme } from '../src/theme';
import { CardArt, Choice, Field, T } from '../src/ui';
import { decide, findCodes, getReader, grab, nameIndex } from '../src/ocr';
import { versionTag } from '../src/find';
import { haptic } from '../src/haptic';
import { usePref, getPref, setPref } from '../src/prefs';
import { toast } from '../src/toast';

const CARD = 63 / 88;

export default function Scan() {
  const d = useData(), c = useTheme(), ins = useSafeAreaInsets();
  const { width: W, height: H } = useWindowDimensions();
  const video = useRef(null), fileIn = useRef(null), stream = useRef(null);
  const [cam, setCam] = useState('starting');          // starting | on | blocked | none
  const [reader, setReader] = useState(null);
  const [load, setLoad] = useState(0);
  const [readErr, setReadErr] = useState('');
  const [seen, setSeen] = useState('');                 // a number read once, waiting for a second read
  const [found, setFound] = useState(null);             // { code (number or card name), codes, list, also }
  const [history, setHistory] = useState([]);           // numbers found this visit
  const [typing, setTyping] = useState(false);
  const [typed, setTyped] = useState('');
  const [busyPhoto, setBusyPhoto] = useState(false);
  const [stuck, setStuck] = useState(false);            // nothing read for a while: show tips
  const [stack, setStack] = usePref('scanStack', false);   // stack mode: keep scanning, collect cards in a tray
  const [tray, setTray] = usePref('scanTray', []);         // [{ k, qty }]
  const [review, setReview] = useState(false);
  const [flash, setFlash] = useState(null);                // "Added …" banner in stack mode
  const [torch, setTorch] = useState(null);                // null = no torch on this camera, else on/off
  const stackRef = useRef(stack); stackRef.current = stack;
  const lastAdd = useRef({ code: '', t: 0 });
  const paused = useRef(false);
  paused.current = !!found || typing || busyPhoto || review;

  const addToTray = useCallback((x, n = 1) => {
    setTray(t => { const cur = t || [], i = cur.findIndex(y => y.k === x.k); return i >= 0 ? cur.map((y, j) => (j === i ? { ...y, qty: y.qty + n } : y)) : [...cur, { k: x.k, qty: n }]; });
    haptic('success');
    setFlash({ text: `${x.num} · ${versionTag(d.cat, x)}`, price: x.mine ? null : x.m, id: Date.now() });
  }, [d.cat]);
  useEffect(() => { if (!flash) return undefined; const t = setTimeout(() => setFlash(f => (f && f.id === flash.id ? null : f)), 1800); return () => clearTimeout(t); }, [flash]);

  // Where the card outline sits on screen (also used to know which part of the picture to read)
  const top = ins.top + 64, bottom = ins.bottom + 150;
  const fw = Math.min(W * 0.8, (H - top - bottom) * CARD, 440), fh = fw / CARD;
  const fx = (W - fw) / 2, fy = top + Math.max(0, (H - top - bottom - fh) / 2);
  const frame = useRef({});
  frame.current = { W, H, fx, fy, fw, fh };

  // card number -> catalog versions (TCGplayer cards plus your own JP/other cards)
  const byNum = useMemo(() => {
    const m = new Map();
    for (const x of [...(d.cat?.list || []), ...d.custom]) {
      const n = String(x.num || '').toUpperCase();
      if (n) (m.get(n) || m.set(n, []).get(n)).push(x);
    }
    return m;
  }, [d.cat, d.custom]);
  const byNumRef = useRef(byNum);
  byNumRef.current = byNum;
  const names = useMemo(() => nameIndex(byNum), [byNum]);
  const namesRef = useRef(names);
  namesRef.current = names;

  // show the results for one number, or for several (a card name printed on more than one card)
  const show = useCallback((codes, also = [], title = null, auto = false) => {
    codes = [].concat(codes);
    const list = codes.flatMap(k => byNumRef.current.get(k) || []).sort((a, b) => (b.m ?? -1) - (a.m ?? -1));
    const label = title || codes[0];
    if (auto && stackRef.current) {
      if (lastAdd.current.code === label && Date.now() - lastAdd.current.t < 4000) return;   // same card still in view
      lastAdd.current = { code: label, t: Date.now() };
      if (list.length === 1) { addToTray(list[0]); setSeen(''); return; }
    }
    haptic(auto ? 'success' : 'light');
    setFound({ code: label, codes, list, also });
    setSeen('');
    picks.current[label] = codes;
    setHistory(h => [label, ...h.filter(x => x !== label)].slice(0, 12));
  }, [addToTray]);
  const picks = useRef({});

  // camera on, camera off when leaving
  useEffect(() => {
    if (Platform.OS !== 'web' || !navigator.mediaDevices?.getUserMedia) { setCam('none'); return undefined; }
    let alive = true;
    navigator.mediaDevices.getUserMedia({ audio: false, video: { facingMode: { ideal: 'environment' }, width: { ideal: 3840 }, height: { ideal: 2160 } } })
      .then(async s => {
        if (!alive) { s.getTracks().forEach(t => t.stop()); return; }
        stream.current = s;
        const v = video.current;
        v.srcObject = s;
        v.setAttribute('playsinline', ''); v.muted = true;
        await v.play().catch(() => {});
        try { await s.getVideoTracks()[0].applyConstraints({ advanced: [{ focusMode: 'continuous' }] }); } catch {}
        try { const cap = s.getVideoTracks()[0].getCapabilities?.(); if (cap && cap.torch) setTorch(false); } catch {}
        setCam('on');
      })
      .catch(e => setCam(e && e.name === 'NotAllowedError' ? 'blocked' : 'none'));
    return () => { alive = false; stream.current?.getTracks().forEach(t => t.stop()); };
  }, []);

  // load the reader (first time ~7 MB, then kept by the browser)
  useEffect(() => {
    if (Platform.OS !== 'web') return;
    getReader(setLoad).then(setReader).catch(e => setReadErr(e.message || String(e)));
  }, []);

  // read loop: alternate the card's number corner and the whole outline (for close-ups)
  useEffect(() => {
    if (!reader || cam !== 'on') return undefined;
    let alive = true, n = 0, lastRead = Date.now(), wl = true;
    const recent = [], texts = [];
    const setWhitelist = async on => {                // numbers: capitals/digits only; names: anything
      if (on === wl) return;
      await reader.setParameters({ tessedit_char_whitelist: on ? 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' : '' });
      wl = on;
    };
    const tick = async () => {
      if (!alive) return;
      const v = video.current;
      if (paused.current || !v || !v.videoWidth) { lastRead = Date.now(); setTimeout(tick, 250); return; }
      try {
        const { W: cw, H: ch, fx: x, fy: y, fw: w, fh: h } = frame.current;
        const s = Math.max(cw / v.videoWidth, ch / v.videoHeight);    // video is shown "cover"
        const ox = (cw - v.videoWidth * s) / 2, oy = (ch - v.videoHeight * s) / 2;
        const vx = (x - ox) / s, vy = (y - oy) / s, vw = w / s, vh = h / s;
        // a cycle of 4: the tight number strip, the name line (plain text), the whole outline (close-ups /
        // a card held off-centre), and the lower half (name + number when the card sits small or high)
        const mode = n++ % 4, plain = mode === 1 || mode === 3;
        await setWhitelist(!plain);
        const canvas = mode === 0 ? grab(v, vx + vw * 0.45, vy + vh * 0.87, vw * 0.57, vh * 0.13, 300)
          : mode === 1 ? grab(v, vx + vw * 0.05, vy + vh * 0.82, vw * 0.9, vh * 0.18, 240)
          : mode === 2 ? grab(v, vx - vw * 0.05, vy - vh * 0.03, vw * 1.1, vh * 1.06, 1500)
          : grab(v, vx - vw * 0.04, vy + vh * 0.5, vw * 1.08, vh * 0.53, 700);
        const { data } = await reader.recognize(canvas);
        const codes = findCodes(data.text, byNumRef.current);
        if (plain) { texts.push(data.text); while (texts.length > 2) texts.shift(); }
        if (codes.length) lastRead = Date.now();
        setStuck(Date.now() - lastRead > 6000);
        const dbg = typeof window !== 'undefined' && window.__scanDebug;   // test hook (see the scanner tests)
        if (dbg) { dbg.reads.push(codes); if (plain) dbg.texts = [...texts]; if (dbg.noStop) { setTimeout(tick, 80); return; } }
        recent.push(...(codes.length ? codes : ['']));
        while (recent.length > 6) recent.shift();
        const got = decide(recent, texts, byNumRef.current, namesRef.current);
        if (got && !paused.current) {
          recent.length = 0; texts.length = 0;
          show(got.hits, got.also, got.title, true);
        } else if (codes[0]) setSeen(codes[0]);
      } catch {}
      setTimeout(tick, 80);
    };
    tick();
    return () => { alive = false; };
  }, [reader, cam, show]);

  // photo fallback: take or pick a picture, read the corner and then the whole picture
  const onPhoto = async e => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setBusyPhoto(true);
    try {
      const r = reader || await getReader(setLoad);
      const img = await new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = URL.createObjectURL(file); });
      const iw = img.naturalWidth, ih = img.naturalHeight;
      const tries = [[iw * 0.45, ih * 0.86, iw * 0.57, ih * 0.14, 300], [iw * 0.3, ih * 0.75, iw * 0.7, ih * 0.25, 500], [0, 0, iw, ih, 2000]];
      let code = null;
      for (const [x, y, w, h, out] of tries) {
        const { data } = await r.recognize(grab(img, x, y, w, h, out));
        code = findCodes(data.text, byNumRef.current)[0] || null;
        if (code) break;
      }
      if (code) show(code);
      else setFound({ code: null, list: [] });
    } catch (err) {
      setReadErr(err.message || String(err));
    } finally { setBusyPhoto(false); }
  };

  const lookUp = () => {
    const raw = typed.trim().toUpperCase().replace(/\s+/g, '');
    const code = findCodes(raw, byNum)[0] || findCodes(raw)[0] || raw;
    setTyping(false); setTyped('');
    if (byNum.has(code)) show(code); else setFound({ code, list: [] });
  };

  const status = !d.cat ? 'Loading prices…'
    : readErr ? readErr
    : !reader ? `Getting the card reader ready${load ? ` · ${Math.round(load * 100)}%` : ''}${load < 0.99 ? ' (first time only)' : ''}`
    : cam === 'starting' ? 'Starting the camera…'
    : cam === 'blocked' ? 'Camera access is off. Allow it for this site, or use Photo below.'
    : cam === 'none' ? 'No camera here. Use Photo or type the number below.'
    : busyPhoto ? 'Reading your photo…'
    : seen ? `Reading… ${seen}?`
    : stuck ? 'Still looking. Move closer so the number in the dashed box is bigger, and tilt away from glare.'
    : stack ? 'Stack mode: hold each card in the outline. It’s added when read, then show the next.'
    : 'Fill the outline with the card, number in the dashed box. Hold still.';

  const pill = { flexDirection: 'row', alignItems: 'center', gap: 7, paddingHorizontal: 16, height: 44, borderRadius: 22, backgroundColor: 'rgba(26,32,28,0.92)' };

  return (
    <View style={{ flex: 1, backgroundColor: '#000' }}>
      {Platform.OS === 'web' ? <video ref={video} playsInline muted autoPlay
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', background: '#000' }} /> : null}

      {/* dim everything except the card outline */}
      <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: 0, right: 0, height: fy, backgroundColor: 'rgba(0,0,0,0.55)' }} />
      <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: fy + fh, right: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.55)' }} />
      <View pointerEvents="none" style={{ position: 'absolute', left: 0, top: fy, width: fx, height: fh, backgroundColor: 'rgba(0,0,0,0.55)' }} />
      <View pointerEvents="none" style={{ position: 'absolute', left: fx + fw, top: fy, right: 0, height: fh, backgroundColor: 'rgba(0,0,0,0.55)' }} />
      <View pointerEvents="none" style={{ position: 'absolute', left: fx, top: fy, width: fw, height: fh, borderRadius: fw * 0.05, borderWidth: 2, borderColor: seen ? c.accent : 'rgba(242,245,240,0.85)' }}>
        {/* where the number is */}
        <View style={{ position: 'absolute', right: '3%', bottom: '2%', width: '52%', height: '10%', borderRadius: 8, borderWidth: 1.5, borderStyle: 'dashed', borderColor: c.accent, opacity: 0.9 }} />
      </View>

      {/* top bar */}
      <View style={{ position: 'absolute', top: ins.top + 10, left: 14, right: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))} accessibilityLabel="Close scanner" hitSlop={8}
          style={{ width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(26,32,28,0.92)' }}>
          <Ionicons name="close" size={24} color={c.ink} />
        </Pressable>
        <T w="bold" size={16}>{stack ? 'Scan a stack' : 'Scan a card'}</T>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {torch != null ? <Pressable onPress={async () => { try { await stream.current.getVideoTracks()[0].applyConstraints({ advanced: [{ torch: !torch }] }); setTorch(!torch); } catch {} }}
            accessibilityLabel={torch ? 'Turn the light off' : 'Turn the light on'} hitSlop={6}
            style={{ width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: torch ? c.accent : 'rgba(26,32,28,0.92)' }}>
            <Ionicons name={torch ? 'flashlight' : 'flashlight-outline'} size={20} color={torch ? c.onAccent : c.ink} />
          </Pressable> : null}
          <Pressable onPress={() => { setStack(!stack); haptic(); }} accessibilityRole="switch" accessibilityState={{ checked: !!stack }} accessibilityLabel="Stack mode: scan many cards in a row"
            style={{ height: 44, paddingHorizontal: 14, borderRadius: 22, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: stack ? c.accent : 'rgba(26,32,28,0.92)' }}>
            <Ionicons name="layers-outline" size={18} color={stack ? c.onAccent : c.ink} />
            <T w="bold" size={13.5} style={{ color: stack ? c.onAccent : c.ink }}>Stack</T>
          </Pressable>
        </View>
      </View>
      {flash ? <View pointerEvents="none" style={{ position: 'absolute', top: fy + fh / 2 - 34, left: 0, right: 0, alignItems: 'center' }}>
        <View style={{ paddingHorizontal: 18, paddingVertical: 10, borderRadius: 16, backgroundColor: c.accent, alignItems: 'center', maxWidth: '86%' }}>
          <T w="bold" size={15} style={{ color: c.onAccent }} numberOfLines={1}>✓ {flash.text}</T>
          {flash.price != null ? <T w="semi" size={13} style={{ color: c.onAccent }}>{d.money(flash.price)} · added to stack</T> : null}
        </View>
      </View> : null}

      {/* status + recent scans + buttons */}
      <View style={{ position: 'absolute', left: 0, right: 0, bottom: ins.bottom + 18, alignItems: 'center', gap: 12, paddingHorizontal: 16 }}>
        <View style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 12, backgroundColor: 'rgba(10,13,11,0.82)', maxWidth: 420 }}>
          <T size={13.5} w="semi" style={{ textAlign: 'center', color: readErr || cam === 'blocked' ? c.down : c.ink }}>{status}</T>
        </View>
        {history.length ? <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ maxWidth: '100%', flexGrow: 0 }}>
          {history.map(h => <Pressable key={h} onPress={() => show(picks.current[h] || h, [], picks.current[h] && picks.current[h].length > 1 ? h : null)} style={{ paddingHorizontal: 12, height: 32, borderRadius: 16, justifyContent: 'center', backgroundColor: 'rgba(26,32,28,0.92)' }}>
            <T size={12.5} w="semi">{h}</T></Pressable>)}
        </ScrollView> : null}
        {tray && tray.length ? <TrayBar tray={tray} onOpen={() => setReview(true)} /> : null}
        <View style={{ flexDirection: 'row', gap: 10 }}>
          <Pressable onPress={() => fileIn.current && fileIn.current.click()} style={pill} accessibilityRole="button">
            <Ionicons name="image-outline" size={18} color={c.ink} /><T w="semi" size={14}>Photo</T>
          </Pressable>
          <Pressable onPress={() => setTyping(true)} style={pill} accessibilityRole="button">
            <Ionicons name="keypad-outline" size={18} color={c.ink} /><T w="semi" size={14}>Type number</T>
          </Pressable>
        </View>
      </View>
      {Platform.OS === 'web' ? <input ref={fileIn} type="file" accept="image/*" onChange={onPhoto} style={{ display: 'none' }} /> : null}

      {typing ? <Sheet onClose={() => setTyping(false)} ins={ins}>
        <T w="bold" size={17}>Type the card number</T>
        <T mute size={13}>It's in the bottom-right corner, e.g. OP13-120, EB01-023, ST10-002, P-105.</T>
        <TextInput value={typed} onChangeText={setTyped} autoFocus autoCapitalize="characters" autoCorrect={false} onSubmitEditing={lookUp} returnKeyType="search"
          placeholder="OP13-120" placeholderTextColor={c.mute} keyboardAppearance="dark"
          style={{ height: 50, borderRadius: 14, backgroundColor: c.soft, paddingHorizontal: 16, color: c.ink, fontFamily: F.bold, fontSize: 18, letterSpacing: 1, outlineStyle: 'none' }} />
        <Pressable onPress={lookUp} style={{ height: 48, borderRadius: 24, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
          <T w="bold" size={15} style={{ color: c.onAccent }}>Look up</T>
        </Pressable>
      </Sheet> : null}

      {found ? <Sheet onClose={() => setFound(null)} ins={ins} tall>
        <Results found={found} stack={stack} onAgain={() => setFound(null)} onType={() => { setFound(null); setTyping(true); }}
          onPick={k => show(k, [...(found.codes || [found.code]), ...(found.also || [])].filter(x => x && x !== k))}
          onStack={x => { addToTray(x); setFound(null); }} />
      </Sheet> : null}

      {review ? <Sheet onClose={() => setReview(false)} ins={ins} tall>
        <Review tray={tray || []} setTray={setTray} onDone={() => { setReview(false); }} />
      </Sheet> : null}
    </View>
  );
}

function Sheet({ children, onClose, ins, tall }) {
  const c = useTheme();
  return (
    <View style={{ position: 'absolute', inset: 0, justifyContent: 'flex-end' }}>
      <Pressable onPress={onClose} style={{ position: 'absolute', inset: 0, backgroundColor: 'rgba(0,0,0,0.35)' }} accessibilityLabel="Close" />
      <View style={{ maxHeight: tall ? '72%' : '60%', backgroundColor: c.panel, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingTop: 10, paddingBottom: ins.bottom + 16, width: '100%', maxWidth: 640, alignSelf: 'center' }}>
        <View style={{ alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: c.raise, marginBottom: 12 }} />
        <ScrollView contentContainerStyle={{ paddingHorizontal: 18, gap: 12 }} keyboardShouldPersistTaps="handled">{children}</ScrollView>
      </View>
    </View>
  );
}

function Results({ found, onAgain, onType, onPick, onStack, stack }) {
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const { code, list } = found;
  const nameOf = k => { const x = (d.byNum.get(k) || [])[0]; return x ? clean(x.n).replace(/\s*\([^)]*\)/g, '') : ''; };
  const ownCount = k => d.owned.filter(o => o.card === k && o.status !== 'sold').reduce((n, o) => n + (Number(o.qty) || 1), 0);
  // versions side by side, big enough to compare the art
  const sheetW = Math.min(width, 640) - 36, cols = list.length >= 5 && sheetW > 420 ? 3 : list.length === 1 ? 1 : 2;
  const tileW = cols === 1 ? Math.min(180, sheetW * 0.45) : Math.floor((sheetW - 12 * (cols - 1)) / cols);
  return (
    <>
      {code && list.length ? <>
        <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <T w="bold" size={22}>{code}</T>
          <T mute size={13}>{list.length === 1 ? '1 version' : `${list.length} versions · highest first`}</T>
        </View>
        {list.length > 1 ? <T mute size={12.5}>Which one is in your hand? Compare the art and the label under each.</T> : null}
        {found.also && found.also.length ? <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 }}>
          <T mute size={12.5}>Not this one? Also read:</T>
          {found.also.map(a => <Pressable key={a} onPress={() => onPick(a)} style={{ paddingHorizontal: 12, height: 32, borderRadius: 16, justifyContent: 'center', backgroundColor: c.soft }}>
            <T w="semi" size={12.5}>{[a, nameOf(a)].filter(Boolean).join(' · ')}</T></Pressable>)}
        </View> : null}
        <View style={{ flexDirection: cols === 1 ? 'row' : 'row', flexWrap: 'wrap', gap: 12, rowGap: 18 }}>
          {list.map(x => {
            const own = ownCount(x.k), set = x.mine ? x.setName : d.cat?.byId[x.g]?.code, sold = d.comps[x.k]?.sales?.[0];
            const add = () => { setPref('didScan', true); return stack ? onStack(x) : router.push({ pathname: '/item/[id]', params: { id: 'new', card: x.k } }); };
            return (
              <View key={x.k} style={cols === 1 ? { flexDirection: 'row', gap: 14, flex: 1 } : { width: tileW, gap: 6 }}>
                <Pressable onPress={add} accessibilityRole="button" accessibilityLabel={`${stack ? 'Add to stack' : 'Add'}: ${clean(x.n)}, ${versionTag(d.cat, x)}`}
                  style={({ pressed }) => ({ opacity: pressed ? 0.7 : 1 })}>
                  <CardArt k={x.k} photo={d.photoOf(x.k)} num={x.num} width={tileW} big />
                </Pressable>
                <View style={{ gap: 3, flex: cols === 1 ? 1 : undefined }}>
                  <T w="bold" size={13.5} numberOfLines={2} style={{ color: c.accent }}>{versionTag(d.cat, x)}</T>
                  <T mute size={12} numberOfLines={1}>{[set, x.r, own ? `you own ${own}` : null].filter(Boolean).join(' · ')}</T>
                  <T w="bold" size={16}>{x.mine ? 'Your card' : d.money(x.m)}</T>
                  {sold ? <T mute size={11.5} numberOfLines={1}>eBay sold {d.money(sold.price)} · {sold.sold}</T> : null}
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 }}>
                    <Pressable onPress={add} accessibilityRole="button"
                      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 4, height: 38, paddingHorizontal: 12, borderRadius: 19, backgroundColor: pressed ? c.raise : c.accent })}>
                      <Ionicons name="add" size={18} color={c.onAccent} /><T w="bold" size={13} style={{ color: c.onAccent }}>{stack ? 'Stack' : 'Add'}</T>
                    </Pressable>
                    <Pressable onPress={() => router.push({ pathname: '/card/[k]', params: { k: x.k } })} hitSlop={8} accessibilityRole="link">
                      <T w="semi" size={13} style={{ color: c.link }}>Prices</T>
                    </Pressable>
                  </View>
                </View>
              </View>
            );
          })}
        </View>
      </> : <>
        <T w="bold" size={18}>{code ? `${code} isn't in the price list` : "Couldn't find a card number"}</T>
        <T mute size={13.5}>{code
          ? 'Check the number, or add it as your own card from Profile → Your own cards.'
          : 'Try again closer, with less glare (or the light on), so the number in the bottom-right corner is sharp. Or type it.'}</T>
      </>}
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
        <Pressable onPress={onAgain} style={{ flex: 1, height: 48, borderRadius: 24, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
          <T w="bold" size={15} style={{ color: c.onAccent }}>Scan another</T>
        </Pressable>
        <Pressable onPress={onType} style={{ height: 48, paddingHorizontal: 18, borderRadius: 24, backgroundColor: c.soft, alignItems: 'center', justifyContent: 'center' }}>
          <T w="semi" size={14}>Type it</T>
        </Pressable>
      </View>
    </>
  );
}

// "5 cards · A$123 · Review" above the scanner buttons
function TrayBar({ tray, onOpen }) {
  const d = useData(), c = useTheme();
  const n = tray.reduce((a, t) => a + t.qty, 0);
  const tot = tray.reduce((a, t) => a + (d.card(t.k)?.m || 0) * t.qty, 0);
  return (
    <Pressable onPress={onOpen} accessibilityRole="button" accessibilityLabel={`Stack: ${n} cards. Review and add`}
      style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, height: 50, paddingLeft: 16, paddingRight: 6, borderRadius: 25, backgroundColor: c.accent, opacity: pressed ? 0.85 : 1 })}>
      <Ionicons name="layers" size={18} color={c.onAccent} />
      <T w="bold" size={14.5} style={{ color: c.onAccent }}>{n} {n === 1 ? 'card' : 'cards'} · {d.money(tot)}</T>
      <View style={{ height: 38, paddingHorizontal: 14, borderRadius: 19, backgroundColor: c.onAccent, justifyContent: 'center' }}>
        <T w="bold" size={13.5} style={{ color: c.accent }}>Review & add</T>
      </View>
    </Pressable>
  );
}

// Check the stack, set condition / language / group once, add everything in one go
function Review({ tray, setTray, onDone }) {
  const d = useData(), c = useTheme();
  const [cond, setCond] = useState('Raw'), [lang, setLang] = useState('EN'), [group, setGroup] = useState(''), [paid, setPaid] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => { getPref('lastAdd', null).then(l => { if (l) { if (l.group) setGroup(l.group); if (l.lang) setLang(l.lang); if (l.cond && !['Sealed', 'Opened'].includes(l.cond)) setCond(l.cond); } }); }, []);
  const groups = [...new Set(d.owned.map(o => o.group || 'Other'))].sort();
  const n = tray.reduce((a, t) => a + t.qty, 0);
  const bump = (k, by) => setTray(t => t.map(x => (x.k === k ? { ...x, qty: x.qty + by } : x)).filter(x => x.qty > 0));
  const add = async () => {
    setBusy(true);
    try {
      const g = group.trim() || 'Other', p = parseFloat(String(paid).replace(',', '.'));
      const out = [];
      for (const t of tray) {
        const x = d.card(t.k); if (!x) continue;
        const old = d.owned.find(o => o.card === t.k && o.status !== 'sold' && (o.lang || 'EN') === lang && o.cond === cond && (o.group || 'Other') === g);
        if (old) out.push({ ...old, qty: (Number(old.qty) || 1) + t.qty });
        else out.push({ id: newId(), card: t.k, name: clean(x.n), qty: t.qty, kind: x.t === 'sealed' ? 'Sealed' : x.t === 'don' ? 'DON!!' : 'Card', cond, lang, group: g,
          paid: isNaN(p) ? null : p, value: null, notes: '', status: 'owned', soldFor: null, added: today() });
      }
      await d.saveMany(out);
      setPref('lastAdd', { group: g, cond, lang });
      setPref('didScan', true);
      haptic('success');
      toast(`Added ${n} ${n === 1 ? 'card' : 'cards'} to ${g}`);
      setTray([]); onDone();
    } catch (e) { toast(e.message || String(e)); } finally { setBusy(false); }
  };
  return (
    <>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' }}>
        <T w="bold" size={20}>Your stack</T>
        <Pressable onPress={() => setTray([])} hitSlop={8}><T mute size={13}>Clear</T></Pressable>
      </View>
      {tray.map(t => {
        const x = d.card(t.k); if (!x) return null;
        return (
          <View key={t.k} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <CardArt k={x.k} photo={d.photoOf(x.k)} num={x.num} width={36} />
            <View style={{ flex: 1 }}>
              <T w="semi" size={14} numberOfLines={1}>{clean(x.n)}</T>
              <T mute size={12} numberOfLines={1}>{x.num} · {versionTag(d.cat, x)} · {x.mine ? 'your card' : d.money(x.m)}</T>
            </View>
            <Step icon="remove" onPress={() => bump(t.k, -1)} label="One fewer" />
            <T w="bold" size={15} style={{ width: 22, textAlign: 'center' }}>{t.qty}</T>
            <Step icon="add" onPress={() => bump(t.k, 1)} label="One more" />
          </View>
        );
      })}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 6 }}>
        <Choice label="Condition" value={cond} onChange={setCond} options={['Raw', 'PSA 10', 'PSA 9', 'Other graded']} />
        <Choice label="Language" value={lang} onChange={setLang} options={['EN', 'JP']} />
        {groups.length ? <Choice label="Group" value={group} onChange={setGroup} options={groups} /> : null}
        <Field label={groups.length ? 'Or a new group' : 'Group'} value={group} onChangeText={setGroup} placeholder="Binder" />
        <Field label="Paid each, A$ (optional)" value={paid} onChangeText={setPaid} keyboardType="decimal-pad" />
      </View>
      {!d.session ? <Pressable onPress={() => router.push({ pathname: '/account', params: { back: '1' } })} style={{ height: 50, borderRadius: 25, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center' }}>
          <T w="bold" size={15} style={{ color: c.onAccent }}>Sign in to save your stack</T></Pressable>
        : <Pressable onPress={add} disabled={busy || !n} style={{ height: 50, borderRadius: 25, backgroundColor: c.accent, alignItems: 'center', justifyContent: 'center', opacity: busy || !n ? 0.5 : 1 }}>
          <T w="bold" size={15} style={{ color: c.onAccent }}>{busy ? 'Adding…' : `Add ${n} to my collection`}</T>
        </Pressable>}
      <T mute size={12}>Your stack is kept on this phone until you add it, even if you close the scanner.</T>
    </>
  );
}

function Step({ icon, onPress, label }) {
  const c = useTheme();
  return (
    <Pressable onPress={() => { haptic(); onPress(); }} accessibilityRole="button" accessibilityLabel={label} hitSlop={4}
      style={({ pressed }) => ({ width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: pressed ? c.raise : c.soft })}>
      <Ionicons name={icon} size={18} color={c.ink} />
    </Pressable>
  );
}
