import React, { useState } from 'react';
import { Linking, View } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { exportCollection } from '../../src/csv';
import { useWide } from '../../src/layout';
import { PushSection } from '../../src/pushui';
import { FeedbackSheet } from '../../src/feedback';
import { usePref } from '../../src/prefs';
import { MenuItem } from '../../src/ui';
import { supabase, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, Choice, Field, Section, T } from '../../src/ui';
import { Screen, Title } from '../../src/screen';
import { siteBase } from '../../src/ocr';

export default function Account() {
  const d = useData(), c = useTheme(), wide = useWide();
  const { back } = useLocalSearchParams();
  const [fb, setFb] = useState(false);
  const [fbBtn, setFbBtn] = usePref('fbButton', true);
  const [, setToured] = usePref('toured', null);
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
      {d.session ? <Section title="Your data">
        <T mute size={14}>Bring in a collection from Collectr, TCGplayer or a spreadsheet, or take a copy of yours.</T>
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <Button ghost icon="cloud-upload-outline" onPress={() => router.push('/import')}>Import CSV</Button>
          <Button ghost icon="download-outline" onPress={() => exportCollection(d)}>Export CSV</Button>
        </View>
      </Section> : null}
      <Section title="Tools">
        <MenuItem icon="layers-outline" label="Deck price" sub="Paste a decklist: cost, what you own, what’s missing" onPress={() => router.push('/deck')} />
        {d.session ? <MenuItem icon="pricetag-outline" label="eBay deals" sub="Listings under the deal prices you set" onPress={() => router.push('/deals')} /> : null}
        <MenuItem icon="swap-horizontal" label="Trade calculator" sub="Your cards against theirs, at today’s prices" onPress={() => router.push('/trade')} />
        <MenuItem icon="grid-outline" label="Set progress" sub="How close you are to finishing each set" onPress={() => router.push('/sets')} />
        {d.session ? <MenuItem icon="receipt-outline" label="Sales report" sub="What you sold each year, with profit" onPress={() => router.push('/sales')} /> : null}
      </Section>
      <PushSection />
      <Section title="Watchlist and price alerts">
        <T mute size={14}>Star cards to follow them and get told in the app when they pass a price you set.{d.favLocal && d.session ? ' Kept on this device for now (run supabase/watchlist.sql to save it to your account).' : ''}</T>
        <Button ghost icon="star-outline" onPress={() => router.push('/watchlist')}>{`Open watchlist${d.favs.length ? ` (${d.favs.length})` : ''}`}</Button>
      </Section>
      <Section title="Help and feedback">
        <MenuItem icon="chatbubble-ellipses-outline" label="Report a problem or idea" onPress={() => setFb(true)} />
        <MenuItem icon="eye-outline" label={fbBtn ? 'Hide the feedback button' : 'Show the feedback button'} sub="The small round button in the corner" onPress={() => setFbBtn(!fbBtn)} />
        <MenuItem icon="play-circle-outline" label="Show the intro again" onPress={() => setToured(false)} />
      </Section>
      <FeedbackSheet open={fb} onClose={() => setFb(false)} />
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
      <Section title="Ideas in progress">
        <T mute size={14}>Try new features before they're real.</T>
        <Button ghost icon="sync-circle-outline" onPress={() => router.push('/spin')}>Daily spin (preview)</Button>
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
      {wide ? <Section title="Keyboard shortcuts">
        <T mute size={14}>/ search · N add an item · S scan · Esc close or go back. In the Collection table, click a quantity or price to change it.</T>
      </Section> : null}
      <T mute size={11.5} style={{ textAlign: 'center', marginTop: 10 }}>Version 24 Nov</T>
    </View></Screen>
  );
}
