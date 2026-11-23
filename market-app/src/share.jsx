// Share one group of your collection as a read-only link (names, versions, quantities and today's
// prices; never what you paid or your notes). Links work until you stop sharing them.
import React, { useEffect, useState } from 'react';
import { Platform, View } from 'react-native';
import { useData } from './data';
import { useTheme } from './theme';
import { Button, MenuItem, Note, Sheet, T } from './ui';
import { siteBase } from './ocr';
import { toast } from './toast';
import { haptic } from './haptic';

export const shareUrl = id => siteBase() + 'share/' + id;

export async function sendLink(url, title) {
  if (Platform.OS === 'web' && navigator.share && /iPhone|iPad|Android/i.test(navigator.userAgent || '')) {
    try { await navigator.share({ title, url }); return; } catch (e) { if (e && e.name === 'AbortError') return; }
  }
  try { await navigator.clipboard.writeText(url); toast('Link copied'); } catch { toast(url); }
}

export function ShareSheet({ open, onClose }) {
  const d = useData(), c = useTheme();
  const [shares, setShares] = useState(null), [err, setErr] = useState('');
  const groups = [...new Set(d.owned.filter(o => o.status !== 'sold').map(o => o.group || 'Other'))].sort();
  const load = () => d.listShares().then(setShares, e => setErr(e.message));
  useEffect(() => { if (open) { setErr(''); load(); } }, [open]);
  const make = async g => {
    try { const id = await d.createShare(g); haptic('success'); await load(); sendLink(shareUrl(id), g); }
    catch (e) { setErr(e.message); }
  };
  const stop = async id => { try { await d.removeShare(id); toast('Link switched off'); load(); } catch (e) { toast(e.message); } };
  return (
    <Sheet open={open} onClose={onClose} title="Share a group">
      {err === 'NOT_SET_UP' ? <Note tone="warn" title="One database step first">Run supabase/2026-11-24.sql in Supabase (SQL Editor) to switch sharing on.</Note>
        : err ? <Note tone="warn">{err}</Note> : null}
      <T mute size={13.5}>Anyone with the link sees that group’s cards with today’s prices. Not what you paid, and not your notes.</T>
      {(shares || []).length ? <>
        <T w="bold" size={14}>Shared now</T>
        {shares.map(s => (
          <View key={s.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={{ flex: 1 }}><MenuItem icon="link" label={s.grp} sub="Tap to send the link again" onPress={() => sendLink(shareUrl(s.id), s.grp)} /></View>
            <Button ghost onPress={() => stop(s.id)} style={{ minHeight: 40, paddingHorizontal: 14 }}>Stop</Button>
          </View>
        ))}
      </> : null}
      <T w="bold" size={14}>Make a link for</T>
      {groups.map(g => <MenuItem key={g} icon="share-outline" label={g} sub={(n => `${n} ${n === 1 ? 'entry' : 'entries'}`)(d.owned.filter(o => o.status !== 'sold' && (o.group || 'Other') === g).length)} onPress={() => make(g)} />)}
    </Sheet>
  );
}
