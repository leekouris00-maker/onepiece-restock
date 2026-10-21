"""One-off check on the test/gametraders branch (not part of the bot): the real box check, with the new
config.json entry, against the real shop. Dry run: posts and saves nothing."""
import tcg_bot as b

cfg = b.load_config()
b.DRY_RUN[0] = True
print("config warnings:", b.CONFIG_WARNINGS or "none")
b.begin_check(cfg, status={}, skip_down=False)
gt = [s for s in cfg["sealed"]["shopify_collections"] if s["name"].startswith("Gametraders")]
print("entry:", gt)
only = dict(cfg, extra_shops=False)
only["sealed"] = dict(cfg["sealed"], shopify_collections=gt, shopify_products=[], woocommerce=[], shopify_search=[])
finds, by_shop = b.check_sealed(only)
m = b.run_metrics()
print(f"\nGametraders read: {m['requests']} requests, {m['kb_wire']} KB on the wire ({m['kb']} KB unzipped), "
      f"{m['secs']}s")
print("buyable now (would alert):", [(f["name"], f["price"]) for f in finds] or "none")
for l in by_shop.get("Gametraders Modbury Heights") or []:
    print(f"  watching: {l['name']} | {'IN STOCK' if l['available'] else 'sold out'} | ${l['price']} | page {l['page']}"
          f" | {l['note'] or '-'}")
known = {}
first = b.new_listings(by_shop, known, finds, {})
print("\nfirst read remembers, no alerts:", len(first) == 0, {k: len(v) for k, v in known.items()})
