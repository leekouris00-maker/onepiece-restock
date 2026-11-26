// Tools (26 Nov 2026): every calculator and collection tool in one short list (Profile → Tools).
import React from 'react';
import { router } from 'expo-router';
import { useData } from '../src/data';
import { MenuItem, Panel, T } from '../src/ui';
import { Screen } from '../src/screen';
import { COMMANDS } from '../src/keys';
import { useTheme } from '../src/theme';

export default function Tools() {
  const d = useData(), c = useTheme();
  const tools = COMMANDS.filter(x => x.tile && (x.need !== 'session' || d.session));
  const add = COMMANDS.find(x => x.id === 'addcard');
  return (
    <Screen max={720}>
      <T mute size={14} style={{ marginBottom: 12 }}>Calculators and collection tools. On every card page you’ll also find Buying, Selling, Grading and Price alert.</T>
      <Panel style={{ gap: 2 }}>
        {tools.map(x => <MenuItem key={x.id} icon={x.icon} label={x.label} sub={x.sub} onPress={() => x.run(d)} />)}
        {d.session && add ? <MenuItem icon={add.icon} label={add.label} sub={add.sub} onPress={() => add.run(d)} /> : null}
      </Panel>
      <MenuItem icon="apps-outline" label="All functions" sub="Everything the app does, and keyboard shortcuts" onPress={() => router.push('/help')} />
    </Screen>
  );
}
