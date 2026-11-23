// Tiny event bus for app-wide nudges (keyboard shortcut → focus the search box).
// A listener that starts within 1.5 s of an event still gets it (the page may still be opening).
const subs = {}, last = {};
export const on = (name, f) => {
  (subs[name] ||= []).push(f);
  if (last[name] && Date.now() - last[name].t < 1500) setTimeout(() => f(last[name].v), 30);
  return () => { subs[name] = subs[name].filter(x => x !== f); };
};
export const emit = (name, v) => { last[name] = { t: Date.now(), v }; (subs[name] || []).forEach(f => f(v)); };
