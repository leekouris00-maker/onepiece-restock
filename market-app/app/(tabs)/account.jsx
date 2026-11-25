import React, { useState } from 'react';
import { Linking, Pressable, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useLayout } from '../../src/layout';
import { PushSection } from '../../src/pushui';
import { usePref, resetPrefs, restorePrefs } from '../../src/prefs';
import { supabase, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, Choice, Field, MenuItem, Panel, Section, T } from '../../src/ui';
import { Screen, Title } from '../../src/screen';
import { siteBase } from '../../src/ocr';
import { emit } from '../../src/bus';
import { toast } from '../../src/toast';
import { COMMANDS, keyParts } from '../../src/keys';
import { Keys } from '../../src/palette';

export default function Account() {
  const d = useData(), c = useTheme(), { wide, inner } = useLayout(820);
  const { back } = useLocalSearchParams();
  const [fbBtn, setFbBtn] = usePref('fbButton', true);
  const [del, setDel] = useState(0); const [delMsg, setDelMsg] = useState('');
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
  const reset = async () => {
    const before = await resetPrefs();
    toast(before.length ? `Reset ${before.length} saved ${before.length === 1 ? 'setting' : 'settings'} on this device` : 'Nothing to reset',
      before.length ? { action: { label: 'Undo', onPress: () => restorePrefs(before) } } : {});
  };
  const tools = COMMANDS.filter(x => x.tile && (x.need !== 'session' || d.session));
  const cols = wide ? 3 : 2, gap = 10, tileW = Math.floor((inner - 32 - gap * (cols - 1)) / cols);
  const email0 = d.session?.user?.email || '';

  return (
    <Screen max={820}><View style={{ gap: 12 }}>
      <Title>Profile</Title>

      {/* who you are */}
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

      {/* find any function */}
      <Pressable onPress={() => emit('palette')} accessibilityRole="button" accessibilityLabel="Search all functions and cards"
        style={({ pressed, hovered }) => ({ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 50, paddingHorizontal: 14, borderRadius: 14, backgroundColor: pressed || hovered ? c.raise : c.soft })}>
        <Ionicons name="flash-outline" size={19} color={c.accent} />
        <T mute size={15} style={{ flex: 1 }}>Find a function or card…</T>
        {wide ? <Keys k="mod+k" small /> : null}
      </Pressable>

      <Section title="Tools" right={<Pressable onPress={() => router.push('/help')} hitSlop={8}><T w="semi" size={13.5} style={{ color: c.accent }}>All functions</T></Pressable>}>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap }}>
          {tools.map(x => (
            <Pressable key={x.id} onPress={() => x.run(d)} accessibilityRole="button" accessibilityLabel={x.label}
              style={({ pressed, hovered }) => ({ width: tileW, minHeight: 104, padding: 12, borderRadius: 16, gap: 6, backgroundColor: pressed || hovered ? c.raise : c.soft })}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <View style={{ width: 34, height: 34, borderRadius: 10, backgroundColor: c.accentDim, alignItems: 'center', justifyContent: 'center' }}>
                  <Ionicons name={x.icon} size={18} color={c.accent} />
                </View>
                {wide && x.keys ? <T size={11.5} w="semi" mute>{keyParts(x.keys[0]).join(' ')}</T> : null}
              </View>
              <T w="bold" size={14.5} numberOfLines={1}>{x.label}</T>
              <T mute size={12} numberOfLines={2}>{x.sub}</T>
            </Pressable>
          ))}
        </View>
        {d.favLocal && d.session ? <T mute size={12}>Watchlist is kept on this device for now (run supabase/watchlist.sql to save it to your account).</T> : null}
      </Section>

      <Section title="Settings">
        <Choice label="Currency" value={d.cur} onChange={d.setCur} options={[['AUD', 'A$ Australian'], ['USD', 'US$ American']]} />
        <MenuItem icon="eye-outline" label={fbBtn ? 'Hide the feedback button' : 'Show the feedback button'} sub="The small round button in the corner" onPress={() => setFbBtn(!fbBtn)} />
        <MenuItem icon="refresh-circle-outline" label="Reset this device’s settings" sub="Sort orders, views, recent searches, calculator setups. Your collection isn’t touched; Undo for a few seconds." onPress={reset} />
      </Section>

      <PushSection />

      <Section title="Your own cards">
        <T mute size={14}>Add Japanese cards, promos and anything else TCGplayer doesn’t list.</T>
        <Button ghost icon="create-outline" onPress={() => router.push('/addcard')}>Add a card</Button>
      </Section>

      <Section title="Help and feedback">
        <MenuItem icon="apps-outline" label="All functions" sub="Everything the app does, where it is and its shortcut" onPress={() => router.push('/help')} />
        {wide ? <MenuItem icon="keypad-outline" label="Keyboard shortcuts" sub="Press ? on any page" onPress={() => emit('cheatsheet')} right={<Keys k="?" small />} /> : null}
        <MenuItem icon="chatbubble-ellipses-outline" label="Report a problem or idea" onPress={() => emit('feedback')} />
        <MenuItem icon="play-circle-outline" label="Show the intro again" onPress={() => emit('tour')} />
        <T mute size={13} style={{ marginTop: 4 }}>Prices: TCGplayer market for every English set, refreshed each morning{d.cat ? ` (now ${d.cat.meta.updated}, US$1 = A$${d.cat.meta.fx})` : ''}; eBay sold prices for cards you track or own. Card pictures are TCGplayer’s until you add your own photo.</T>
      </Section>

      <Section title="Ideas in progress">
        <T mute size={14}>Try new features before they're real.</T>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <Button ghost icon="gift-outline" style={{ flexGrow: 1 }} onPress={() => router.push('/rewards')}>Rewards</Button>
          <Button ghost icon="sparkles-outline" style={{ flexGrow: 1 }} onPress={() => router.push('/shop')}>Points shop</Button>
        </View>
      </Section>

      <Section title="Privacy">
        <T mute size={14}>No ads, no tracking, nothing sold. Card scans are read on your phone and never uploaded.</T>
        <Button ghost icon="shield-checkmark-outline" onPress={() => Linking.openURL(siteBase() + 'privacy.html')}>Privacy policy</Button>
        {d.session ? <>
          {del === 0 ? <Button ghost danger onPress={() => { setDel(1); setDelMsg(''); }}>Delete my account</Button> : <>
            <T size={14}>This permanently deletes your login, your whole collection, logged sales, your own cards, tracked eBay searches and photos. It can't be undone.</T>
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <Button danger disabled={del === 2} onPress={async () => {
                setDel(2); setDelMsg('');
                try { await d.deleteAccount(); setDel(0); setDelMsg('Your account and everything in it has been deleted.'); }
                catch (e) { setDel(1); setDelMsg(e.message || String(e)); }
              }}>{del === 2 ? 'Deleting…' : 'Delete everything'}</Button>
              <Button ghost disabled={del === 2} onPress={() => { setDel(0); setDelMsg(''); }}>Keep my account</Button>
            </View>
          </>}
        </> : null}
        {delMsg ? <T size={13.5} style={{ color: /deleted/.test(delMsg) ? c.accent : c.down }}>{delMsg}</T> : null}
      </Section>
      <T mute size={11.5} style={{ textAlign: 'center', marginTop: 10 }}>Version 25 Nov</T>
    </View></Screen>
  );
}
