// Small settings kept on this device (last choices when adding, sell-calculator setup, recent searches…)
import { useCallback, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const mem = {};
const subs = {};

export async function getPref(key, fallback) {
  if (key in mem) return mem[key];
  try { const v = await AsyncStorage.getItem('pref:' + key); mem[key] = v == null ? fallback : JSON.parse(v); } catch { mem[key] = fallback; }
  return mem[key];
}

export function setPref(key, value) {
  mem[key] = value;
  AsyncStorage.setItem('pref:' + key, JSON.stringify(value)).catch(() => {});
  (subs[key] || []).forEach(f => f(value));
}

export function usePref(key, fallback) {
  const [v, setV] = useState(key in mem ? mem[key] : fallback);
  useEffect(() => {
    let alive = true;
    const f = x => setV(x === undefined ? fallback : x);
    getPref(key, fallback).then(x => alive && setV(x));
    (subs[key] ||= []).push(f);
    return () => { alive = false; subs[key] = subs[key].filter(g => g !== f); };
  }, [key]);
  const set = useCallback(x => setPref(key, typeof x === 'function' ? x(mem[key] ?? fallback) : x), [key]);
  return [v, set];
}

// Clear this device's settings (sort orders, views, recent searches, calculator setups…). Returns what was
// there so it can be put back with restorePrefs. Your collection lives in your account and isn't touched.
export async function resetPrefs(keep = ['toured', 'spinPoints']) {
  const keys = (await AsyncStorage.getAllKeys()).filter(k => k.startsWith('pref:') && !keep.includes(k.slice(5)));
  const pairs = keys.length ? await AsyncStorage.multiGet(keys) : [];
  if (keys.length) await AsyncStorage.multiRemove(keys);
  for (const k of keys) { const name = k.slice(5); delete mem[name]; (subs[name] || []).forEach(f => f(undefined)); }
  return pairs;
}
export function restorePrefs(pairs) {
  for (const [k, v] of pairs || []) { if (v == null) continue; try { setPref(k.slice(5), JSON.parse(v)); } catch {} }
}
