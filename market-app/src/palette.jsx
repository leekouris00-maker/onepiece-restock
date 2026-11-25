// Command palette (Ctrl/⌘ K, or the ⚡ button): type what you want to do or a card name, Enter to go.
// Shortcut sheet (?): every key for the page you're on and the whole app.
// KeyHost is mounted once by the app: it installs the keyboard and owns these two overlays.
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Pressable, ScrollView, TextInput, View, useWindowDimensions } from 'react-native';
import { router } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData, clean } from './data';
import { F, useTheme } from './theme';
import { CardArt, T } from './ui';
import { on } from './bus';
import { usePref } from './prefs';
import { searchCards, versionTag } from './find';
import { useModalPause } from './modal';
import { COMMANDS, GROUPS, PAGE_KEYS, commandsFor, installFocusStyle, keyParts, pageKeys, useGlobalKeys, web } from './keys';
import { FeedbackSheet } from './feedback';
import { useWide } from './layout';

// Keyboard keys drawn as little keycaps: <Keys k="g h" /> → [G] then [H]
export function Keys({ k, small }) {
  const c = useTheme();
  if (!k) return null;
  const list = Array.isArray(k) ? k : [k];
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      {list.map((one, i) => (
        <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
          {i ? <T size={11} mute>or</T> : null}
          {keyParts(one).map((p, j) => (
            <View key={j} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
              {j ? <T size={11} mute>then</T> : null}
              <View style={{ minWidth: small ? 20 : 24, height: small ? 20 : 24, paddingHorizontal: 6, borderRadius: 6, borderWidth: 1, borderBottomWidth: 2, borderColor: c.raise, backgroundColor: c.soft, alignItems: 'center', justifyContent: 'center' }}>
                <T size={small ? 11 : 12} w="bold">{p}</T>
              </View>
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

// Centred box on a computer, near the top on a phone (so the keyboard doesn't cover it)
function Dialog({ open, onClose, children, width = 640, label }) {
  const c = useTheme(), wide = useWide(), ins = useSafeAreaInsets(), { height } = useWindowDimensions();
  useModalPause(open);
  return (
    <Modal visible={open} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable onPress={onClose} accessibilityLabel="Close" style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.62)', paddingTop: wide ? Math.round(height * 0.11) : ins.top + 10, paddingHorizontal: 10, alignItems: 'center' }}>
        <Pressable accessibilityRole="none" aria-label={label} style={{ width: '100%', maxWidth: width, maxHeight: wide ? height * 0.78 : height - ins.top - 30, borderRadius: 20, backgroundColor: c.panel, overflow: 'hidden',
          borderWidth: 1, borderColor: c.line, shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 30 }}>
          {children}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const words = s => String(s || '').toLowerCase();

function Palette({ open, onClose }) {
  const d = useData(), c = useTheme(), wide = useWide();
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const [recent, setRecent] = usePref('palRecent', []);
  const input = useRef(null), scroller = useRef(null);
  useEffect(() => { if (open) { setQ(''); setSel(0); setTimeout(() => input.current && input.current.focus(), 60); } }, [open]);

  const items = useMemo(() => {
    if (!open) return [];
    const s = q.trim().toLowerCase();
    const cmds = commandsFor(d);
    const asItem = x => ({ key: 'c:' + x.id, kind: 'cmd', icon: x.icon, label: x.label, sub: x.info ? x.where : x.sub, keys: x.keys,
      run: () => { setRecent(r => [x.id, ...(r || []).filter(i => i !== x.id)].slice(0, 5)); if (x.info) router.push('/help'); else x.run(d); } });
    if (!s) {
      const rec = (recent || []).map(id => cmds.find(x => x.id === id)).filter(Boolean);
      const rest = cmds.filter(x => !x.info && !rec.includes(x) && x.group !== 'Go to').slice(0, 12);
      return [...rec.map(x => ({ ...asItem(x), head: rec[0] === x ? 'Recent' : null })), ...rest.map((x, i) => ({ ...asItem(x), head: i === 0 ? 'Things you can do' : null }))];
    }
    const toks = s.split(/\s+/);
    const scored = [];
    for (const x of cmds) {
      const hay = words(`${x.label} ${x.sub} ${x.group} ${x.where || ''} ${x.id}`);
      if (!toks.every(t => hay.includes(t))) continue;
      const l = words(x.label);
      scored.push([l.startsWith(s) ? 3 : l.includes(s) ? 2 : 1, x]);
    }
    const out = scored.sort((a, b) => b[0] - a[0]).slice(0, 8).map(([, x], i) => ({ ...asItem(x), head: i === 0 ? 'Functions' : null }));
    if (s.length >= 2 && d.index) {
      searchCards(d.index, s, 6).forEach((x, i) => out.push({ key: 'k:' + x.k, kind: 'card', card: x, label: clean(x.n),
        sub: [x.num, versionTag(d.cat, x), x.mine ? null : d.money(x.m)].filter(Boolean).join(' · '),
        run: () => router.push({ pathname: '/card/[k]', params: { k: x.k } }), head: i === 0 ? 'Cards' : null }));
      const sets = (d.cat?.sets || []).filter(x => words(`${x.code} ${x.name}`).includes(s)).slice(0, 4);
      sets.forEach((x, i) => out.push({ key: 's:' + x.id, kind: 'set', icon: 'albums-outline', label: x.name, sub: [x.code, x.date].filter(Boolean).join(' · '),
        run: () => router.push({ pathname: '/set/[id]', params: { id: x.id } }), head: i === 0 ? 'Sets' : null }));
      const mine = (d.owned || []).filter(o => o.status !== 'sold' && words(`${o.name} ${o.num || ''} ${o.group || ''}`).includes(s)).slice(0, 4);
      mine.forEach((o, i) => out.push({ key: 'o:' + o.id, kind: 'own', own: o, label: clean(o.name), sub: [o.group || 'Other', `×${o.qty || 1}`, d.aud((d.unitAt(o, 0) || 0) * (Number(o.qty) || 1))].join(' · '),
        run: () => router.push({ pathname: '/item/[id]', params: { id: o.id } }), head: i === 0 ? 'In your collection' : null }));
    }
    return out;
  }, [open, q, d.index, d.owned, d.session, recent]);

  useEffect(() => { setSel(0); }, [q]);
  const go = it => { if (!it) return; onClose(); setTimeout(() => it.run(), 30); };
  const move = by => setSel(i => {
    const n = items.length; if (!n) return 0;
    const j = (i + by + n) % n;
    if (web) setTimeout(() => { const el = document.getElementById('pal-' + j); el && el.scrollIntoView({ block: 'nearest' }); }, 0);
    return j;
  });

  return (
    <Dialog open={open} onClose={onClose} label="Search all functions">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 16, minHeight: 58, borderBottomWidth: 1, borderBottomColor: c.line }}>
        <Ionicons name="flash" size={19} color={c.accent} />
        <TextInput ref={input} value={q} onChangeText={setQ} placeholder="What do you want to do? Or a card name / number" placeholderTextColor={c.mute}
          autoCorrect={false} autoCapitalize="none" returnKeyType="go" keyboardAppearance="dark" accessibilityLabel="Search all functions and cards"
          onSubmitEditing={() => go(items[sel])}
          onKeyPress={e => {
            const k = e.nativeEvent.key;
            if (k === 'ArrowDown') { e.preventDefault && e.preventDefault(); move(1); }
            else if (k === 'ArrowUp') { e.preventDefault && e.preventDefault(); move(-1); }
            else if (k === 'Escape') { if (q) setQ(''); else onClose(); }
          }}
          style={{ flex: 1, color: c.ink, fontFamily: F.medium, fontSize: 16.5, minHeight: 56, outlineStyle: 'none' }} />
        {q ? <Pressable onPress={() => setQ('')} hitSlop={10} accessibilityLabel="Clear"><Ionicons name="close-circle" size={20} color={c.mute} /></Pressable>
          : <Pressable onPress={onClose} hitSlop={10} accessibilityLabel="Close">{wide ? <Keys k="escape" small /> : <T w="semi" size={14} style={{ color: c.accent }}>Close</T>}</Pressable>}
      </View>
      <ScrollView ref={scroller} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 8, paddingBottom: 10 }}>
        {!items.length ? <T mute style={{ padding: 18, textAlign: 'center' }}>{`Nothing matches “${q}”. Try fewer words, or a card number like op13 120.`}</T> : null}
        {items.map((it, i) => (
          <View key={it.key}>
            {it.head ? <T size={11.5} mute w="bold" caps style={{ paddingHorizontal: 10, paddingTop: i ? 12 : 6, paddingBottom: 4 }}>{it.head}</T> : null}
            <Pressable nativeID={'pal-' + i} onPress={() => go(it)} onHoverIn={() => setSel(i)} accessibilityRole="button"
              style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 50, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 12, backgroundColor: i === sel ? c.soft : 'transparent' }}>
              {it.card ? <CardArt k={it.card.k} photo={d.photoOf(it.card.k)} num={it.card.num} width={26} />
                : it.own ? <CardArt k={it.own.card} photo={d.ownPhoto(it.own)} num={it.own.num} width={26} />
                : <View style={{ width: 30, height: 30, borderRadius: 9, backgroundColor: i === sel ? c.accentDim : c.soft, alignItems: 'center', justifyContent: 'center' }}>
                    <Ionicons name={it.icon || 'ellipse-outline'} size={17} color={i === sel ? c.accent : c.ink} /></View>}
              <View style={{ flex: 1, minWidth: 0 }}>
                <T w="semi" size={14.5} numberOfLines={1}>{it.label}</T>
                {it.sub ? <T mute size={12.5} numberOfLines={1}>{it.sub}</T> : null}
              </View>
              {wide && it.keys ? <Keys k={it.keys[0]} small /> : i === sel && wide ? <T size={12} mute>Enter</T> : null}
            </Pressable>
          </View>
        ))}
      </ScrollView>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderTopWidth: 1, borderTopColor: c.line }}>
        <T size={12} mute>{wide ? '↑ ↓ to move · Enter to open · Esc to close' : 'Tap to open'}</T>
        <Pressable onPress={() => { onClose(); router.push('/help'); }} hitSlop={8} accessibilityRole="link"><T size={12.5} w="semi" style={{ color: c.accent }}>All functions</T></Pressable>
      </View>
    </Dialog>
  );
}

