import React, { useState } from 'react';
import { View } from 'react-native';
import { router } from 'expo-router';
import { supabase, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, Choice, Field, Section, T } from '../../src/ui';
import { Screen, Title } from '../../src/screen';

export default function Account() {
  const d = useData(), c = useTheme();
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
    </View></Screen>
  );
}
