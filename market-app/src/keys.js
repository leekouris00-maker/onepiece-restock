// Every function in the app in one list, plus the keyboard.
// The command palette (Ctrl/⌘ K), the "All functions" page and the ? shortcut sheet are all built from COMMANDS,
// so a new feature added here shows up in all three.
import { useCallback, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { emit } from './bus';
import { toast, lastUndo } from './toast';
import { exportCollection } from './csv';
import { siteBase } from './ocr';
import { modalOpen } from './modal';

export const web = Platform.OS === 'web' && typeof window !== 'undefined';
export const mac = web && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '');

const tab = p => () => router.navigate(p);
const page = p => () => router.push(p);

// group order on the All functions page
export const GROUPS = ['Go to', 'Add cards', 'Your collection', 'Prices and alerts', 'Money tools', 'Rewards', 'Settings', 'Help'];

// keys: shortcut ('n', 'g h', 'mod+k'); where: how to find it by tapping; need: 'session' = signed in only;
// tile: shown in the Profile tools grid; info: explains a function that lives on a page (no direct action)
export const COMMANDS = [
  { id: 'home', group: 'Go to', label: 'Home', sub: 'Collection value, chart, alerts and movers', icon: 'home-outline', keys: ['1', 'g h'], run: tab('/') },
  { id: 'search', group: 'Go to', label: 'Search', sub: 'Every One Piece set and card by name or number', icon: 'search-outline', keys: ['2', 'g s'], run: tab('/search') },
  { id: 'market', group: 'Go to', label: 'Market', sub: 'What’s rising and falling across all sets', icon: 'compass-outline', keys: ['3', 'g m'], run: tab('/market') },
  { id: 'collection', group: 'Go to', label: 'Collection', sub: 'Everything you own, grouped, with value and profit', icon: 'albums-outline', keys: ['4', 'g c'], run: tab('/portfolio') },
  { id: 'profile', group: 'Go to', label: 'Profile', sub: 'Account, tools, settings and privacy', icon: 'person-outline', keys: ['5', 'g p'], run: tab('/account') },

  { id: 'scan', group: 'Add cards', label: 'Scan a card', sub: 'Point the camera at a card; Stack mode adds a pile in one go', icon: 'scan-outline', keys: ['s'], run: page('/scan') },
  { id: 'add', group: 'Add cards', label: 'Add an item', sub: 'Sealed product, a card or anything else, by hand', icon: 'add-circle-outline', keys: ['n'], run: page('/item/new'), need: 'session' },
  { id: 'find', group: 'Add cards', label: 'Search and add', sub: 'Find a card, then Add English or Japanese copy on its page', icon: 'search', keys: ['/'], run: () => { emit('focus-search'); router.navigate('/search'); } },
  { id: 'addcard', group: 'Add cards', label: 'Add your own card', sub: 'Japanese cards and promos TCGplayer doesn’t list', icon: 'create-outline', run: page('/addcard'), need: 'session' },
  { id: 'import', group: 'Add cards', label: 'Import a CSV', sub: 'From Collectr, TCGplayer or a spreadsheet', icon: 'cloud-upload-outline', run: page('/import'), need: 'session', tile: true },

  { id: 'binders', group: 'Your collection', label: 'Binders', sub: 'Your cards page by page; fill from a group, a set, or pick them', icon: 'book-outline', keys: ['g i'], run: page('/binders'), tile: true },
  { id: 'export', group: 'Your collection', label: 'Export as CSV', sub: 'Opens in Excel or Google Sheets', icon: 'download-outline', run: d => exportCollection(d), need: 'session', tile: true },
  { id: 'sets', group: 'Your collection', label: 'Set progress', sub: 'How close you are to finishing each set, and the cost to finish', icon: 'grid-outline', keys: ['g r'], run: page('/sets'), tile: true },
  { id: 'sales', group: 'Your collection', label: 'Sales report', sub: 'What you sold each year, with profit', icon: 'receipt-outline', keys: ['g l'], run: page('/sales'), need: 'session', tile: true },
  { id: 'share', group: 'Your collection', label: 'Share a group', sub: 'Read-only link for a buyer or friend', icon: 'share-outline', where: 'Collection → ⋯ → Share a group', run: () => { router.navigate('/portfolio'); emit('collection-share'); }, need: 'session' },
  { id: 'select', group: 'Your collection', label: 'Edit several at once', sub: 'Move, set price paid, mark sold or remove a whole selection', icon: 'checkmark-circle-outline', where: 'Collection → tick button, or hold a row', info: true },
  { id: 'swipe', group: 'Your collection', label: 'Quick changes', sub: 'Swipe a row left for −1 / +1 / Sold; hold it for the full menu', icon: 'hand-left-outline', where: 'Collection on a phone', info: true },
  { id: 'reload', group: 'Your collection', label: 'Reload', sub: 'Latest prices and your saved items', icon: 'refresh', keys: ['r'], run: d => { d.refresh(); d.loadCatalog(true); toast('Reloading prices and your collection…'); } },

  { id: 'meta', group: 'Prices and alerts', label: 'Ban & Meta Radar', sub: 'Ban list changes and winning decks, checked against your cards', icon: 'shield-half-outline', keys: ['g b'], where: 'Market → Meta', run: () => router.navigate({ pathname: '/market', params: { tab: 'meta' } }) },
  { id: 'promos', group: 'Prices and alerts', label: 'Promos & prize events', sub: 'Official events on now, their prize cards and every promo by price', icon: 'trophy-outline', keys: ['g x'], where: 'Market → Promos', run: () => router.navigate({ pathname: '/market', params: { tab: 'promos' } }) },
  { id: 'watchlist', group: 'Prices and alerts', label: 'Watchlist', sub: 'Cards you follow, with your price alerts', icon: 'star-outline', keys: ['g w'], run: page('/watchlist'), tile: true },
  { id: 'movers', group: 'Prices and alerts', label: 'Market movers', sub: 'Biggest risers and fallers this week', icon: 'trending-up-outline', run: page('/movers'), tile: true },
  { id: 'deals', group: 'Prices and alerts', label: 'eBay deals', sub: 'Listings under the deal prices you set', icon: 'pricetag-outline', keys: ['g e'], run: page('/deals'), need: 'session', tile: true },
  { id: 'alert', group: 'Prices and alerts', label: 'Price alert on a card', sub: 'Get told when it drops or rises past your price', icon: 'notifications-outline', where: 'Any card → Price alert', info: true },
  { id: 'ebay', group: 'Prices and alerts', label: 'eBay sold prices', sub: 'Last 5 sales and the 90-day median for a card', icon: 'pricetags-outline', where: 'Any card → Last sold on eBay', info: true },
  { id: 'history', group: 'Prices and alerts', label: 'Long price history', sub: 'Charts back to 2024 with 90-day highs and lows', icon: 'analytics-outline', where: 'Any card, under the price', info: true },

  { id: 'trade', group: 'Money tools', label: 'Trade calculator', sub: 'Your cards against theirs at today’s prices', icon: 'swap-horizontal', keys: ['g t'], run: page('/trade'), tile: true },
  { id: 'deck', group: 'Money tools', label: 'Deck price', sub: 'Paste a decklist: cost, what you own, what’s missing', icon: 'layers-outline', keys: ['g d'], run: page('/deck'), tile: true },
  { id: 'offer', group: 'Money tools', label: 'Offer prices', sub: '70 / 80 / 90% of market, for buying collections', icon: 'cash-outline', where: 'Any card → Buying', info: true },
  { id: 'sell', group: 'Money tools', label: 'Sell calculator', sub: 'What you take home after eBay fees and postage', icon: 'calculator-outline', where: 'Any card → Selling', info: true },
  { id: 'grade', group: 'Money tools', label: 'Grading calculator', sub: 'Is it worth sending to PSA?', icon: 'ribbon-outline', where: 'Any card → Grading', info: true },
  { id: 'open', group: 'Money tools', label: 'Open or keep sealed', sub: 'Expected value of a booster box against its sealed price', icon: 'cube-outline', where: 'A booster box or set page → Open or keep', run: () => { router.navigate('/search'); emit('search-for', 'booster box'); } },

  { id: 'settings', group: 'Settings', label: 'Settings', sub: 'Currency, phone notifications, feedback button, reset', icon: 'settings-outline', run: page('/settings') },
  { id: 'tools', group: 'Help', label: 'Tools', sub: 'Trade, deck price, set progress, sales and more', icon: 'construct-outline', keys: ['g k'], run: page('/tools') },
  { id: 'currency', group: 'Settings', label: 'Switch AUD / USD', sub: 'Show prices in the other currency', icon: 'repeat-outline', keys: ['c'], run: d => { const v = d.cur === 'AUD' ? 'USD' : 'AUD'; d.setCur(v); toast(`Showing ${v === 'AUD' ? 'A$' : 'US$'} prices`); } },
  { id: 'push', group: 'Settings', label: 'Phone notifications', sub: 'Price alerts and the weekly summary on your phone', icon: 'phone-portrait-outline', where: 'Profile → Settings', run: page('/settings'), need: 'session' },
  { id: 'feedback', group: 'Settings', label: 'Report a problem or idea', sub: 'Sends the page you’re on and your device', icon: 'chatbubble-ellipses-outline', run: () => emit('feedback') },
  { id: 'reset', group: 'Settings', label: 'Reset this device’s settings', sub: 'Sort orders, views, recent searches, calculator setups (your collection is untouched)', icon: 'refresh-circle-outline', where: 'Profile → Settings', run: page('/settings') },
  { id: 'privacy', group: 'Settings', label: 'Privacy policy', sub: 'What’s saved and how to delete it', icon: 'shield-checkmark-outline', run: () => web && window.open(siteBase() + 'privacy.html', '_blank') },
  { id: 'rewards', group: 'Rewards', label: 'Rewards', sub: 'Daily check-in, weekly bounties, sets and milestones: fixed points, no chance', icon: 'gift-outline', keys: ['g y'], run: page('/rewards') },
  { id: 'poster', group: 'Rewards', label: 'Your bounty poster', sub: 'Your rank and bounty, ready to share', icon: 'document-text-outline', keys: ['g u'], run: page('/poster') },
  { id: 'shop', group: 'Rewards', label: 'Points shop (preview)', sub: 'Swap points for store credit, packs and singles', icon: 'sparkles-outline', keys: ['g o'], run: page('/shop') },

  { id: 'palette', group: 'Help', label: 'Search all functions', sub: 'Type what you want to do, or a card name', icon: 'flash-outline', keys: ['mod+k'], run: () => emit('palette') },
  { id: 'keys', group: 'Help', label: 'Keyboard shortcuts', sub: 'Every key for this page and the whole app', icon: 'keypad-outline', keys: ['?'], run: () => emit('cheatsheet') },
  { id: 'help', group: 'Help', label: 'All functions', sub: 'Everything the app does, where it is and its shortcut', icon: 'apps-outline', keys: ['g a'], run: page('/help') },
  { id: 'undo', group: 'Help', label: 'Undo', sub: 'Takes back the last change (remove, sold, +1, move…)', icon: 'arrow-undo-outline', keys: ['mod+z'], run: () => runUndo() },
  { id: 'back', group: 'Help', label: 'Back / close', sub: 'Closes a card, sheet or menu', icon: 'arrow-back-outline', keys: ['escape'], info: true },
  { id: 'tour', group: 'Help', label: 'Show the intro again', sub: 'The three-screen welcome', icon: 'play-circle-outline', run: () => emit('tour') },
];

