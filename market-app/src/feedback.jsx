// "Report a problem" from any page (sent to the feedback table with the page and device), and the
// three-screen intro for first-time users.
import React, { useState } from 'react';
import { Linking, Modal, Platform, Pressable, View } from 'react-native';
import { usePathname } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Ionicons from '@expo/vector-icons/Ionicons';
import * as ImagePicker from 'expo-image-picker';
import { useData } from './data';
import { useTheme } from './theme';
import { Button, Field, Sheet, T } from './ui';
import { usePref } from './prefs';
import { useWide } from './layout';
import { toast } from './toast';
import { haptic } from './haptic';

const device = () => {
  if (Platform.OS !== 'web' || typeof navigator === 'undefined') return Platform.OS;
  const ua = navigator.userAgent || '', standalone = window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone;
  const os = /iPhone/.test(ua) ? 'iPhone' : /iPad/.test(ua) ? 'iPad' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac/.test(ua) ? 'Mac' : 'other';
  const ver = (ua.match(/OS (\d+[_\d]*)/) || [])[1];
  return `${os}${ver ? ' ' + ver.replace(/_/g, '.') : ''} · ${standalone ? 'home-screen app' : 'browser'} · ${window.innerWidth}×${window.innerHeight}`;
};

export function FeedbackSheet({ open, onClose }) {
  const d = useData(), c = useTheme(), path = usePathname();
  const [note, setNote] = useState(''), [uri, setUri] = useState(null), [busy, setBusy] = useState(false);
  const pick = async () => {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.85 });
    if (!r.canceled && r.assets?.[0]) setUri(r.assets[0].uri);
  };
  const send = async () => {
    setBusy(true);
    try {
      await d.sendFeedback({ note: note.trim(), page: path, uri, device: device() });
      haptic('success'); toast('Thanks! Your note was sent.'); setNote(''); setUri(null); onClose();
    } catch (e) {
      if (e.message === 'NOT_SET_UP') {
        // database not updated yet: hand it over as an email-style note instead
        const body = encodeURIComponent(`${note.trim()}\n\nPage: ${path}\nDevice: ${device()}`);
        Linking.openURL(`https://github.com/leekouris00-maker/onepiece-restock/issues/new?title=${encodeURIComponent('App feedback')}&body=${body}`);
        onClose();
      } else toast(e.message || String(e));
    } finally { setBusy(false); }
  };
  return (
    <Sheet open={open} onClose={onClose} title="Report a problem or idea">
      <T mute size={13.5}>Say what you did and what went wrong (or what you’d like). The page you’re on and your phone type are added for you.</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
        <Field label="What happened?" value={note} onChangeText={setNote} multiline numberOfLines={4} placeholder="I scanned OP13-120 and it picked the wrong version…" style={{ flexBasis: '100%' }} />
      </View>
      {d.session ? <Pressable onPress={pick} accessibilityRole="button" style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: 12, backgroundColor: pressed ? c.raise : c.soft })}>
        <Ionicons name={uri ? 'checkmark-circle' : 'image-outline'} size={20} color={uri ? c.accent : c.ink} />
        <T w="semi" size={14}>{uri ? 'Screenshot attached (tap to change)' : 'Attach a screenshot (optional)'}</T>
      </Pressable> : <T mute size={12.5}>Sign in to attach a screenshot.</T>}
      <T mute size={12}>Page: {path}</T>
      <Button disabled={busy || note.trim().length < 3} onPress={send} icon="send">{busy ? 'Sending…' : 'Send'}</Button>
    </Sheet>
  );
}

// Small round button in the corner of every page (can be switched off in Profile)
export function FeedbackButton() {
  const c = useTheme(), ins = useSafeAreaInsets(), wide = useWide(), path = usePathname();
  const [on] = usePref('fbButton', true);
  const [open, setOpen] = useState(false);
  if (!on || /^\/(scan|share)/.test(path)) return null;
  const tabs = ['/', '/search', '/market', '/portfolio', '/account'].includes(path);
  return (
    <>
      <Pressable onPress={() => setOpen(true)} accessibilityRole="button" accessibilityLabel="Report a problem"
        style={({ pressed }) => ({ position: 'absolute', ...(wide ? { right: 22 } : { left: 12 }), bottom: wide ? 22 : ins.bottom + (tabs ? 74 : 16), width: 40, height: 40, borderRadius: 20,
          alignItems: 'center', justifyContent: 'center', backgroundColor: pressed ? c.raise : 'rgba(35,42,37,0.92)', borderWidth: 1, borderColor: c.line, zIndex: 900 })}>
        <Ionicons name="chatbubble-ellipses-outline" size={19} color={c.mute} />
      </Pressable>
      <FeedbackSheet open={open} onClose={() => setOpen(false)} />
    </>
  );
}

const SLIDES = [
  { icon: 'scan', title: 'Scan a card', text: 'Point your camera at a card. You get every version of it with prices, and one tap adds it. Turn on Stack to scan a whole pile in a row.' },
  { icon: 'swap-horizontal', title: 'Quick changes', text: 'In Collection, swipe a row left for −1, +1 or Sold, or hold it for more. Everything can be undone.' },
  { icon: 'star', title: 'Watch prices', text: 'Star any card to follow it, and set a price alert. You’ll see it on Home when the price gets there.' },
];

export function Tour() {
  const c = useTheme();
  const [seen, setSeen] = usePref('toured', null);
  const [i, setI] = useState(0);
  if (seen !== false) return null;          // null = still loading, true = done
  const s = SLIDES[i], last = i === SLIDES.length - 1;
  const done = () => { setSeen(true); setI(0); };
  return (
    <Modal visible transparent animationType="fade" onRequestClose={done}>
      <View style={{ flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', alignItems: 'center', justifyContent: 'center', padding: 22 }}>
        <View style={{ width: '100%', maxWidth: 420, borderRadius: 26, backgroundColor: c.panel, padding: 26, gap: 14, alignItems: 'center' }}>
          <View style={{ width: 76, height: 76, borderRadius: 38, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={s.icon} size={36} color={c.accent} />
          </View>
          <T head size={24} style={{ textAlign: 'center' }}>{s.title}</T>
          <T mute size={15} style={{ textAlign: 'center', lineHeight: 22 }}>{s.text}</T>
          <View style={{ flexDirection: 'row', gap: 6, marginVertical: 4 }}>
            {SLIDES.map((_, j) => <View key={j} style={{ width: j === i ? 18 : 7, height: 7, borderRadius: 4, backgroundColor: j === i ? c.accent : c.raise }} />)}
          </View>
          <Button onPress={() => (last ? done() : setI(i + 1))} style={{ alignSelf: 'stretch' }}>{last ? 'Start' : 'Next'}</Button>
          {!last ? <Pressable onPress={done} hitSlop={10}><T mute size={14}>Skip</T></Pressable> : null}
        </View>
      </View>
    </Modal>
  );
}

// First launch: show the intro once (existing users who already have a collection skip it)
export function useTourStart() {
  const d = useData();
  const [seen, setSeen] = usePref('toured', null);
  React.useEffect(() => {
    if (seen !== null) return;
    const t = setTimeout(() => setSeen(d.owned.length > 0 ? true : false), 1500);
    return () => clearTimeout(t);
  }, [seen, d.owned.length]);
}
