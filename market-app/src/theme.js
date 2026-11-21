// Clean dark look: green-black background, one lime accent with a soft glow.
const dark = {
  bg: '#0a0d0b', panel: '#131815', soft: '#1a201c', raise: '#232a25', ink: '#f2f5f0', mute: '#8b958d', line: '#222a24',
  accent: '#c6f432', accentDim: 'rgba(198,244,50,0.14)', onAccent: '#0a0d0b', glow: '#3f6b1f',
  gold: '#c6f432', red: '#c6f432', band: '#0a0d0b', link: '#c6f432',
  paper: '#f2f5f0', paperInk: '#0a0d0b', paperMute: '#5b655d', paperLine: '#d9ded6',
  up: '#c6f432', down: '#ff5b5b', hi: '#1a201c',
};

export const F = {
  head: 'Manrope_800ExtraBold',
  headMed: 'Manrope_600SemiBold',
  serif: 'Manrope_800ExtraBold',
  serifIt: 'Manrope_700Bold',
  text: 'Manrope_400Regular',
  medium: 'Manrope_500Medium',
  semi: 'Manrope_600SemiBold',
  bold: 'Manrope_700Bold',
};

export function useTheme() {
  return dark;
}
