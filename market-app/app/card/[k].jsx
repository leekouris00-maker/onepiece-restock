import React, { useState } from 'react';
import { Linking, Pressable, ScrollView, View, useWindowDimensions } from 'react-native';
import { router, useLocalSearchParams } from 'expo-router';
import { pickPhoto } from '../../src/photo';
import { clean, median, today, useData } from '../../src/data';
import { useTheme } from '../../src/theme';
import { Button, CardArt, Chip, Choice, Empty, Field, Section, Sparkline, Stat, T } from '../../src/ui';

export default function CardScreen() {
  const { k } = useLocalSearchParams();
  const d = useData(), c = useTheme();
  const { width } = useWindowDimensions();
  const card = d.card(k);
  const [msg, setMsg] = useState('');
  const w = d.watchOf(k), cp = d.comps[k];
  const [q, setQ] = useState(w?.q || (card ? `one piece ${card.num} ${clean(card.n).replace(/[\[\]()!]/g, ' ')}`.replace(/\s+/g, ' ').trim() : ''));
  const [lang, setLang] = useState(w ? w.lang || '' : card?.lang === 'JP' ? 'ja' : '');
  const [graded, setGraded] = useState(w ? (w.graded == null ? 'any' : String(w.graded)) : 'false');
  const [sale, setSale] = useState({ price: '', cur: d.cur, date: today(), grade: 'Raw', link: '', note: '' });
  if (!card) return <Empty>{d.cat ? 'Card not found.' : 'Loading…'}</Empty>;

  const set = card.mine ? card.setName : d.cat?.byId[card.g]?.name || '';
  const sl = d.salesOf(card.k), raw = sl.filter(s => (s.grade || 'Raw') === 'Raw').map(s => d.toUsd(s.price, s.cur));
  const mine = d.owned.filter(o => o.card === card.k && o.status !== 'sold'), n = mine.reduce((a, o) => a + (Number(o.qty) || 1), 0);
  const mv = d.move(card), artW = Math.min(170, width * 0.36);
  const search = encodeURIComponent(`one piece ${card.num} ${clean(card.n).replace(/\[.*?\]/g, '')} ${card.lang === 'JP' ? 'japanese' : ''}`.trim());
  const run = async (f, ok) => { try { setMsg(''); await f(); if (ok) setMsg(ok); } catch (e) { setMsg(e.message || String(e)); } };
  const fx = d.fx;
  const lab = v => (d.cur === 'AUD' ? 'A$' + Math.round(v * fx).toLocaleString() : 'US$' + Math.round(v).toLocaleString());

  return (
    <ScrollView contentContainerStyle={{ padding: 20, paddingBottom: 60, maxWidth: 820, width: '100%', alignSelf: 'center' }} keyboardShouldPersistTaps="handled">
      <View style={{ flexDirection: 'row', gap: 18 }}>
        <View style={{ gap: 8, width: artW }}>
          <CardArt k={card.k} photo={d.photoOf(card.k)} num={card.num} width={artW} big />
          <Chip onPress={() => pickPhoto(uri => run(() => d.addPhoto({ card: card.k }, uri), 'Photo saved'))}>{d.photoOf(card.k) ? 'Change photo' : 'Add photo'}</Chip>
        </View>
        <View style={{ flex: 1, gap: 6 }}>
          <T mute size={13}>{[card.num, set, card.r, card.lang].filter(Boolean).join(' · ')}</T>
          <T serif size={clean(card.n).length > 38 ? 21 : 27} style={{ lineHeight: clean(card.n).length > 38 ? 25 : 31 }}>{clean(card.n)}</T>
          {n ? <T size={13.5} w="semi" style={{ color: c.gold }}>You own {n}</T> : null}
        </View>
      </View>
      {msg ? <T size={14} style={{ marginTop: 12, color: c.down }}>{msg}</T> : null}

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 18 }}>
        {!card.mine && <Stat label="TCGplayer market" value={d.money(card.m)} />}
        {!card.mine && <Stat label="Lowest listing" value={d.money(card.l)} />}
        {!card.mine && <Stat label="7-day change" value={mv == null ? '–' : `${mv > 0 ? '▲' : mv < 0 ? '▼' : ''}${Math.abs(mv).toFixed(1)}%`} tone={mv > 0.05 ? c.up : mv < -0.05 ? c.down : null} />}
        <Stat label="Your logged sales, raw median" value={raw.length ? d.money(median(raw)) : '–'} />
      </View>
      {!card.mine && <View style={{ marginTop: 14 }}>
        <Sparkline hist={card.h} now={card.m} width={Math.min(width, 820) - 40} label={card.m != null ? lab(card.m) : ''} />
        <T mute size={12.5}>TCGplayer market price, last 35 days</T>
      </View>}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 18, marginTop: 12 }}>
        {!card.mine && <T style={{ color: c.link }} onPress={() => Linking.openURL(`https://www.tcgplayer.com/product/${card.k.slice(2)}`)}>Open on TCGplayer</T>}
        <T style={{ color: c.link }} onPress={() => Linking.openURL(`https://www.ebay.com.au/sch/i.html?_nkw=${search}&LH_Sold=1&LH_Complete=1`)}>eBay AU sold</T>
        <T style={{ color: c.link }} onPress={() => Linking.openURL(`https://www.ebay.com/sch/i.html?_nkw=${search}&LH_Sold=1&LH_Complete=1`)}>eBay US sold</T>
      </View>

      <Section title="My collection">
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {mine.map(o => <Chip key={o.id} onPress={() => router.push({ pathname: '/item/[id]', params: { id: o.id } })}>{(o.group || 'Other') + ' ×' + (o.qty || 1)}</Chip>)}
          <Chip on onPress={() => router.push({ pathname: '/item/[id]', params: { id: 'new', card: card.k } })}>{n ? 'Add more' : 'Add to my collection'}</Chip>
        </View>
      </Section>

      <Section title="eBay sold, automatic">
        {!w ? <T mute size={14}>Track this card and its eBay sold prices are fetched every morning, each card refreshed about weekly. The free plan covers about 20 cards ({d.watch.length} tracked now).</T>
          : !cp || cp.q !== w.q ? <T mute size={14}>Tracking. Prices arrive with the next morning update.</T>
          : cp.none || cp.median == null ? <T mute size={14}>No eBay sales matched this search in the last 90 days (checked {String(cp.at).slice(0, 10)}). Try fewer words.</T>
          : <>
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                <Stat label="Median, last 90 days" value={d.money(cp.median)} />
                <Stat label="Middle half of sales" value={`${d.money(cp.p25)} – ${d.money(cp.p75)}`} />
                <Stat label="Sales found" value={String(cp.count)} />
              </View>
              <T mute size={12.5}>Checked {String(cp.at).slice(0, 10)} · newest sale {cp.newest} · converted from US$</T>
              {cp.sales.map((x, i) => (
                <Pressable key={i} onPress={() => x.url && Linking.openURL(x.url)} style={{ flexDirection: 'row', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: c.line }}>
                  <T serif size={16} style={{ width: 92 }}>{d.money(x.price)}</T>
                  <View style={{ flex: 1 }}><T size={13.5} numberOfLines={1}>{x.title}</T><T mute size={12}>{[x.sold, x.grade, x.offer && 'offer'].filter(Boolean).join(' · ')}</T></View>
                </Pressable>
              ))}
            </>}
        <Field label="eBay search used" value={q} onChangeText={setQ} autoCapitalize="none" />
        <Choice label="Language" value={lang} onChange={setLang} options={[['', 'Any'], ['ja', 'Japanese only']]} />
        <Choice label="Condition" value={graded} onChange={setGraded} options={[['false', 'Raw only'], ['true', 'Graded only'], ['any', 'Any']]} />
        <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
          <Button onPress={() => run(() => d.setTrack(card.k, { q: q.trim(), lang: lang || null, graded: graded === 'any' ? null : graded === 'true' }), w ? 'Search saved' : 'Tracking this card')}>{w ? 'Save search' : 'Track eBay sold prices'}</Button>
          {w ? <Button ghost onPress={() => run(() => d.untrack(card.k), 'Stopped tracking')}>Stop tracking</Button> : null}
        </View>
      </Section>

      <Section title="Sales you logged">
        {!sl.length ? <T mute size={14}>None yet. Check the sold listings above and add what it actually sold for.</T> : sl.map(s => (
          <View key={s.id} style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12, alignItems: 'center', paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: c.line }}>
            <T serif size={16}>{(s.cur === 'USD' ? 'US$' : 'A$') + Number(s.price).toFixed(2)}</T>
            <T size={13.5}>{s.grade || 'Raw'}</T><T mute size={13}>{String(s.date)}</T>
            {s.link ? <T size={13} style={{ color: c.link }} onPress={() => Linking.openURL(s.link)}>listing</T> : null}
            <View style={{ flex: 1 }} />
            <T mute size={13} onPress={() => run(() => d.removeSale(s.id), 'Sale deleted')}>Delete</T>
          </View>
        ))}
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
          <Field label="Sold for" value={sale.price} onChangeText={v => setSale({ ...sale, price: v })} keyboardType="decimal-pad" />
          <Field label="Date (YYYY-MM-DD)" value={sale.date} onChangeText={v => setSale({ ...sale, date: v })} />
          <Choice label="Currency" value={sale.cur} onChange={v => setSale({ ...sale, cur: v })} options={['AUD', 'USD']} />
          <Choice label="Condition" value={sale.grade} onChange={v => setSale({ ...sale, grade: v })} options={['Raw', 'PSA 10', 'PSA 9', 'Other graded']} />
          <Field label="Listing link (optional)" value={sale.link} onChangeText={v => setSale({ ...sale, link: v })} autoCapitalize="none" keyboardType="url" style={{ flexBasis: '100%' }} />
        </View>
        <Button onPress={() => run(async () => {
          const p = Number(sale.price); if (!(p > 0)) throw new Error('Enter the price it sold for');
          await d.addSale({ card: card.k, price: p, cur: sale.cur, date: sale.date || today(), grade: sale.grade, link: sale.link.trim() || null, note: sale.note || null });
          setSale({ ...sale, price: '', link: '' });
        }, 'Sale added')}>Add sale</Button>
      </Section>

      {card.mine ? <Section title="This card">
        {card.note ? <T size={14}>{card.note}</T> : null}
        <Button ghost onPress={() => run(async () => { await d.removeCard(card.id); router.back(); })}>Delete this card</Button>
      </Section> : null}
    </ScrollView>
  );
}