// Keys that only work on one page, for the help page and the ? sheet (each page also registers them with useKeys)
export const PAGE_KEYS = [
  ['Collection', [[['j', 'arrowdown'], 'Next item'], [['k', 'arrowup'], 'Previous item'], [['enter'], 'Open the highlighted item'], [['+'], 'One more of it'], [['-'], 'One less of it'],
    [['x'], 'Tick it'], [['e'], 'Select several on / off'], [['a'], 'Select all (while selecting)'], [['m'], 'Move ticked items to a group'], [['p'], 'Set price paid on ticked items'],
    [['delete'], 'Remove ticked or highlighted (with Undo)'], [['/'], 'Search your collection'], [['v'], 'Grid / list'], [['o'], 'Owned / sold'], [['shift+x'], 'Clear search and filters'], [['b'], 'Binders']]],
  ['Search', [[['/'], 'Jump to the search box'], [['arrowdown', 'arrowup'], 'Move through results'], [['enter'], 'Open the highlighted card or set'], [['escape'], 'Clear the search']]],
  ['Card page', [[['w'], 'Watch / unwatch'], [['a'], 'Add an English copy'], [['j'], 'Add a Japanese copy'], [['arrowleft', 'arrowright'], 'Other versions of this card'],
    [['[', ']'], 'Previous / next tool (Buying, Selling…)'], [['t'], 'Open on TCGplayer'], [['e'], 'eBay AU sold listings']]],
  ['Item page', [[['mod+s', 'mod+enter'], 'Save']]],
  ['Anywhere with a mouse or keyboard', [[['tab'], 'Next button (outlined in lime)'], [['enter', 'space'], 'Press it'], [['escape'], 'Close / back']]],
];

