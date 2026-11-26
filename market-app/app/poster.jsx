// Your wanted poster (27 Nov 2026): bounty, rank and collection at a glance, shareable as a picture.
// The design is our own (no One Piece artwork); the "photo" is your most valuable card.
import React, { useMemo, useState } from 'react';
import { Platform, Pressable, ScrollView, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { tcgImage, useData, useTrack } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, CardArt, Panel, T } from '../src/ui';
import { usePref } from '../src/prefs';
import { toast } from '../src/toast';
import { RANKS, berries, rankOf, usePoints } from '../src/points';
import { Bar, RankBadge } from '../src/bounty';

const INK = '#3b2a1a', PAPER = '#ead7aa', PAPER2 = '#d9c08a';
const SERIF = Platform.OS === 'web' ? 'Georgia, "Times New Roman", serif' : undefined;

export default function Poster() {
  const d = useData(), c = useTheme(), pts = usePoints();
  useTrack('poster');
  const email = d.session?.user?.email || '';
  const [name, setName] = usePref('posterName', '');
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const shown = (name || email.split('@')[0] || 'Collector').slice(0, 22);
  const b = pts.bounty || 0, r = rankOf(b);
  const live = d.owned.filter(o => o.status !== 'sold');
  const value = live.reduce((s, o) => s + (d.unitAt(o, 0) || 0) * (Number(o.qty) || 1), 0);
  const count = live.reduce((s, o) => s + (Number(o.qty) || 1), 0);
  const top = useMemo(() => live.filter(o => o.card && o.card.startsWith('t:')).sort((x, y) => (d.unitAt(y, 0) || 0) - (d.unitAt(x, 0) || 0))[0] || null, [d.owned, d.cat]);
  const done = [...(pts.sets || [])].filter(k => k.endsWith(':100')).length;
  const stats = `${d.aud(value)} collection · ${count.toLocaleString()} ${count === 1 ? 'card' : 'cards'}${done ? ` · ${done} ${done === 1 ? 'set' : 'sets'} complete` : ''}`;

  const share = async () => {
    if (Platform.OS !== 'web') { toast('Sharing the poster works in the web app for now'); return; }
    setBusy(true);
    try {
      const blob = await drawPoster({ name: shown, bounty: berries(b), rank: r.label, stats, img: top ? tcgImage(top.card, 400) : null });
      const file = new File([blob], 'my-bounty.png', { type: 'image/png' });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        try { await navigator.share({ files: [file], title: 'My bounty' }); } catch (e) { if (e?.name !== 'AbortError') throw e; }
      } else {
        const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'my-bounty.png'; a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        toast('Poster saved as a picture');
      }
    } catch (e) { toast(e.message || String(e)); } finally { setBusy(false); }
  };

  if (pts.mode === 'signedout') return (
    <View style={{ flex: 1, backgroundColor: c.bg, padding: 18, gap: 12 }}>
      <T w="bold" size={22}>Sign in to get a bounty</T>
      <Button onPress={() => router.push({ pathname: '/account', params: { back: '1' } })}>Sign in</Button>
    </View>
  );

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ padding: 18, paddingBottom: 60, gap: 16, width: '100%', maxWidth: 520, alignSelf: 'center' }}>
      {/* the poster */}
      <View accessibilityLabel={`Wanted poster: ${shown}, ${berries(b)}, ${r.label}`}
        style={{ backgroundColor: PAPER, borderRadius: 6, padding: 18, gap: 10, alignItems: 'center', borderWidth: 6, borderColor: PAPER2 }}>
        <T style={{ fontFamily: SERIF, fontSize: 56, lineHeight: 62, fontWeight: '900', color: INK, letterSpacing: 4 }}>WANTED</T>
        <View style={{ width: '100%', aspectRatio: 1.25, backgroundColor: '#5b4630', borderWidth: 3, borderColor: INK, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
          {top ? <CardArt k={top.card} num={top.num} width={150} big /> : <Ionicons name="help" size={90} color={PAPER} />}
        </View>
        <T style={{ fontFamily: SERIF, fontSize: 30, fontWeight: '800', color: INK, textTransform: 'uppercase', letterSpacing: 1 }} numberOfLines={1} adjustsFontSizeToFit>{shown}</T>
        <T style={{ fontFamily: SERIF, fontSize: 30, fontWeight: '900', color: INK }} numberOfLines={1} adjustsFontSizeToFit>{berries(b)}</T>
        <View style={{ height: 2, alignSelf: 'stretch', backgroundColor: INK, opacity: 0.5 }} />
        <T style={{ fontFamily: SERIF, fontSize: 18, fontWeight: '800', color: INK, letterSpacing: 3 }}>{r.label.toUpperCase()}</T>
        <T style={{ fontSize: 12.5, color: INK, opacity: 0.8, textAlign: 'center' }}>{stats}</T>
        <T style={{ fontSize: 10.5, color: INK, opacity: 0.6 }}>One Piece Market</T>
      </View>

      <View style={{ flexDirection: 'row', gap: 10 }}>
        <View style={{ flex: 1 }}><Button icon="share-outline" disabled={busy} onPress={share}>{busy ? 'Making the picture…' : 'Share poster'}</Button></View>
        <Button ghost icon="create-outline" onPress={() => setEditing(e => !e)}>Name</Button>
      </View>
      {editing ? <Panel>
        <T mute size={12.5}>The name on your poster (only you see it unless you share it).</T>
        <TextInput value={name} onChangeText={setName} placeholder={email.split('@')[0] || 'Your name'} placeholderTextColor={c.mute} maxLength={22} autoFocus
          onSubmitEditing={() => setEditing(false)} accessibilityLabel="Poster name"
          style={{ color: c.ink, backgroundColor: c.soft, borderRadius: 12, paddingHorizontal: 14, minHeight: 46, fontSize: 16 }} />
      </Panel> : null}

      {/* ranks */}
      <Panel title="Ranks">
        {r.next ? <View style={{ gap: 6 }}>
          <Bar frac={r.frac} />
          <T mute size={12.5}>{`${berries(r.toNext, true)} more bounty to ${r.next.label}`}</T>
        </View> : null}
        {RANKS.map(x => {
          const on = x.id === r.id, got = b >= x.at;
          return (
            <View key={x.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 44, opacity: got ? 1 : 0.6 }}>
              <RankBadge rank={x} size={34} />
              <T w={on ? 'bold' : 'semi'} size={14.5} style={{ flex: 1, color: on ? c.accent : c.ink }}>{x.label}</T>
              <T mute size={13}>{x.at ? berries(x.at, true) : 'Start'}</T>
              {got ? <Ionicons name="checkmark-circle" size={18} color={c.accent} /> : <View style={{ width: 18 }} />}
            </View>
          );
        })}
        <T mute size={12}>Your bounty is every point you’ve earned plus set-completion bounty. Spending points never lowers it.</T>
      </Panel>
      <Pressable onPress={() => router.push('/rewards')} style={{ alignSelf: 'center', minHeight: 44, justifyContent: 'center' }}>
        <T w="semi" style={{ color: c.accent }}>Earn more bounty ›</T>
      </Pressable>
    </ScrollView>
  );
}

