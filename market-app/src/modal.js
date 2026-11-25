// How many sheets / menus / the palette are open. The keyboard's page shortcuts pause while one is up.
import { useEffect } from 'react';

let modals = 0;
export const modalOpen = () => modals > 0;

export function useModalPause(open) {
  useEffect(() => { if (!open) return undefined; modals++; return () => { modals = Math.max(0, modals - 1); }; }, [open]);
}
