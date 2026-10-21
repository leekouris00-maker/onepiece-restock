"""One-off check on the test/gametraders branch (not part of the bot): how should the bot read
Gametraders Modbury Heights (gametradersinglefarm.com.au)? It uses the bot's own fetch code, so
robots.txt, pacing and headers are exactly what real checks would use. Posts and saves nothing."""
import time
import urllib.parse

import tcg_bot as b

BASE = "https://www.gametradersinglefarm.com.au"
EB05 = "pre-order-one-piece-card-game-extra-booster-box-tba-eb-05-30th-october"

cfg = b.load_config()
b.DRY_RUN[0] = True
b.begin_check(cfg, status={}, skip_down=False)
watch = cfg.get("sealed_watch", b.DEFAULT_SEALED_WATCH) or []


def kb():
    return round(b.HTTP.m["bytes"] / 1024)


print("robots.txt:")
for path in ("/collections/trading-cards/products.json?limit=250", "/collections/all/products.json?limit=250",
             "/products.json?limit=250", "/search/suggest.json?q=one%20piece", f"/products/{EB05}.js"):
    print(f"  {path}: {'allowed' if b.HTTP.allowed(BASE + path) else 'BLOCKED'}")
host = urllib.parse.urlsplit(BASE).hostname
print("  rules for us:", len((b.HTTP.robots.get(host) or {}).get("rules") or []), "lines",
      "(unreachable)" if (b.HTTP.robots.get(host) or {}).get("unreachable") else "")


def collection(handle, max_pages=8):
    b.HTTP.reset_metrics()
    url = f"{BASE}/collections/{handle}/products.json?limit=250"
    t0 = time.time()
    prods, pages = b.shopify_collection(url, max_pages=max_pages)
    if prods is None:
        print(f"\n[{handle}] couldn't be read")
        return
    op = [p for p in prods if "one piece" in (p.get("title") or "").lower()]
    n_pages = max(pages.values(), default=1)
    print(f"\n[{handle}] {len(prods)} products on {n_pages} page(s)"
          f"{' (hit the page cap)' if len(prods) >= 250 * max_pages else ''}, {len(op)} One Piece, "
          f"{kb()} KB, {time.time() - t0:.1f}s")
    for p in op:
        v = p.get("variants") or [{}]
        avail = any(x.get("available") for x in v)
        kind = "BOX" if b.is_box_title(p["title"]) else ("watch" if b.watch_item(p["title"], watch) else "-")
        print(f"   page {pages.get(p['handle'])} {kind:5} {'IN STOCK' if avail else 'sold out'} ${v[0].get('price')}  "
              f"{p['title']}  [created {p.get('created_at', '')[:10]}]")
    eb = pages.get(EB05)
    print(f"   EB-05 box: {'page ' + str(eb) if eb else 'NOT in this list'}")


for h in ("trading-cards", "latest-preorders", "one-piece", "one-piece-card-game",
          "trading-cards/one-piece", "all/one-piece", "all"):
    collection(h)

print("\nsearch (the bot's search mode):")
for q in b.SEARCH_QUERIES:
    d = b.fetch_json(b._suggest_url(BASE, q)) or {}
    ps = d.get("resources", {}).get("results", {}).get("products", [])
    print(f"  '{q}': {len(ps)} results; One Piece ones: {[p['title'] for p in ps if 'one piece' in p['title'].lower()]}")
u = (f"{BASE}/search/suggest.json?q=one%20piece&resources[type]=product&resources[limit]=10"
     "&resources[options][unavailable_products]=show&resources[options][fields]=title")
d = b.fetch_json(u) or {}
ps = d.get("resources", {}).get("results", {}).get("products", [])
print(f"  title-only, sold out shown: {[(p['title'], p.get('available')) for p in ps]}")

print("\nEB-05 product page (.js):")
p = b.fetch_json(f"{BASE}/products/{EB05}.js") or {}
print("  ", p.get("title"), "| available:", p.get("available"), "| price:", p.get("price"),
      "| variants:", [(v.get("id"), v.get("available")) for v in p.get("variants", [])])

print("\nThe bot's own box check on trading-cards (what an alert would say):")
finds, listings = b.shopify_boxes("Gametraders Modbury Heights",
                                  f"{BASE}/collections/trading-cards/products.json?limit=250",
                                  cfg["sealed"]["max_price"], watch)
print("  buyable finds:", [(f["name"], f["price"]) for f in finds])
for l in listings or []:
    print(f"  listing: {l['name']} | {'in stock' if l['available'] else 'sold out'} | ${l['price']} | {l['note']}")
print("\nrequests:", b.run_metrics()["requests"])