// the poster as a 1080×1500 picture (web)
async function drawPoster({ name, bounty, rank, stats, img }) {
  const W = 1080, H = 1500, cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  const g = cv.getContext('2d');
  const paint = pic => {
    g.fillStyle = PAPER; g.fillRect(0, 0, W, H);
    const v = g.createRadialGradient(W / 2, H / 2, 300, W / 2, H / 2, 900);
    v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(90,60,20,0.35)');
    g.fillStyle = v; g.fillRect(0, 0, W, H);
    g.strokeStyle = PAPER2; g.lineWidth = 24; g.strokeRect(12, 12, W - 24, H - 24);
    g.fillStyle = INK; g.textAlign = 'center'; g.textBaseline = 'alphabetic';
    const fit = (txt, size, maxW, weight = '900') => { let s = size; do { g.font = `${weight} ${s}px Georgia, "Times New Roman", serif`; s -= 4; } while (g.measureText(txt).width > maxW && s > 20); };
    fit('WANTED', 210, W - 120); g.fillText('WANTED', W / 2, 250);
    const px = 110, py = 300, pw = W - 220, ph = 680;
    g.fillStyle = '#5b4630'; g.fillRect(px, py, pw, ph);
    if (pic) {
      const h = ph - 60, w = h * (pic.width / pic.height);
      g.drawImage(pic, W / 2 - w / 2, py + 30, w, h);
    } else {
      g.fillStyle = PAPER; g.font = '900 300px Georgia, serif'; g.fillText('?', W / 2, py + ph / 2 + 105);
    }
    g.strokeStyle = INK; g.lineWidth = 8; g.strokeRect(px, py, pw, ph);
    g.fillStyle = INK;
    fit(name.toUpperCase(), 96, W - 160, '800'); g.fillText(name.toUpperCase(), W / 2, 1110);
    fit(bounty, 100, W - 140); g.fillText(bounty, W / 2, 1230);
    g.fillRect(140, 1268, W - 280, 4);
    g.font = '800 54px Georgia, serif'; g.fillText(rank.toUpperCase().split('').join(String.fromCharCode(8202)), W / 2, 1345);
    g.globalAlpha = 0.85; fit(stats, 36, W - 160, '600'); g.fillText(stats, W / 2, 1410);
    g.globalAlpha = 0.6; g.font = '600 28px Georgia, serif'; g.fillText('One Piece Market', W / 2, 1460); g.globalAlpha = 1;
  };
  let pic = null;
  if (img) pic = await new Promise(res => { const i = new Image(); i.crossOrigin = 'anonymous'; i.onload = () => res(i); i.onerror = () => res(null); i.src = img; setTimeout(() => res(null), 6000); });
  paint(pic);
  const blob = await new Promise(res => { try { cv.toBlob(res, 'image/png'); } catch { res(null); } });
  if (blob) return blob;
  paint(null);   // the card picture couldn't be used: poster without it
  return new Promise(res => cv.toBlob(res, 'image/png'));
}
