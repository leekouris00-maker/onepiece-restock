#!/usr/bin/env python3
"""
Where v2's speed comes from: v2 with its speed-ups switched off one at a time, cumulatively, on the cloud
workload, alternating with v1 and full v2.

    python bench/ablate.py --runs 8          -> bench/results/ablation.json

Each variant is tcg_bot.py with a few lines swapped by exact-text patches (listed below), so the
production file carries no benchmark switches. Removing them in a different order would split the
saving a little differently, because the changes interact (a retry's sleep only costs time when it
sits on the slowest path).
"""
import argparse
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench  # noqa: E402
from mockserver import Profile  # noqa: E402

REPO = os.path.dirname(HERE)


def patch(src, pairs):
    for old, new in pairs:
        if src.count(old) != 1:
            raise SystemExit(f"ablation patch no longer matches tcg_bot.py: {old[:70]!r}")
        src = src.replace(old, new)
    return src


NO_PARALLEL = [
    ('''    ex = _pool("phases", 4)
    fs = ex.submit(check_sealed, cfg) if sealed else None
    fg = ex.submit(check_singles, cfg) if singles else None
    return (fs.result() if fs else None), (fg.result() if fg else None)''',
     '''    s = check_sealed(cfg) if sealed else None
    g = check_singles(cfg) if singles else None
    return s, g'''),
    ('''    if len(items) <= 1:
        return [fn(x) for x in items]''',
     '''    if leaf or len(items) <= 1:
        return [fn(x) for x in items]'''),
    ("JOB_WORKERS = 16", "JOB_WORKERS = 8"),
]
V1_RETRIES = [
    ('''            ra = _retry_after(h, data if status == 429 else b"")
            err = HttpError(status, http.client.responses.get(status, ""), ra)
            if status in RETRY_STATUSES''',
     '''            ra = _retry_after(h, data if status == 429 else b"")
            err = HttpError(status, http.client.responses.get(status, ""), ra)
            time.sleep(1.5 * (attempt + 1))             # v1: every failure waits, even the last one
            if attempt + 1 < tries:
                last = err
                continue
            raise err
            if status in RETRY_STATUSES'''),
]
NO_GZIP = [('"Accept-Encoding": "gzip, deflate"', '"Accept-Encoding": "identity"')]
NO_KEEPALIVE = [('''             "Accept": "application/json, text/plain, */*"}''',
                 '''             "Accept": "application/json, text/plain, */*", "Connection": "close"}''')]

# (name, label, patches applied on top of the previous step, config change)
STEPS = [
    ("v2", "v2 as shipped", [], {}),
    ("no_skip", "asks down shops every check", [], {"down_retry_minutes": 0}),
    ("no_parallel", "no extra parallelism", NO_PARALLEL, {}),
    ("v1_retries", "v1 retries (4.5 s per refused request)", V1_RETRIES, {}),
    ("no_gzip", "no gzip", NO_GZIP, {}),
    ("no_keepalive", "new connection per request", NO_KEEPALIVE, {}),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=8)
    ap.add_argument("--scale", type=float, default=1.6)
    ap.add_argument("--v1", default=os.path.join(HERE, "baseline", "tcg_bot_v1.py"))
    ap.add_argument("--out", default=os.path.join(HERE, "results", "ablation.json"))
    a = ap.parse_args()
    os.makedirs(bench.CACHE, exist_ok=True)
    with open(os.path.join(REPO, "tcg_bot.py"), encoding="utf-8") as f:
        src = f.read()
    h = bench.Harness("baseline", Profile(scale=a.scale))
    try:
        dirs, cfg_extra = {}, {}
        for name, label, pairs, cfg_change in STEPS:
            src = patch(src, pairs)
            cfg_extra.update(cfg_change)
            cfg = bench.cloud_config()
            cfg.update(cfg_extra)
            tmp = os.path.join(tempfile.mkdtemp(prefix=f"ablate-{name}-", dir=bench.CACHE), "tcg_bot.py")
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(src)
            dirs[name] = bench.make_dir(tmp, cfg, f"abl-{name}")
        dirs["v1"] = bench.make_dir(a.v1, bench.cloud_config(), "abl-v1")
        for d in dirs.values():
            bench.warm(h, d, (), bench.WEBHOOKS, 3)
        rows = {n: [] for n in dirs}
        for i in range(a.runs):
            for n, d in dirs.items():
                rows[n].append(bench.run(h, d, (), bench.WEBHOOKS))
            print(f"... round {i + 1}/{a.runs}", flush=True)
        labels = {n: l for n, l, _, _ in STEPS}
        labels["v1"] = "v1"
        out = {n: {"label": labels[n], "summary": bench.summarise(r), "runs": r} for n, r in rows.items()}
        with open(a.out, "w") as f:
            json.dump(out, f, indent=1)
        for n, v in out.items():
            s = v["summary"]
            print(f"{n:14} p50 {s['p50']:6.2f}  mean {s['mean']:6.2f}  req {s['requests_mean']:5.1f}  "
                  f"conn {s['connections_mean']:5.1f}  MB {s['mb_mean']:5.2f}")
    finally:
        h.stop()


if __name__ == "__main__":
    main()
