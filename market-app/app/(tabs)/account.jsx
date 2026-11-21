import React, { useState } from 'react';
import { Linking, View } from 'react-native';
import { router } from 'expo-router';
import { supabase, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, Choice, Field, Section, T } from '../../src/ui';
import { Screen, Title } from '../../src/screen';
import { siteBase } from '../../src/ocr';

export default function Account() {
  const d = useData(), c = useTheme();
  const [del, setDel] = useState(0); const [delMsg, setDelMsg] = useState('');
  const [email, setEmail] = useState(''); const [pw, setPw] = useState(''); const [msg, setMsg] = useState(''); const [wait, setWait] = useState(false);
  const go = async up => {
    setMsg(''); setWait(true);
    try {
      const r = up ? await supabase.auth.signUp({ email: email.trim(), password: pw }) : await supabase.auth.signInWithPassword({ email: email.trim(), password: pw });
      if (r.error) throw r.error;
      if (up && !r.data.session) setMsg('Account made. Check your email for the confirmation link, then sign in here.');
    } catch (e) { setMsg(e.message || String(e)); } finally { setWait(false); }
  };
  return (
    <Screen max={820}><View style={{ gap: 12 }}>
      <Title>Profile</Title>
      {!d.configured ? <T mute>Saving isn’t set up in this build: the Supabase address and key haven’t been added yet. Prices still work.</T>
        : d.session ? <>
            <T w="bold" size={20}>Signed in</T>
            <T mute>{d.session.user.email}</T>
            <T mute size={13}>{d.busy ? 'Loading your collection…' : `${d.owned.length} collection entries loaded`}{d.loadError ? ` · error: ${d.loadError}` : ''}</T>
            <Button onPress={() => { d.refresh(); d.loadCatalog(true); }} icon="refresh">Reload my collection</Button>
            <Button ghost onPress={() => supabase.auth.signOut()}>Sign out</Button>
          </> : <>
            <T w="bold" size={20}>Sign in</T>
            <T mute>Your collection, sales and photos are saved to your account, so they follow you to any device.</T>
            {msg ? <T style={{ color: c.down }}>{msg}</T> : null}
            <Field label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" textContentType="emailAddress" style={{ flexBasis: 'auto' }} />
            <Field label="Password" value={pw} onChangeText={setPw} secureTextEntry autoComplete="password" textContentType="password" style={{ flexBasis: 'auto' }} />
            <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
              <Button disabled={wait} onPress={() => go(false)}>Sign in</Button>
              <Button disabled={wait} ghost onPress={() => go(true)}>Create account</Button>
            </View>
          </>}
      <Section title="Display">
        <Choice label="Currency" value={d.cur} onChange={d.setCur} options={['AUD', 'USD']} />
      </Section>
      <Section title="Your own cards">
        <T mute size={14}>Add Japanese cards, promos and anything else TCGplayer doesn’t list.</T>
        <Button ghost onPress={() => router.push('/addcard')}>Add a card</Button>
      </Section>
      <Section title="Where prices come from">
        <T mute size={14}>TCGplayer market prices for every English set, refreshed each morning{d.cat ? ` (now ${d.cat.meta.updated}, US$1 = A$${d.cat.meta.fx})` : ''}. eBay sold prices for the cards you track. Card pictures are TCGplayer’s until you add your own photo.</T>
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
      <T mute size={11.5} style={{ textAlign: 'center', marginTop: 10 }}>Version 22 Nov</T>
    </View></Screen>
  );
}
