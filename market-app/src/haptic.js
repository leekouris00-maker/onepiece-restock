// A small tap you can feel. Android browsers have navigator.vibrate; iPhone Safari (iOS 18+) has no vibrate,
// but toggling a hidden "switch" checkbox makes the phone tick. Best effort: silently does nothing elsewhere.
import { Platform } from 'react-native';

let box = null;
export function haptic(kind = 'light') {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return;
  try {
    if (typeof navigator !== 'undefined' && navigator.vibrate) { navigator.vibrate(kind === 'success' ? [12, 60, 12] : kind === 'warn' ? [30, 50, 30] : 10); return; }
    if (!box) {
      box = document.createElement('label');
      const i = document.createElement('input');
      i.type = 'checkbox'; i.setAttribute('switch', ''); i.tabIndex = -1;
      box.appendChild(i);
      box.setAttribute('aria-hidden', 'true');
      box.style.cssText = 'position:fixed;left:-9999px;top:0;width:1px;height:1px;opacity:0;pointer-events:none';
      document.body.appendChild(box);
    }
    box.click();
    if (kind === 'success') setTimeout(() => box && box.click(), 90);
  } catch {}
}
