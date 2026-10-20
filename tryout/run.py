"""Try-out against the real shops (test branch only; no webhooks, so nothing can post)."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import tcg_bot as tb  # noqa: E402

OUT = HERE
tb.DROPS_PATH = os.path.join(OUT, "singles_prices.json")
cfg = tb.load_config()
assert not any(k.startswith("discord_webhook") for k in cfg["alerts"]), "no webhooks on the test branch"
tb.begin_check(cfg)

print("=== 1. Elemental want-list prices (in-stock copy) for the Sabo deck cards, any price")
nums = ["OP05-015", "OP13-016", "OP05-021", "EB03-042", "OP12-086", "OP05-006", "OP04-083", "OP07-085",
        "OP13-017", "OP14-096"]
for num in nums:
    card = {"name": "", "num": num, "qty": 1, "max": 9999, "deck": "Sabo"}
    finds = tb.elemental_card(card, "https://elementalarcade.com.au")
    sug = tb.suggest("https://elementalarcade.com.au", num)
    raw = [(p["title"][:60], p.get("price_min"), p.get("available")) for p in sug]
    print(f"{num}: in stock now -> " + (", ".join(f"{f['note'][:55]} {tb.price_label(f)}" for f in finds) or "none"))
    print(f"    search said: {raw}")

print("\n=== 2. Want-list check as the bot runs it (config.json max prices)")
t0 = time.perf_counter()
for f in tb.check_singles(cfg):
    if not f.get("value_pick"):
        print(f"  {f['name']} {tb.price_label(f)} @ {f['shop']}  (max {next((c['max'] for c in cfg['singles']['cards'] if c['num'] in f['name']), '?')})")
print(f"  ({time.perf_counter() - t0:.1f}s)")

print("\n=== 3. Whole singles lists")
s = tb.drops_settings(cfg)
print("lists:", [x["url"] for x in s["shops"]])
store = tb.load_drops_store()
for sh in s["shops"]:
    tb.HTTP.reset_metrics()
    t0 = time.perf_counter()
    products, complete = tb.read_catalog(sh["url"])
    m = tb.run_metrics()
    secs = time.perf_counter() - t0
    if products is None:
        print(f"{sh['name']}: COULDN'T READ")
        continue
    n = tb.record_catalog(store, sh["name"], tb.origin(sh["url"]), products, complete)
    entries = [tb.catalog_entry(p) for p in products]
    ok = [e for e in entries if e]
    print(f"{sh['name']}: {len(products)} products, complete={complete}, pages={tb.PAGE_HINTS.get(sh['url'])}, "
          f"{secs:.1f}s, {m['requests']} requests, {m['kb_wire']} KB on the wire, {m['kb']} KB unpacked, "
          f"{len(ok)} with a price, {sum(1 for e in ok if e['avail'])} NM in stock, {n} changes")
    nm = sum(1 for p in products if any('near mint' in str(v.get('title', '')).lower() for v in p.get('variants', [])))
    print(f"   {nm} have a Near Mint variant; variant titles seen: "
          f"{sorted({str(v.get('title')) for p in products[:400] for v in p.get('variants', [])})[:12]}")
    for p, e in list(zip(products, entries))[:4]:
        print(f"   e.g. {e}")
    nonum = [e["name"] for e in ok if not tb.CARD_NUM_RE.search(e["name"])]
    print(f"   names without a card number: {len(nonum)} e.g. {nonum[:5]}")
tb.save_drops_store(store)
print(f"store: {len(store['items'])} singles, {os.path.getsize(tb.DROPS_PATH):,} bytes")

print("\n=== 4. Read again a minute later (should be ~no changes), then best drops")
time.sleep(60)
for sh in s["shops"]:
    products, complete = tb.read_catalog(sh["url"])
    if products is not None:
        print(f"{sh['name']}: {tb.record_catalog(store, sh['name'], tb.origin(sh['url']), products, complete)} changes")
tb.save_drops_store(store)
print("best drops now (window 6h):", tb.best_drops(store, time.time(), 6))
e = tb.drops_embed(tb.best_drops(store, time.time(), 6), 6, store, s)
print(json.dumps(e, ensure_ascii=False)[:600])
