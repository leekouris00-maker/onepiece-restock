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
    getPref(key, fallback).then(x => alive && setV(x));
    (subs[key] ||= []).push(setV);
    return () => { alive = false; subs[key] = subs[key].filter(f => f !== setV); };
  }, [key]);
  const set = useCallback(x => setPref(key, typeof x === 'function' ? x(mem[key] ?? fallback) : x), [key]);
  return [v, set];
}
