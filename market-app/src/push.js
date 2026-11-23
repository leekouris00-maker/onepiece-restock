// Phone notifications for price alerts (web push). Works in Chrome/Android and, on iPhone (iOS 16.4+),
// only in the home-screen app. The sender runs each morning on GitHub (push_alerts.py) after prices update.
import { Platform } from 'react-native';
import { RAW_BASE } from './data';

export function pushState() {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return 'unsupported';
  const ios = /iPhone|iPad/.test(navigator.userAgent || '');
  const standalone = window.matchMedia?.('(display-mode: standalone)').matches || navigator.standalone;
  if (ios && !standalone) return 'homescreen';
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return 'unsupported';
  if (Notification.permission === 'denied') return 'denied';
  return 'ok';
}

const ready = () => Promise.race([navigator.serviceWorker.ready, new Promise((_, rej) => setTimeout(() => rej(new Error('The app’s offline helper isn’t running yet. Close and reopen the app, then try again.')), 6000))]);

export async function currentSub() {
  try { const reg = await ready(); return await reg.pushManager.getSubscription(); } catch { return null; }
}

const b64 = s => { const p = '='.repeat((4 - (s.length % 4)) % 4), raw = atob((s + p).replace(/-/g, '+').replace(/_/g, '/')); return Uint8Array.from(raw, ch => ch.charCodeAt(0)); };

export async function turnOn(d) {
  const r = await fetch(RAW_BASE + 'push_public_key.txt?h=' + Date.now()).catch(() => null);
  const key = r && r.ok ? (await r.text()).trim() : '';
  if (!key) throw new Error('Notifications are still being set up on the server. Try again tomorrow.');
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') throw new Error('Notifications were not allowed. You can allow them in your phone’s settings for this app.');
  const reg = await ready();
  let sub = await reg.pushManager.getSubscription();
  if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
  const ua = navigator.userAgent || '';
  await d.savePushSub(sub, /iPhone/.test(ua) ? 'iPhone' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac/.test(ua) ? 'Mac' : 'other');
  return sub;
}

export async function turnOff(d) {
  const sub = await currentSub();
  if (!sub) return;
  await d.removePushSub(sub.endpoint);
  await sub.unsubscribe();
}
