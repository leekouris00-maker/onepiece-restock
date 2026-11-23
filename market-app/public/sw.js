// One Piece Market: lets the home-screen app open without signal.
// Pages: network first (so updates arrive), saved copy when offline. Built files (names change every build): saved copy first.
// Prices, your collection and card pictures come from other sites and are not touched here.
const CACHE = 'opm-v1';
self.addEventListener('install', e => { self.skipWaiting(); });
self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== CACHE) await caches.delete(k);
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', e => {
  const r = e.request, u = new URL(r.url);
  if (r.method !== 'GET' || u.origin !== self.location.origin || !u.pathname.startsWith(new URL(self.registration.scope).pathname)) return;
  if (u.searchParams.has('check')) return;                       // the app's own "is there a newer version?" check
  const isPage = r.mode === 'navigate' || r.destination === 'document';
  if (isPage) {
    e.respondWith((async () => {
      try {
        const res = await fetch(r);
        if (res.ok) { const c = await caches.open(CACHE); c.put(new URL(self.registration.scope).href, res.clone()); }
        return res;
      } catch {
        const c = await caches.open(CACHE);
        return (await c.match(new URL(self.registration.scope).href)) || Response.error();
      }
    })());
    return;
  }
  e.respondWith((async () => {
    const c = await caches.open(CACHE);
    const hit = await c.match(r);
    if (hit) return hit;
    const res = await fetch(r);
    if (res.ok && (u.pathname.includes('/_expo/') || u.pathname.includes('/assets/') || u.pathname.includes('/ocr/') || /\.(png|json|ttf|woff2?)$/.test(u.pathname))) c.put(r, res.clone());
    return res;
  })());
});
