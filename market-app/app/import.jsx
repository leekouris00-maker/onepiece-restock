// Bring a collection in from a CSV: Collectr, TCGplayer, this app's own export, or any spreadsheet with
// a name or card-number column. Shows what matched before anything is saved.
import React, { useMemo, useState } from 'react';
import { ScrollView, View } from 'react-native';
import { router } from 'expo-router';
import { clean, useData } from '../src/data';
import { useTheme } from '../src/theme';
import { Button, CardArt, Choice, Field, Note, Panel, T } from '../src/ui';
import { mapHeader, matchRows, parseCSV, pickFile } from '../src/csv';
import { versionTag } from '../src/find';
import { toast } from '../src/toast';
import { haptic } from '../src/haptic';

const LABELS = { pid: 'TCGplayer product ID', num: 'Card number', name: 'Name', set: 'Set', version: 'Version / printing', qty: 'Quantity', paid: 'Price paid',
  value: 'Your value', group: 'Group / folder', cond: 'Condition', lang: 'Language', status: 'Status', sold: 'Sold for', added: 'Date added', notes: 'Notes' };

export default function Import() {
  const d = useData(), c = useTheme();
  const [file, setFile] = useState(null);       // { name, head, rows }
  const [group, setGroup] = useState('');
  const [dupes, setDupes] = useState('add');    // add | skip
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [paste, setPaste] = useState('');

  const load = (name, text) => {
    setErr('');
    const rows = parseCSV(text);
    if (rows.length < 2) { setErr('That file has no rows under its headings.'); return; }
    const map = mapHeader(rows[0]);
    if (map.name == null && map.num == null && map.pid == null) { setErr('Couldn’t find a Name, Card number or Product ID column. Check the first row has headings.'); return; }
    setFile({ name, head: rows[0], rows: rows.slice(1), map });
  };
  const choose = async () => {
    const f = await pickFile();
    if (!f) return;
    load(f.name, await f.text());
  };

  const preview = useMemo(() => (file && d.cat ? matchRows(file.rows, file.map, d, d.byNum) : []), [file, d.cat, d.custom]);
  const matched = preview.filter(p => p.card).length;
  const units = preview.reduce((n, p) => n + p.item.qty, 0);

  const run = async () => {
    setBusy(true); setErr('');
    try {
      const out = [];
      const have = new Map(d.owned.filter(o => o.status !== 'sold' && o.card).map(o => [`${o.card}|${o.lang}|${o.cond}`, o]));
      let merged = 0, skipped = 0;
      for (const p of preview) {
        const it = { ...p.item, group: p.item.group || group.trim() || 'Imported' };
        const key = `${it.card}|${it.lang}|${it.cond}`;
        const old = it.card && it.status === 'owned' ? have.get(key) : null;
        if (old) {
          if (dupes === 'skip') { skipped++; continue; }
          const next = { ...old, qty: (Number(old.qty) || 1) + it.qty, paid: old.paid ?? it.paid };
          have.set(key, next); out.push(next); merged++;
          continue;
        }
        out.push(it);
      }
      // the same entry may appear twice in out after merging: keep the last
      const byId = new Map(out.map(o => [o.id, o]));
      await d.saveMany([...byId.values()]);
      haptic('success');
      toast(`Imported ${preview.length - skipped} rows${merged ? ` (${merged} added to cards you had)` : ''}${skipped ? `, skipped ${skipped}` : ''}`);
      router.back();
    } catch (e) { setErr(e.message || String(e)); } finally { setBusy(false); }
  };

  if (!d.session) return (
    <ScrollView contentContainerStyle={{ padding: 20, gap: 14, maxWidth: 820, width: '100%', alignSelf: 'center' }}>
      <T mute>Sign in first: an import saves into your account.</T>
      <Button onPress={() => router.push({ pathname: '/account', params: { back: '1' } })}>Sign in</Button>
    </ScrollView>
  );

  return (
    <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 60, gap: 14, maxWidth: 820, width: '100%', alignSelf: 'center' }} keyboardShouldPersistTaps="handled">
      {!file ? <>
        <T mute size={14.5}>Choose a CSV file. Collectr (Portfolio → ⋯ → Export, Pro), TCGplayer and this app’s own export all work, as does any spreadsheet saved as CSV with a name or card-number column.</T>
        <Button icon="document-outline" onPress={choose}>Choose a CSV file</Button>
        <Panel title="Or paste it">
          <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
            <Field label="Paste rows here, headings first" value={paste} onChangeText={setPaste} multiline numberOfLines={5} placeholder={'Name,Card number,Quantity,Paid\nSabo,OP13-120,1,45'} style={{ flexBasis: '100%' }} />
          </View>
          <Button ghost disabled={!paste.trim()} onPress={() => load('pasted', paste)}>Read pasted rows</Button>
        </Panel>
        <T mute size={12.5}>Matching uses the TCGplayer product ID when there is one, else the card number and name. Anything that doesn’t match is still brought in, priced by your own value.</T>
      </> : <>
        <View style={{ gap: 4 }}>
          <T w="bold" size={18}>{file.name}</T>
          <T mute size={13.5}>{preview.length} rows · {units} items · {matched} matched to a card{preview.length - matched ? ` · ${preview.length - matched} not matched` : ''}{preview.some(p => /guess/.test(p.how)) ? ` · ${preview.filter(p => /guess/.test(p.how)).length} best guesses (yellow): check the version after importing` : ''}</T>
        </View>
        <Panel title="Columns found">
          <T mute size={13}>{Object.entries(file.map).map(([f, i]) => `${LABELS[f]} ← “${file.head[i]}”`).join('\n')}</T>
        </Panel>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {file.map.group == null ? <Field label="Put them in group" value={group} onChangeText={setGroup} placeholder="Imported" /> : null}
          <Choice label="Cards you already have" value={dupes} onChange={setDupes} options={[['add', 'Add to the quantity'], ['skip', 'Skip them']]} />
        </View>
        {err ? <Note tone="warn" title="Import failed">{err}</Note> : null}
        <Button disabled={busy || !preview.length} onPress={run} icon="cloud-upload-outline">{busy ? 'Importing…' : `Import ${preview.length} rows`}</Button>
        <Button ghost onPress={() => setFile(null)}>Choose another file</Button>
        <Panel title="Preview" style={{ gap: 2 }}>
          {preview.slice(0, 60).map((p, i) => (
            <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 7 }}>
              <CardArt k={p.card?.k} num={p.card?.num || p.item.num} width={30} />
              <View style={{ flex: 1 }}>
                <T w="semi" size={14} numberOfLines={1}>{p.card ? clean(p.card.n) : p.item.name}</T>
                <T size={12} mute numberOfLines={1} style={/guess/.test(p.how) ? { color: '#f2c94c' } : null}>{p.card ? [p.card.num, versionTag(d.cat, p.card), /guess/.test(p.how) ? p.how : `matched by ${p.how}`].join(' · ') : 'Not matched · kept as your own item'}</T>
              </View>
              <T w="semi" size={13.5}>×{p.item.qty}</T>
              <T size={13} style={{ width: 70, textAlign: 'right', color: p.card ? c.ink : c.mute }}>{p.card ? d.money(p.card.m) : '–'}</T>
            </View>
          ))}
          {preview.length > 60 ? <T mute size={12.5}>…and {preview.length - 60} more</T> : null}
        </Panel>
      </>}
      {!file && err ? <Note tone="warn" title="Couldn’t read that file">{err}</Note> : null}
    </ScrollView>
  );
}
