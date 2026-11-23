// Deck price checker: paste a decklist (OPTCGSim / Egman / "4x OP01-016" / "4 OP01-016 Nami"),
// see what the whole deck costs, which cards you already own, and the cheapest way to finish it.
import React, { useMemo } from 'react';
import { Platform, Pressable, View } from 'react-native';
import { router } from 'expo-router';
import { clean, useData } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, CardArt, Empty, Field, Panel, T } from '../src/ui';
import { Screen } from '../src/screen';
import { usePref } from '../src/prefs';
import { versionTag } from '../src/find';
import { toast } from '../src/toast';
import { Progress } from '../src/progress';

const NUM = '((?:OP|EB|ST|PRB)\\d{2}-\\d{3}|P-\\d{3})';
export function parseDeck(text) {
  const out = new Map();
  for (const raw of String(text || '').split(/\r?\n|,|;/)) {
    const line = raw.trim().toUpperCase();
    if (!line) continue;
    let m = new RegExp(`^(\\d{1,2})\\s*[X×]?\\s*${NUM}`).exec(line), n, num;
    if (m) { n = Number(m[1]); num = m[2]; }
    else if ((m = new RegExp(`${NUM}\\s*[X×]\\s*(\\d{1,2})`).exec(line))) { num = m[1]; n = Number(m[2]); }
    else if ((m = new RegExp(NUM).exec(line))) { num = m[1]; n = 1; }
    else continue;
    out.set(num, (out.get(num) || 0) + n);
  }
  return [...out.entries()].map(([num, n]) => ({ num, n }));
}

export default function Deck() {
  const d = useData(), c = useTheme();
  const [text, setText] = usePref('deckText', '');
  const lines = useMemo(() => parseDeck(text), [text]);
  const rows = useMemo(() => lines.map(({ num, n }) => {
    const vs = (d.byNum.get(num) || []).filter(x => !x.mine && x.t === 'card');
    const priced = vs.filter(x => x.m != null).sort((a, b) => a.m - b.m);
    const cheap = priced[0] || vs[0] || null;
    const have = d.owned.filter(o => o.status !== 'sold' && o.card && String(d.card(o.card)?.num || '').toUpperCase() === num).reduce((s, o) => s + (Number(o.qty) || 1), 0);
    const use = Math.min(have, n), miss = n - use;
    return { num, n, cheap, have, use, miss, each: cheap?.m ?? null, leader: vs.some(x => x.r === 'L') };
  }).sort((a, b) => (b.leader - a.leader) || a.num.localeCompare(b.num, undefined, { numeric: true })), [lines, d.cat, d.owned]);
  const total = rows.reduce((s, r) => s + (r.each || 0) * r.n, 0);
  const finish = rows.reduce((s, r) => s + (r.each || 0) * r.miss, 0);
  const cards = rows.reduce((s, r) => s + r.n, 0), haveN = rows.reduce((s, r) => s + r.use, 0);
  const unknown = rows.filter(r => !r.cheap).length;

  const copy = async () => {
    const list = rows.filter(r => r.miss).map(r => `${r.miss}x ${r.num} ${r.cheap ? clean(r.cheap.n).replace(/\s*\(.*$/, '') : ''} · ${d.money(r.each)} each`).join('\n');
    try { await navigator.clipboard.writeText(`Still need (${rows.reduce((s, r) => s + r.miss, 0)} cards, about ${d.money(finish)}):\n${list}`); toast('Shopping list copied'); }
    catch { toast('Couldn’t copy on this device'); }
  };

  return (
    <Screen max={900}>
      <T mute size={13.5}>Paste a decklist from OPTCGSim, Egman, Limitless or a group chat. Lines like “4xOP01-016”, “4 OP01-016 Nami” or “OP01-016 x4” all work.</T>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', marginTop: 10 }}>
        <Field label="Decklist" value={text} onChangeText={setText} multiline numberOfLines={6} placeholder={'1xOP13-002\n4xOP13-005\n4xOP13-010\n…'} style={{ flexBasis: '100%' }} />
      </View>
      {text && !rows.length ? <Empty>No card numbers found. Each line needs a number like OP01-016.</Empty> : null}
      {rows.length ? <>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 14 }}>
          <Box label={`Whole deck (${cards} cards)`} value={d.money(total)} />
          <Box label="To finish it" value={d.money(finish)} strong />
        </View>
        <View style={{ gap: 6, marginTop: 12 }}>
          <T size={13} w="semi">You have {haveN} of {cards} cards</T>
          <Progress v={cards ? haveN / cards : 0} />
          {cards !== 51 ? <T mute size={12}>{cards < 51 ? `${51 - cards} short of a full deck (1 leader + 50 cards).` : `${cards - 51} over a full deck (1 leader + 50 cards).`}</T> : null}
          {unknown ? <T mute size={12}>{unknown} number{unknown === 1 ? '' : 's'} not in the price list, so not counted.</T> : null}
        </View>
        <Panel style={{ marginTop: 14, gap: 2 }}>
          {rows.map(r => (
            <Pressable key={r.num} onPress={() => r.cheap && router.push({ pathname: '/card/[k]', params: { k: r.cheap.k } })} accessibilityRole="button"
              style={({ pressed }) => ({ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 7, opacity: pressed ? 0.6 : 1 })}>
              <CardArt k={r.cheap?.k} photo={r.cheap ? d.photoOf(r.cheap.k) : null} num={r.num} width={32} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <T w="semi" size={14} numberOfLines={1}>{r.n}× {r.cheap ? clean(r.cheap.n).replace(/\s*\(.*$/, '') : r.num}{r.leader ? '  · Leader' : ''}</T>
                <T mute size={12} numberOfLines={1}>{[r.num, r.cheap ? `cheapest: ${versionTag(d.cat, r.cheap)}` : 'not in the price list'].join(' · ')}</T>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <T w="bold" size={14}>{r.each == null ? '–' : d.money(r.each * r.n)}</T>
                <T size={12} w="semi" style={{ color: r.miss ? c.down : c.up }}>{r.miss ? `need ${r.miss}` : r.have >= r.n ? 'have all' : ''}</T>
              </View>
            </Pressable>
          ))}
        </Panel>
        {finish > 0 && Platform.OS === 'web' ? <Button ghost icon="copy-outline" onPress={copy} style={{ marginTop: 14 }}>Copy what I still need</Button> : null}
        <T mute size={11.5} style={{ marginTop: 12 }}>Priced at the cheapest English version of each card (TCGplayer market). Cards count as yours if any version of that number is in your collection.</T>
      </> : null}
    </Screen>
  );
}

function Box({ label, value, strong }) {
  const c = useTheme();
  return (
    <View style={{ flexGrow: 1, flexBasis: 140, borderRadius: 16, padding: 14, backgroundColor: strong ? c.accentDim : c.panel }}>
      <T size={12.5} mute>{label}</T>
      <T w="bold" size={20} style={[{ marginTop: 3 }, strong ? { color: c.accent } : null]}>{value}</T>
    </View>
  );
}
