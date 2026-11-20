// One dark look everywhere: black ground, soft grey surfaces, mint-teal accent, coral for drops.
const dark = {
  bg: '#000000', panel: '#111113', soft: '#18181b', raise: '#1f1f23', ink: '#f4f4f5', mute: '#9b9ba1', line: '#2a2a2f',
  accent: '#5fd1c1', accentDim: 'rgba(95,209,193,0.16)', gold: '#5fd1c1', red: '#5fd1c1', band: '#000000', link: '#5fd1c1',
  up: '#5fd1c1', down: '#ff6f61', hi: '#18181b',
};

export const F = {
  serif: 'Lato_900Black',   // big figures and titles
  serifIt: 'Lato_700Bold',
  text: 'Lato_400Regular',
  medium: 'Lato_400Regular',
  semi: 'Lato_700Bold',
  bold: 'Lato_900Black',
};

export function useTheme() {
  return dark;
}
