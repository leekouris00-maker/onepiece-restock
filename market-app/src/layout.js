import { useWindowDimensions } from 'react-native';

// Wide screens (a computer browser) get a sidebar and multi-column pages; phones keep the bottom-tab layout.
export const WIDE = 1000;
export const SIDE = 228;

export function useWide() {
  const { width } = useWindowDimensions();
  return width >= WIDE;
}

// Page padding and the usable content width inside a page with the given max width
export function useLayout(max = 1100) {
  const { width } = useWindowDimensions();
  const wide = width >= WIDE;
  const pad = wide ? 32 : 18;
  const page = Math.min(width - (wide ? SIDE : 0), max);
  return { wide, pad, page, inner: page - pad * 2 };
}

// Card tiles sized so a computer row fills the page edge to edge; phones keep the fixed carousel size
export function useTiles(max = 1100, min = 128, gap = 18) {
  const { wide, inner } = useLayout(max);
  if (!wide) return { wide, width: 120, cols: 0 };
  const cols = Math.max(2, Math.floor((inner + gap) / (min + gap)));
  return { wide, cols, width: Math.floor((inner - gap * (cols - 1)) / cols) };
}