// "mod+k" → "⌘K" / "Ctrl K"; "g h" → "G then H"
export function keyParts(k) {
  return String(k).split(' ').filter(Boolean).map(s => (s === '+' ? ['+'] : s.split('+')).map(p => ({
    mod: mac ? '⌘' : 'Ctrl', shift: '⇧', escape: 'Esc', enter: 'Enter', delete: 'Del', arrowdown: '↓', arrowup: '↑', arrowleft: '←', arrowright: '→', tab: 'Tab', space: 'Space',
  }[p] || (p.length === 1 ? p.toUpperCase() : p))).join(mac ? '' : ' '));
}

export function commandsFor(d) {
  return COMMANDS.filter(x => x.need !== 'session' || (d && d.session));
}

// ---------- the keyboard ----------
let pageStack = [];            // keys registered by the page on screen (top = current)

// A page's own keys while it's on screen: [{ keys: 'v' | ['j','arrowdown'], label, run, typing: true to work inside a text box }]
export function useKeys(list) {
  const ref = useRef(list); ref.current = list;
  useFocusEffect(useCallback(() => {
    const entry = { get: () => ref.current || [] };
    pageStack.push(entry);
    return () => { pageStack = pageStack.filter(x => x !== entry); };
  }, []));
}
export const pageKeys = () => (pageStack.length ? pageStack[pageStack.length - 1].get() : []);

