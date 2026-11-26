// Help and privacy (26 Nov 2026): moved out of Profile.
import React, { useState } from 'react';
import { Linking, View } from 'react-native';
import { router } from 'expo-router';
import { useData } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, MenuItem, Section, T } from '../src/ui';
import { Screen } from '../src/screen';
import { useWide } from '../src/layout';
import { siteBase } from '../src/ocr';
import { emit } from '../src/bus';
import { Keys } from '../src/palette';

export default function About() {
  const d = useData(), c = useTheme(), wide = useWide();
  const [del, setDel] = useState(0); const [delMsg, setDelMsg] = useState('');
  return (
    <Screen max={720}><View style={{ gap: 12 }}>
      <Section title="Help">
        <MenuItem icon="apps-outline" label="All functions" sub="Everything the app does, where it is and its shortcut" onPress={() => router.push('/help')} />
        {wide ? <MenuItem icon="keypad-outline" label="Keyboard shortcuts" sub="Press ? on any page" onPress={() => emit('cheatsheet')} right={<Keys k="?" small />} /> : null}
        <MenuItem icon="chatbubble-ellipses-outline" label="Report a problem or idea" onPress={() => emit('feedback')} />
        <MenuItem icon="play-circle-outline" label="Show the intro again" onPress={() => emit('tour')} />
        <T mute size={13} style={{ marginTop: 4 }}>Prices: TCGplayer market for every English set, refreshed each morning{d.cat ? ` (now ${d.cat.meta.updated}, US$1 = A$${d.cat.meta.fx})` : ''}; eBay sold prices for cards you track or own. Card pictures are TCGplayer’s until you add your own photo.</T>
      </Section>
      <Section title="Privacy">
        <T mute size={14}>No ads, no outside tracking, nothing sold. Card scans are read on your phone and never uploaded.</T>
        <Button ghost icon="shield-checkmark-outline" onPress={() => Linking.openURL(siteBase() + 'privacy.html')}>Privacy policy</Button>
        {d.session ? <>
          {del === 0 ? <Button ghost danger onPress={() => { setDel(1); setDelMsg(''); }}>Delete my account</Button> : <>
            <T size={14}>This permanently deletes your login, your whole collection, logged sales, your own cards, tracked eBay searches, photos and Rewards points. It can't be undone.</T>
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
      <T mute size={11.5} style={{ textAlign: 'center', marginTop: 10 }}>Version 27 Nov</T>
    </View></Screen>
  );
}
