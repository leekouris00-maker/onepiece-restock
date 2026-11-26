// Profile (26 Nov 2026 cleanup): your account, then four rows: Tools, Rewards, Settings, Help and privacy.
// Each row opens its own page (app/tools.jsx, app/rewards.jsx, app/settings.jsx, app/about.jsx).
import React, { useState } from 'react';
import { Pressable, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { supabase, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, Field, Panel, T } from '../../src/ui';
import { Screen, Title } from '../../src/screen';
import { toast } from '../../src/toast';
import { usePoints } from '../../src/points';

function Row({ icon, label, hint, onPress, last }) {
  const c = useTheme();
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityLabel={label}
      style={({ pressed, hovered }) => ({ flexDirection: 'row', alignItems: 'center', gap: 14, minHeight: 56, paddingHorizontal: 14,
        backgroundColor: pressed || hovered ? c.soft : 'transparent', borderBottomWidth: last ? 0 : 1, borderBottomColor: c.line })}>
      <Ionicons name={icon} size={20} color={c.accent} />
      <T w="semi" size={15.5} style={{ flex: 1 }}>{label}</T>
      {hint ? <T mute size={13} numberOfLines={1} style={{ maxWidth: '45%' }}>{hint}</T> : null}
      <Ionicons name="chevron-forward" size={17} color={c.mute} />
    </Pressable>
  );
}

export default function Account() {
  const d = useData(), c = useTheme();
  const { back } = useLocalSearchParams();
  const pts = usePoints();
  const [email, setEmail] = useState(''); const [pw, setPw] = useState(''); const [msg, setMsg] = useState(''); const [wait, setWait] = useState(false);
  const go = async up => {
    setMsg(''); setWait(true);
    try {
      const r = up ? await supabase.auth.signUp({ email: email.trim(), password: pw }) : await supabase.auth.signInWithPassword({ email: email.trim(), password: pw });
      if (r.error) throw r.error;
      if (up && !r.data.session) setMsg('Account made. Check your email for the confirmation link, then sign in here.');
      else if (back && router.canGoBack()) router.back();
    } catch (e) { setMsg(e.message || String(e)); } finally { setWait(false); }
  };
  const email0 = d.session?.user?.email || '';
  const ptsHint = pts.mode === 'server' || pts.mode === 'device' ? `${pts.pts.toLocaleString()} pts${pts.checkedIn ? '' : ' · check in'}` : null;

  return (
    <Screen max={720}><View style={{ gap: 14 }}>
      <Title>Profile</Title>

      {!d.configured ? <T mute>Saving isn’t set up in this build: the Supabase address and key haven’t been added yet. Prices still work.</T>
        : d.session ? <Panel>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
              <View style={{ width: 48, height: 48, borderRadius: 24, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
                <T head size={20} style={{ color: c.accent }}>{(email0[0] || '?').toUpperCase()}</T>
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <T w="bold" size={16} numberOfLines={1}>{email0}</T>
                <T mute size={12.5}>{d.busy ? 'Loading your collection…' : `${d.owned.length} collection ${d.owned.length === 1 ? 'entry' : 'entries'} · saved to your account`}{d.loadError ? ` · error: ${d.loadError}` : ''}</T>
              </View>
            </View>
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <Button ghost icon="refresh" style={{ flexGrow: 1, minHeight: 44 }} onPress={() => { d.refresh(); d.loadCatalog(true); toast('Reloading…'); }}>Reload</Button>
              <Button ghost style={{ flexGrow: 1, minHeight: 44 }} onPress={() => supabase.auth.signOut()}>Sign out</Button>
            </View>
          </Panel> : <Panel>
            <T w="bold" size={20}>Sign in</T>
            <T mute>Your collection, sales and photos are saved to your account, so they follow you to any device.</T>
            {msg ? <T style={{ color: c.down }}>{msg}</T> : null}
            <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" textContentType="emailAddress" style={{ flexBasis: 'auto' }} />
            <Field label="Password" value={pw} onChangeText={setPw} secureTextEntry autoComplete="password" textContentType="password" style={{ flexBasis: 'auto' }}
              onSubmitEditing={() => go(false)} returnKeyType="go" />
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <Button disabled={wait} onPress={() => go(false)}>Sign in</Button>
              <Button disabled={wait} ghost onPress={() => go(true)}>Create account</Button>
            </View>
          </Panel>}

      <Panel style={{ padding: 0, gap: 0, overflow: 'hidden' }}>
        <Row icon="construct-outline" label="Tools" hint="Trade, deck, sets, sales" onPress={() => router.push('/tools')} />
        <Row icon="gift-outline" label="Rewards" hint={ptsHint} onPress={() => router.push('/rewards')} />
        <Row icon="settings-outline" label="Settings" hint="Currency, alerts" onPress={() => router.push('/settings')} />
        <Row icon="help-circle-outline" label="Help and privacy" onPress={() => router.push('/about')} last />
      </Panel>
      {d.favLocal && d.session ? <T mute size={12}>Watchlist is kept on this device for now (run supabase/watchlist.sql to save it to your account).</T> : null}
      <T mute size={11.5} style={{ textAlign: 'center', marginTop: 10 }}>Version 26 Nov</T>
    </View></Screen>
  );
}