export function runUndo() {
  const u = lastUndo();
  if (u) u.run(); else toast('Nothing to undo');
}

// key name for an event: 'k', 'mod+k', 'shift+x', '?', 'arrowdown', 'escape'
export function keyOf(e) {
  let k = e.key === ' ' ? 'space' : String(e.key || '').toLowerCase();
  if (k === 'backspace') k = 'delete';
  if (k === 'esc') k = 'escape';
  if (k === '=') k = '+';
  if (k === '_') k = '-';
  const mod = e.ctrlKey || e.metaKey;
  const letter = /^[a-z]$/.test(k);
  return (mod ? 'mod+' : '') + (e.shiftKey && (letter || k.length > 1) && !['shift'].includes(k) && k !== '?' ? 'shift+' : '') + k;
}

const has = (spec, k) => (Array.isArray(spec) ? spec : [spec]).includes(k);

// Installed once by the app. getD returns the data (collection, currency…) for commands that need it.
export function useGlobalKeys(getD) {
  useEffect(() => {
    if (!web) return undefined;
    let pending = null, timer = null;
    const handler = e => {
      if (e.isComposing) return;
      const t = e.target, typing = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
      const k = keyOf(e);
      if (['shift', 'control', 'meta', 'alt'].includes(k.replace(/^.*\+/, ''))) return;
      if (e.altKey) return;
      const d = getD();
      const fire = c => { e.preventDefault(); c.run(d); };

      // the palette works from anywhere, even inside a text box or a sheet
      if (k === 'mod+k') { e.preventDefault(); emit('palette'); return; }
      if (modalOpen()) return;                         // a sheet or menu has the keyboard

      // page keys first (they can take over / and Esc)
      for (const c of pageKeys()) {
        if ((typing && !c.typing) || (c.when && !c.when())) continue;
        if (has(c.keys, k)) { fire(c); return; }
      }
      if (typing) {
        if (k === 'escape') t.blur();
        return;
      }
      if (k === 'mod+z') { e.preventDefault(); runUndo(); return; }
      if (k.startsWith('mod+')) return;               // leave copy / paste / browser keys alone

      if (pending) {
        const combo = pending + ' ' + k; pending = null; clearTimeout(timer);
        const c = commandsFor(d).find(x => x.keys && x.keys.includes(combo) && x.run);
        if (c) { fire(c); return; }
      }
      if (k === 'g') { pending = 'g'; timer = setTimeout(() => { pending = null; }, 1300); return; }
      if (k === 'escape') { if (router.canGoBack()) router.back(); return; }
      const c = commandsFor(d).find(x => x.keys && x.keys.includes(k) && x.run);
      if (c) fire(c);
    };
    window.addEventListener('keydown', handler, true);    // capture: before text boxes and lists see the key
    return () => { window.removeEventListener('keydown', handler, true); clearTimeout(timer); };
  }, []);
}

// Lime outline round whatever the keyboard is on (Tab key), so you can see where you are
export function installFocusStyle() {
  if (!web || document.getElementById('kbd-focus')) return;
  const s = document.createElement('style');
  s.id = 'kbd-focus';
  s.textContent = '[role="button"]:focus-visible,[role="link"]:focus-visible,[role="tab"]:focus-visible,[role="checkbox"]:focus-visible,a:focus-visible{outline:2px solid #c6f432 !important;outline-offset:2px;border-radius:12px}';
  document.head.appendChild(s);
}
