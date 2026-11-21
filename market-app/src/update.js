// Home-screen web app on iPhone: Safari keeps the old page around, so a fully closed app can still open
// an old version. On launch and whenever the app comes back to the front, ask the site (bypassing every
// cache) which build is current; if it's newer than the one running, reload once onto it.
import { AppState, Platform } from 'react-native';

const SCRIPT = /_expo\/static\/js\/web\/[^"'\s]+\.js/g;
const scriptsIn = text => [...new Set(String(text).match(SCRIPT) || [])].sort().join('|');

export function watchForUpdates() {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return () => {};
  const srcs = [...document.scripts].map(s => s.src).filter(s => s.includes('/_expo/static/js/web/'));
  const running = scriptsIn(srcs.join(' '));
  if (!running) return () => {};                              // dev server: nothing to compare
  const base = srcs[0].slice(0, srcs[0].indexOf('_expo/'));    // e.g. https://…github.io/onepiece-restock/
  let busy = false;
  const check = async () => {
    if (busy) return;
    busy = true;
    try {
      const r = await fetch(`${base}?check=${Date.now()}`, { cache: 'no-store' });
      if (!r.ok) return;
      const latest = scriptsIn(await r.text());
      if (!latest || latest === running) return;
      let tried = null;
      try { tried = sessionStorage.getItem('op-updated-to'); sessionStorage.setItem('op-updated-to', latest); } catch {}
      if (tried === latest) return;                            // already reloaded for this build once: don't loop
      location.replace(`${location.pathname}?v=${Date.now()}`); // new address = no cached copy of the page
    } catch {} finally { busy = false; }
  };
  check();
  const sub = AppState.addEventListener('change', st => { if (st === 'active') check(); });
  return () => sub.remove();
}
