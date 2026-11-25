// Every function in one place: what it does, where to find it, and its keyboard shortcut. Tap one to use it.
import React, { useState } from 'react';
import { Pressable, View } from 'react-native';
import Ionicons from '@expo/vector-icons/Ionicons';
import { useData } from '../src/data';
import { useTheme } from '../src/theme';
import { Panel, SearchBar, T, Empty } from '../src/ui';
import { Screen } from '../src/screen';
import { useWide } from '../src/layout';
import { COMMANDS, GROUPS, PAGE_KEYS } from '../src/keys';
import { Keys } from '../src/palette';

const GESTURES = [
  ['hand-left-outline', 'Swipe a collection row left', '−1, +1 or Sold without opening it'],
  ['finger-print-outline', 'Hold a row or tile', 'Menu: edit, move, price paid, sold, remove, select'],
  ['arrow-down-outline', 'Pull down from the top', 'Refresh prices and your collection'],
  ['analytics-outline', 'Drag across a chart', 'Read the value on any day'],
  ['layers-outline', 'Stack mode in the scanner', 'Keep scanning; review the pile and add it all at once'],
  ['arrow-undo-outline', 'Undo on the message at the bottom', 'Every remove, sold, +1 and move can be taken back for a few seconds'],
];

export default function Help() {
  const d = useData(), c = useTheme(), wide = useWide();
  const [q, setQ] = useState('');
  const s = q.trim().toLowerCase();
  const match = x => !s || `${x.label} ${x.sub} ${x.where || ''} ${x.group}`.toLowerCase().includes(s);
  const list = COMMANDS.filter(match);
  return (
    <Screen max={980}>
      <T mute size={14} style={{ marginBottom: 12 }}>Everything the app does, where to find it and its shortcut. Tap one to use it.{wide ? ' Press Ctrl K (⌘K on a Mac) anywhere to search these.' : ''}</T>
      <SearchBar value={q} onChangeText={setQ} placeholder="Find a function: sell, alert, export, grade…" />
      {!list.length ? <Empty>{`No function matches “${q}”.`}</Empty> : null}
      <View style={wide ? { flexDirection: 'row', flexWrap: 'wrap', gap: 14, marginTop: 14 } : { gap: 14, marginTop: 14 }}>
        {GROUPS.map(g => {
          const rows = list.filter(x => x.group === g);
          if (!rows.length) return null;
          return (
            <Panel key={g} title={g} style={wide ? { flexBasis: '48%', flexGrow: 1 } : null}>
              {rows.map(x => {
                const locked = x.need === 'session' && !d.session;
                const can = x.run && !x.info && !locked;
                return (
                  <Pressable key={x.id} disabled={!can} onPress={() => x.run(d)} accessibilityRole={can ? 'button' : undefined}
                    style={({ pressed, hovered }) => ({ flexDirection: 'row', gap: 12, alignItems: 'flex-start', padding: 8, marginHorizontal: -8, borderRadius: 12,
                      backgroundColor: can && (pressed || hovered) ? c.soft : 'transparent' })}>
                    <View style={{ width: 32, height: 32, borderRadius: 10, backgroundColor: c.soft, alignItems: 'center', justifyContent: 'center', marginTop: 1 }}>
                      <Ionicons name={x.icon} size={17} color={can ? c.accent : c.mute} />
                    </View>
                    <View style={{ flex: 1, gap: 2 }}>
                      <T w="semi" size={14.5}>{x.label}</T>
                      <T mute size={12.5}>{x.sub}</T>
                      {x.where || locked ? <T size={12} style={{ color: locked ? c.down : c.mute }}>{locked ? 'Sign in to use this' : `Where: ${x.where}`}</T> : null}
                      {!wide && x.keys ? <View style={{ marginTop: 4 }}><Keys k={x.keys} small /></View> : null}
                    </View>
                    {wide && x.keys ? <Keys k={x.keys} small /> : can ? <Ionicons name="chevron-forward" size={16} color={c.mute} style={{ marginTop: 8 }} /> : null}
                  </Pressable>
                );
              })}
            </Panel>
          );
        })}
      </View>

      {!s ? <>
        <T w="bold" size={17} style={{ marginTop: 26, marginBottom: 4 }}>Keyboard shortcuts on each page</T>
        <T mute size={13} style={{ marginBottom: 12 }}>On a computer, or an iPad with a keyboard. Press ? on any page to see its keys. They pause while you’re typing; Esc leaves the box.</T>
        <View style={wide ? { flexDirection: 'row', flexWrap: 'wrap', gap: 14 } : { gap: 14 }}>
          {PAGE_KEYS.map(([name, keys]) => (
            <Panel key={name} title={name} style={wide ? { flexBasis: '31%', flexGrow: 1 } : null}>
              {keys.map(([k, label], i) => (
                <View key={i} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 30 }}>
                  <T size={13.5} style={{ flex: 1 }}>{label}</T><Keys k={k} small />
                </View>
              ))}
            </Panel>
          ))}
        </View>
        <Panel title="On your phone" style={{ marginTop: 14 }}>
          {GESTURES.map(([icon, a, b]) => (
            <View key={a} style={{ flexDirection: 'row', gap: 12, alignItems: 'center' }}>
              <Ionicons name={icon} size={19} color={c.accent} />
              <View style={{ flex: 1 }}><T w="semi" size={14}>{a}</T><T mute size={12.5}>{b}</T></View>
            </View>
          ))}
        </Panel>
      </> : null}
    </Screen>
  );
}
