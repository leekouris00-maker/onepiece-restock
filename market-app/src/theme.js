import { useColorScheme } from 'react-native';

const light = {
  bg: '#ffffff', panel: '#ffffff', soft: '#f6f4f1', ink: '#151515', mute: '#6b6762', line: '#e8e4de',
  gold: '#a8875a', red: '#8e0d1f', band: '#8e0d1f', link: '#7a1222', up: '#1d6b40', down: '#a3122a', hi: '#faf6ef',
};
const dark = {
  bg: '#121212', panel: '#1a1a1a', soft: '#1f1e1d', ink: '#efece6', mute: '#a39e96', line: '#2c2a28',
  gold: '#c9a977', red: '#e0475b', band: '#8e0d1f', link: '#f08a97', up: '#6fcf97', down: '#f07a8a', hi: '#24211d',
};

export const F = {
  serif: 'BodoniModa_600SemiBold',
  serifIt: 'BodoniModa_500Medium_Italic',
  text: 'InterTight_400Regular',
  medium: 'InterTight_500Medium',
  semi: 'InterTight_600SemiBold',
  bold: 'InterTight_700Bold',
};

export function useTheme() {
  return useColorScheme() === 'dark' ? dark : light;
}