function CheatSheet({ open, onClose, here }) {
  const c = useTheme(), wide = useWide();
  const global = COMMANDS.filter(x => x.keys);
  const Row = ({ k, label }) => (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 34 }}>
      <T size={13.5} style={{ flex: 1 }}>{label}</T>
      <Keys k={k} small />
    </View>
  );
  const Col = ({ title, children }) => <View style={{ flex: 1, minWidth: 260, gap: 2 }}><T size={11.5} mute w="bold" caps style={{ marginBottom: 6 }}>{title}</T>{children}</View>;
  return (
    <Dialog open={open} onClose={onClose} width={940} label="Keyboard shortcuts">
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: c.line }}>
        <T w="bold" size={17}>Keyboard shortcuts</T>
        <Pressable onPress={onClose} hitSlop={10} accessibilityLabel="Close"><Keys k="escape" small /></Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: 20, gap: 22, flexDirection: wide ? 'row' : 'column', flexWrap: 'wrap' }}>
        {here && here.length ? <Col title="On this page">{here.map((x, i) => <Row key={i} k={x.keys} label={x.label} />)}</Col> : null}
        <Col title="Anywhere">
          {global.filter(x => !['Go to'].includes(x.group)).map(x => <Row key={x.id} k={x.keys} label={x.label} />)}
        </Col>
        <Col title="Go to">
          {global.filter(x => x.group === 'Go to').map(x => <Row key={x.id} k={x.keys} label={x.label} />)}
          <T size={12.5} mute style={{ marginTop: 8 }}>Shortcuts pause while you’re typing in a box; Esc leaves the box. They also work on an iPad with a keyboard.</T>
          <Pressable onPress={() => { onClose(); router.push('/help'); }} hitSlop={8} style={{ marginTop: 10 }}><T w="semi" size={13.5} style={{ color: c.accent }}>All functions and page shortcuts →</T></Pressable>
        </Col>
      </ScrollView>
    </Dialog>
  );
}

export function KeyHost() {
  const d = useData();
  const ref = useRef(d); ref.current = d;
  const [pal, setPal] = useState(false);
  const [cheat, setCheat] = useState(null);       // page keys captured when it opened
  const [fb, setFb] = useState(false);
  const [, setToured] = usePref('toured', null);
  useGlobalKeys(() => ref.current);
  useEffect(() => { installFocusStyle(); }, []);
  useEffect(() => on('palette', () => { setCheat(null); setPal(p => !p); }), []);
  useEffect(() => on('cheatsheet', () => { setPal(false); setCheat(pageKeys().filter(x => x.label)); }), []);
  useEffect(() => on('feedback', () => setFb(true)), []);
  useEffect(() => on('tour', () => setToured(false)), []);
  return (
    <>
      <Palette open={pal} onClose={() => setPal(false)} />
      <CheatSheet open={!!cheat} here={cheat} onClose={() => setCheat(null)} />
      <FeedbackSheet open={fb} onClose={() => setFb(false)} />
    </>
  );
}

export { GROUPS, PAGE_KEYS };
