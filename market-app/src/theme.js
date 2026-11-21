// Grand Line look: deep-sea navy, treasure gold, parchment "bounty" labels.
const sea = {
  bg: '#0b1a2e', panel: '#10233b', soft: '#142a47', raise: '#1b3658', ink: '#eef2f7', mute: '#8ea3bd', line: '#22405f',
  accent: '#e0b04a', accentDim: 'rgba(224,176,74,0.16)', gold: '#e0b04a', red: '#e0b04a', band: '#0b1a2e', link: '#e0b04a',
  paper: '#f1e4c3', paperInk: '#3a2812', paperMute: '#7a6440', paperLine: '#cdb98c',
  up: '#5fd68a', down: '#ff7a6b', hi: '#142a47',
};

export const F = {
  head: 'Oswald_700Bold',     // condensed caps headings and bounty figures
  headMed: 'Oswald_500Medium',
  serif: 'Oswald_700Bold',
  serifIt: 'Lato_700Bold',
  text: 'Lato_400Regular',
  medium: 'Lato_400Regular',
  semi: 'Lato_700Bold',
  bold: 'Lato_900Black',
};

export function useTheme() {
  return sea;
}
