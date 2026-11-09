import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tcg_bot as tb, chain_shops as cs
cfg = tb.load_config(); tb.begin_check(cfg)
watch = cfg.get("sealed_watch", tb.DEFAULT_SEALED_WATCH)
t = time.time()
for rnd in range(3):
    st = tb.read_json(cs.state_path(tb), {})
    if st: st[cs.JB_NAME]["ts"] = 1; st[cs.JB_NAME]["bf_ts"] = 0; tb.atomic_write_json(cs.state_path(tb), st)
    f, l = cs.jb_boxes(tb, cfg["sealed"]["max_price"], watch)
    print(f"\n== round {rnd}: {time.time()-t:.1f}s finds={len(f)} listings={None if l is None else len(l)}")
    for x in f: print("FIND", x["price"], x["name"], "|", x["note"], x["cart"])
    for x in l or []: print("LIST", x["available"], x["price"], x["group"], x.get("quiet"), x["name"], "|", x["note"])
st = tb.read_json(cs.state_path(tb), {})[cs.JB_NAME]
print("cursor", st.get("cursor"), "files", st.get("files"))
for h, e in st["handles"].items(): print(e.get("ok"), h, e)
print(tb.run_metrics() if hasattr(tb, "run_metrics") else "")
