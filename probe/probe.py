import re, sys, os, json, html
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tcg_bot as tb
cfg = tb.load_config(); tb.begin_check(cfg)
def get(url):
    try:
        b = tb.HTTP.fetch(url)
        print(f"\n### OK {len(b):,} bytes  {url}")
        return b.decode("utf-8", "replace")
    except Exception as e:
        print(f"\n### FAIL {type(e).__name__}: {e}  {url}")
        return ""
def locs(x): return [html.unescape(m) for m in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)]
# ---- JB
idx = get("https://www.jbhifi.com.au/sitemap.xml"); L = locs(idx)
prod = [u for u in L if "sitemap_products_" in u]
print(len(L), "sitemaps;", len(prod), "product sitemaps; last:", prod[-2:])
print("collections sitemaps:", [u for u in L if "collections" in u][:3])
if prod:
    t = get(prod[-1]); pl = [u for u in locs(t) if "/products/" in u]
    print("tail products:", len(pl), "sample:", pl[:2], pl[-2:])
    print("one-piece in tail:", [u for u in pl if "one-piece" in u][:20])
    print("lastmod sample:", re.findall(r"<lastmod>[^<]+</lastmod>", t)[:2])
    mid = get(prod[len(prod)//2]); ml = [u for u in locs(mid) if "/products/" in u]
    print("mid products:", len(ml), "one-piece:", [u for u in ml if "one-piece" in u][:20])
for cs in [u for u in L if "collections" in u][:15]:
    c = get(cs); hits = [u for u in locs(c) if re.search(r"trading|tcg|one-piece|card-game", u)]
    print("collection hits:", hits[:30])
js = get("https://www.jbhifi.com.au/products/one-piece-card-game-extra-booster-display-heroines-edition-box-24-pack-eb-03.js")
try:
    p = json.loads(js); print({k: (v if k in ("title","handle","type","vendor","tags","price","available","options") else "...") for k, v in p.items()})
    for v in p["variants"]: print({k: v.get(k) for k in ("id","title","public_title","option1","option2","sku","available","price","name")})
except Exception as e: print("js parse", e, js[:300])
for u in ["https://www.jbhifi.com.au/collections/trading-cards/products.json?limit=3",
          "https://www.jbhifi.com.au/collections/one-piece/products.json?limit=3",
          "https://www.jbhifi.com.au/products.json?limit=250&page=1"]:
    x = get(u)
    try:
        pr = json.loads(x)["products"]; print(len(pr), [(q["title"][:50], q.get("published_at"), q.get("created_at")) for q in pr[:4]], "...", [(q["title"][:40], q.get("published_at")) for q in pr[-2:]])
    except Exception as e: print("no products", e)
# ---- Toymate
ti = get("https://toymate.com.au/sitemap.xml"); print(locs(ti))
for n in (1, 2, 3, 4, 5, 6, 7, 8):
    s = get(f"https://checkout.toymate.com.au/xmlsitemap.php?type=products&page={n}"); sl = locs(s)
    print("page", n, len(sl), "sample:", sl[:2], sl[-1:], "one-piece:", [u for u in sl if "one-piece" in u][:60])
    if not sl: break
cat = get("https://checkout.toymate.com.au/xmlsitemap.php?type=categories&page=1")
print("cat hits:", [u for u in locs(cat) if re.search(r"one-piece|trading|tcg|card", u)])
pg = get("https://toymate.com.au/one-piece-card-game-legacy-of-the-master-op-12-booster-pack")
for pat in (r"<title>.*?</title>", r"<meta[^>]+(?:og:title|price|availability)[^>]*>", r"<script type=\"application/ld\+json\">.*?</script>",
            r".{200}Out of Stock.{200}", r".{300}Stock:.{200}", r".{200}Maximum purchase.{100}", r"<h1.*?</h1>",
            r".{150}data-product-price.{200}", r".{100}BCData.{1500}", r".{200}instock.{200}", r".{200}CTA in store.{300}"):
    for m in re.findall(pat, pg, re.S | re.I)[:3]:
        print("\n--", pat[:30], "=>", re.sub(r"\s+", " ", m)[:1800])
print(tb.HTTP.robots.get("toymate.com.au", {}).get("rules", [])[:60])
